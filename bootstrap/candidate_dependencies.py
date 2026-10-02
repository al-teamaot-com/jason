from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping, Sequence

from jsonschema import Draft202012Validator

from bootstrap.candidate_host import (
    CandidateHostIdentity,
    authorize_mutation_target,
    validate_candidate_host_identity,
)


class CandidateDependencyError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CandidateDependencyPlan:
    schema_version: str
    instance_id: str
    target_root: str
    compose_file: str
    ollama_model: str
    networks: tuple[str, ...]
    status: str
    blockers: tuple[str, ...]


Runner = Callable[
    [Sequence[str]],
    subprocess.CompletedProcess[str],
]


def _default_runner(
    command: Sequence[str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        text=True,
        capture_output=True,
        check=False,
    )


def load_candidate_dependency_config(
    document_path: str | Path,
    schema_path: str | Path,
) -> dict[str, Any]:
    document = json.loads(Path(document_path).read_text(encoding="utf-8"))
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(document),
        key=lambda item: list(item.absolute_path),
    )
    if errors:
        raise CandidateDependencyError(
            "candidate dependency config invalid: "
            + errors[0].message
        )
    required = {
        "jason-core",
        "jason-observability",
        "openclaw_default",
    }
    networks = set(str(item) for item in document["networks"])
    if not required.issubset(networks):
        raise CandidateDependencyError(
            "candidate dependency networks must include "
            "jason-core, jason-observability, and openclaw_default"
        )
    return document


def _network_exists(runner: Runner, name: str) -> bool:
    return (
        runner(("docker", "network", "inspect", name)).returncode
        == 0
    )


def _container_state(runner: Runner, name: str) -> str:
    result = runner(
        (
            "docker",
            "inspect",
            "--format",
            "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
            name,
        )
    )
    if result.returncode != 0:
        return "missing"
    return (result.stdout or "").strip().lower() or "unknown"


def _openbao_status(runner: Runner) -> str:
    result = runner(
        (
            "docker",
            "exec",
            "openbao",
            "bao",
            "status",
            "-format=json",
        )
    )
    raw = (result.stdout or "").strip()
    if not raw:
        return "unavailable"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return "unavailable"
    if not bool(payload.get("initialized")):
        return "uninitialized"
    if bool(payload.get("sealed")):
        return "sealed"
    return "ready"


def _ollama_model_present(
    runner: Runner,
    model: str,
) -> bool:
    result = runner(
        ("docker", "exec", "jason-ollama", "ollama", "list")
    )
    if result.returncode != 0:
        return False
    names = {
        line.split()[0]
        for line in (result.stdout or "").splitlines()[1:]
        if line.strip()
    }
    return model in names


def _compose_text(
    *,
    root: Path,
    config: Mapping[str, Any],
) -> str:
    openbao_config = (
        root / "opt/jason/current/deploy/openbao/config"
    )
    openbao_state = root / "var/lib/jason/openbao"
    ollama_cache = root / "var/lib/jason/cache/ollama"
    return (
        "services:\n"
        "  openbao:\n"
        f"    image: {config['openbao_image']}\n"
        "    container_name: openbao\n"
        "    hostname: openbao\n"
        "    user: \"0:0\"\n"
        "    restart: \"no\"\n"
        "    command: [\"server\", \"-config=/openbao/config/openbao.hcl\"]\n"
        "    ports:\n"
        f"      - \"127.0.0.1:{int(config['openbao_host_port'])}:8200\"\n"
        "    volumes:\n"
        f"      - {openbao_config}:/openbao/config:ro\n"
        f"      - {openbao_state / 'data'}:/openbao/data\n"
        f"      - {openbao_state / 'audit'}:/openbao/audit\n"
        f"      - {openbao_state / 'logs'}:/openbao/logs\n"
        "    networks: [jason-core]\n"
        "    cap_add: [IPC_LOCK]\n"
        "    security_opt: [no-new-privileges:true]\n"
        "  ollama:\n"
        f"    image: {config['ollama_image']}\n"
        "    container_name: jason-ollama\n"
        "    restart: \"no\"\n"
        "    volumes:\n"
        f"      - {ollama_cache}:/root/.ollama\n"
        "    ports:\n"
        f"      - \"127.0.0.1:{int(config['ollama_host_port'])}:11434\"\n"
        "    healthcheck:\n"
        "      test: [\"CMD\", \"ollama\", \"list\"]\n"
        "      interval: 15s\n"
        "      timeout: 10s\n"
        "      retries: 8\n"
        "      start_period: 20s\n"
        "    networks: [jason-observability]\n"
        "networks:\n"
        "  jason-core:\n"
        "    external: true\n"
        "    name: jason-core\n"
        "  jason-observability:\n"
        "    external: true\n"
        "    name: jason-observability\n"
    )


def build_candidate_dependency_plan(
    *,
    target_root: str | Path,
    candidate_identity: CandidateHostIdentity,
    dependency_config: Mapping[str, Any],
    ollama_model: str,
) -> CandidateDependencyPlan:
    validate_candidate_host_identity(candidate_identity)
    root = authorize_mutation_target(
        target_root=target_root,
        candidate_identity=candidate_identity,
        operation="candidate dependency plan",
    )
    blockers: list[str] = []
    model = ollama_model.strip()
    if not model:
        blockers.append("ollama_model_missing")

    openbao_config = (
        root / "opt/jason/current/deploy/openbao/config/openbao.hcl"
    )
    if not openbao_config.is_file():
        blockers.append("openbao_config_missing")

    compose_path = (
        root / "var/lib/jason/candidate-dependencies.compose.yaml"
    )
    compose_path.parent.mkdir(parents=True, exist_ok=True)
    compose_path.write_text(
        _compose_text(root=root, config=dependency_config),
        encoding="utf-8",
    )
    compose_path.chmod(0o640)

    return CandidateDependencyPlan(
        schema_version="1.0",
        instance_id=candidate_identity.instance_id,
        target_root=str(root),
        compose_file=str(compose_path),
        ollama_model=model,
        networks=tuple(str(item) for item in dependency_config["networks"]),
        status=(
            "ready_for_dependency_prepare"
            if not blockers
            else "blocked"
        ),
        blockers=tuple(blockers),
    )


def prepare_candidate_dependencies(
    *,
    plan: CandidateDependencyPlan,
    candidate_identity: CandidateHostIdentity,
    runner: Runner = _default_runner,
) -> dict[str, Any]:
    validate_candidate_host_identity(candidate_identity)
    root = authorize_mutation_target(
        target_root=plan.target_root,
        candidate_identity=candidate_identity,
        operation="candidate dependency prepare",
    )
    if plan.instance_id != candidate_identity.instance_id:
        raise CandidateDependencyError(
            "dependency plan instance does not match candidate host"
        )
    if plan.status != "ready_for_dependency_prepare":
        raise CandidateDependencyError(
            "candidate dependency plan is blocked: "
            + ",".join(plan.blockers)
        )

    for relative in (
        "var/lib/jason/openbao/data",
        "var/lib/jason/openbao/audit",
        "var/lib/jason/openbao/logs",
        "var/lib/jason/cache/ollama",
    ):
        path = root / relative
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(0o700)

    evidence: list[dict[str, str]] = []
    for network in plan.networks:
        if _network_exists(runner, network):
            evidence.append(
                {
                    "dependency": "network",
                    "name": network,
                    "result": "already_present",
                }
            )
            continue
        created = runner(
            ("docker", "network", "create", network)
        )
        if created.returncode != 0:
            raise CandidateDependencyError(
                "failed to create candidate network " + network
            )
        evidence.append(
            {
                "dependency": "network",
                "name": network,
                "result": "created",
            }
        )

    started = runner(
        (
            "docker",
            "compose",
            "--project-name",
            "jason-candidate-dependencies",
            "-f",
            plan.compose_file,
            "up",
            "-d",
            "openbao",
            "ollama",
        )
    )
    if started.returncode != 0:
        raise CandidateDependencyError(
            "failed to start candidate dependency services"
        )
    evidence.append(
        {
            "dependency": "containers",
            "name": "openbao,jason-ollama",
            "result": "started",
        }
    )

    return {
        "status": "dependency_services_started",
        "instance_id": candidate_identity.instance_id,
        "evidence": evidence,
        "secret_values_observed": False,
    }


def verify_candidate_dependencies(
    *,
    plan: CandidateDependencyPlan,
    candidate_identity: CandidateHostIdentity,
    runner: Runner = _default_runner,
    pull_ollama_model: bool = False,
) -> dict[str, Any]:
    validate_candidate_host_identity(candidate_identity)
    authorize_mutation_target(
        target_root=plan.target_root,
        candidate_identity=candidate_identity,
        operation="candidate dependency verification",
    )
    blockers: list[str] = []

    for network in plan.networks:
        if not _network_exists(runner, network):
            blockers.append("network_missing:" + network)

    openbao_state = _container_state(runner, "openbao")
    if openbao_state not in {"running", "healthy"}:
        blockers.append("openbao_container_not_running")
    else:
        bao = _openbao_status(runner)
        if bao != "ready":
            blockers.append("openbao_not_ready:" + bao)

    ollama_state = _container_state(runner, "jason-ollama")
    if ollama_state != "healthy":
        blockers.append("ollama_not_healthy")
    elif not _ollama_model_present(runner, plan.ollama_model):
        if pull_ollama_model:
            pulled = runner(
                (
                    "docker",
                    "exec",
                    "jason-ollama",
                    "ollama",
                    "pull",
                    plan.ollama_model,
                )
            )
            if pulled.returncode != 0 or not _ollama_model_present(
                runner,
                plan.ollama_model,
            ):
                blockers.append(
                    "ollama_model_unavailable:" + plan.ollama_model
                )
        else:
            blockers.append(
                "ollama_model_unavailable:" + plan.ollama_model
            )

    return {
        "status": "ready" if not blockers else "blocked",
        "instance_id": candidate_identity.instance_id,
        "openbao_status": (
            "ready"
            if not any(item.startswith("openbao_") for item in blockers)
            else "blocked"
        ),
        "ollama_status": (
            "ready"
            if not any(item.startswith("ollama_") for item in blockers)
            else "blocked"
        ),
        "blockers": blockers,
        "secret_values_observed": False,
    }
