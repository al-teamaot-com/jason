from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping, Sequence

from bootstrap.install_runtime import evaluate_candidate_readiness


class CandidateActivationError(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class CandidateHostIdentity:
    schema_version: str
    environment: str
    instance_id: str
    bootstrap_authorized: bool


@dataclass(frozen=True, slots=True)
class ActivationAction:
    action: str
    arguments: tuple[str, ...]
    mutating: bool


@dataclass(frozen=True, slots=True)
class CandidateActivationPlan:
    schema_version: str
    instance_id: str
    target_root: str
    actions: tuple[ActivationAction, ...]


def load_candidate_host_identity(path: str | Path) -> CandidateHostIdentity:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    identity = CandidateHostIdentity(
        schema_version=str(payload.get("schema_version") or ""),
        environment=str(payload.get("environment") or ""),
        instance_id=str(payload.get("instance_id") or ""),
        bootstrap_authorized=bool(payload.get("bootstrap_authorized")),
    )
    if identity.schema_version != "1.0":
        raise CandidateActivationError("unsupported candidate-host identity schema")
    if identity.environment != "candidate":
        raise CandidateActivationError("host identity is not candidate")
    if not identity.instance_id.strip():
        raise CandidateActivationError("candidate instance_id is missing")
    if not identity.bootstrap_authorized:
        raise CandidateActivationError("candidate bootstrap is not authorized")
    return identity


def _portable_unit_names(resources: Mapping[str, Any]) -> tuple[str, ...]:
    names = []
    for unit in resources["systemd_units"]:
        if bool(unit["portable"]):
            names.append(Path(str(unit["source"])).name)
    return tuple(sorted(names))


def build_candidate_activation_plan(
    *,
    target_root: str | Path,
    resources: Mapping[str, Any],
    candidate_identity: CandidateHostIdentity,
) -> CandidateActivationPlan:
    if candidate_identity.environment != "candidate":
        raise CandidateActivationError("Production activation is not supported here")
    if not candidate_identity.bootstrap_authorized:
        raise CandidateActivationError("candidate bootstrap is not authorized")

    root = Path(target_root)
    readiness = evaluate_candidate_readiness(
        target_root=root,
        resources=resources,
    )
    if readiness["status"] != "ready_for_runtime_activation":
        raise CandidateActivationError(
            "candidate filesystem is not ready for runtime activation: "
            + ",".join(readiness["blockers"])
        )

    actions: list[ActivationAction] = []
    for network in resources["networks"]:
        if not bool(network["required"]):
            continue
        name = str(network["name"])
        actions.append(
            ActivationAction(
                action="ensure_docker_network",
                arguments=(name,),
                mutating=True,
            )
        )

    for unit_name in _portable_unit_names(resources):
        actions.append(
            ActivationAction(
                action="enable_systemd_unit",
                arguments=(unit_name,),
                mutating=True,
            )
        )

    return CandidateActivationPlan(
        schema_version="1.0",
        instance_id=candidate_identity.instance_id,
        target_root=str(root),
        actions=tuple(actions),
    )


Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def _default_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        text=True,
        capture_output=True,
        check=False,
    )


def execute_candidate_activation_plan(
    *,
    plan: CandidateActivationPlan,
    runner: Runner = _default_runner,
) -> dict[str, Any]:
    if Path(plan.target_root) != Path("/"):
        raise CandidateActivationError(
            "runtime activation may execute only on the candidate host root"
        )

    evidence: list[dict[str, Any]] = []
    for action in plan.actions:
        if action.action == "ensure_docker_network":
            name = action.arguments[0]
            inspect = runner(("docker", "network", "inspect", name))
            if inspect.returncode == 0:
                evidence.append(
                    {"action": action.action, "target": name, "result": "already_present"}
                )
                continue
            create = runner(("docker", "network", "create", name))
            if create.returncode != 0:
                raise CandidateActivationError(
                    f"failed to create required Docker network {name}"
                )
            evidence.append(
                {"action": action.action, "target": name, "result": "created"}
            )
            continue

        if action.action == "enable_systemd_unit":
            unit = action.arguments[0]
            enable = runner(("systemctl", "enable", unit))
            if enable.returncode != 0:
                raise CandidateActivationError(
                    f"failed to enable candidate systemd unit {unit}"
                )
            evidence.append(
                {"action": action.action, "target": unit, "result": "enabled"}
            )
            continue

        raise CandidateActivationError(
            f"unsupported candidate activation action: {action.action}"
        )

    return {
        "status": "candidate_activation_prepared",
        "instance_id": plan.instance_id,
        "actions": evidence,
        "services_started": False,
        "provider_secrets_enrolled": False,
    }


def write_activation_plan(
    plan: CandidateActivationPlan,
    *,
    output: str | Path,
) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": plan.schema_version,
                "instance_id": plan.instance_id,
                "target_root": plan.target_root,
                "actions": [asdict(item) for item in plan.actions],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path
