from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
from typing import Any, Callable, Mapping

from jsonschema import Draft202012Validator


SUPPORTED_ENVIRONMENTS = {"development", "candidate"}
SUPPORTED_OS_ID = "ubuntu"
SUPPORTED_OS_VERSION_PREFIX = "24.04"


@dataclass(frozen=True, slots=True)
class HostObservation:
    os_id: str
    os_version: str
    architecture: str
    python_version: str
    docker_version: str | None
    compose_version: str | None


@dataclass(frozen=True, slots=True)
class InstallAction:
    action: str
    target: str
    detail: str


@dataclass(frozen=True, slots=True)
class CleanInstallPlan:
    schema_version: str
    environment: str
    target_root: str
    msp_configuration_revision: str
    msp_policy_revision: str
    host: HostObservation
    actions: tuple[InstallAction, ...]


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_json_sha256(value: Any) -> str:
    import hashlib

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_json_document(*, document: Any, schema: Mapping[str, Any], label: str) -> None:
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(document),
        key=lambda item: list(item.absolute_path),
    )
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.absolute_path) or "<root>"
        raise ValueError(f"{label} validation failed at {location}: {first.message}")


def _command_version(
    command: list[str],
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str | None:
    try:
        result = runner(
            command,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or result.stderr or "").strip() or None


def observe_host(
    *,
    os_release_path: str | Path = "/etc/os-release",
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> HostObservation:
    os_values: dict[str, str] = {}
    for raw in Path(os_release_path).read_text(encoding="utf-8").splitlines():
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        os_values[key] = value.strip().strip('"')

    return HostObservation(
        os_id=os_values.get("ID", ""),
        os_version=os_values.get("VERSION_ID", ""),
        architecture=platform.machine(),
        python_version=platform.python_version(),
        docker_version=_command_version(["docker", "--version"], runner=runner),
        compose_version=_command_version(
            ["docker", "compose", "version"],
            runner=runner,
        ),
    )


def _version_tuple(value: str) -> tuple[int, ...]:
    matches = re.findall(r"\d+", value)
    return tuple(int(part) for part in matches[:3])


def validate_supported_host(host: HostObservation, *, require_container_runtime: bool) -> None:
    if host.os_id != SUPPORTED_OS_ID:
        raise ValueError(f"unsupported OS: {host.os_id or '<unknown>'}")
    if not host.os_version.startswith(SUPPORTED_OS_VERSION_PREFIX):
        raise ValueError(f"unsupported Ubuntu version: {host.os_version or '<unknown>'}")
    if host.architecture not in {"x86_64", "amd64"}:
        raise ValueError(f"unsupported architecture: {host.architecture}")
    if _version_tuple(host.python_version) < (3, 12):
        raise ValueError(f"Python 3.12+ required, observed {host.python_version}")
    if require_container_runtime:
        if not host.docker_version:
            raise ValueError("Docker is required but unavailable")
        if not host.compose_version:
            raise ValueError("Docker Compose is required but unavailable")


def canonical_layout(target_root: str | Path) -> tuple[InstallAction, ...]:
    root = Path(target_root)
    directories = (
        "opt/jason/releases",
        "opt/jason/services",
        "opt/jason/bootstrap",
        "var/lib/jason",
        "var/lib/jason/audit",
        "var/lib/jason/authority",
        "var/lib/jason/orchestration",
        "var/lib/jason/playbooks",
        "var/lib/jason/provider-state",
        "var/lib/jason/recovery",
        "var/log/jason",
        "run/jason",
    )
    actions = [
        InstallAction("create_directory", str(root / item), "canonical Jason path")
        for item in directories
    ]
    actions.extend(
        (
            InstallAction("validate_network", "jason-core", "required Docker network"),
            InstallAction(
                "validate_network",
                "jason-observability",
                "required when observability profile is enabled",
            ),
            InstallAction(
                "validate_secret_provider",
                "configured-provider",
                "secret enrollment remains a separate governed process",
            ),
            InstallAction(
                "write_install_identity",
                str(root / "var/lib/jason/deployment-bootstrap.json"),
                "records validated bootstrap inputs; contains no secrets",
            ),
        )
    )
    return tuple(actions)


def build_plan(
    *,
    environment: str,
    target_root: str | Path,
    msp_configuration_path: str | Path,
    msp_policy_path: str | Path,
    schema_root: str | Path,
    host: HostObservation,
) -> CleanInstallPlan:
    normalized_environment = environment.strip().lower()
    if normalized_environment not in SUPPORTED_ENVIRONMENTS:
        raise PermissionError(
            "clean-install implementation is currently non-production only; "
            "supported environments are development and candidate"
        )

    root = Path(target_root)
    if root == Path("/"):
        raise PermissionError("clean-install may not target the live filesystem root")
    if not root.is_absolute():
        raise ValueError("target_root must be an absolute path")

    config = read_json(msp_configuration_path)
    policy = read_json(msp_policy_path)
    schema_root = Path(schema_root)
    validate_json_document(
        document=config,
        schema=read_json(schema_root / "msp-configuration.schema.json"),
        label="MSP configuration",
    )
    validate_json_document(
        document=policy,
        schema=read_json(schema_root / "msp-policy.schema.json"),
        label="MSP policy",
    )

    require_container_runtime = any(
        bool(provider.get("enabled"))
        for provider in dict(config.get("providers") or {}).values()
    )
    validate_supported_host(host, require_container_runtime=require_container_runtime)

    return CleanInstallPlan(
        schema_version="1.0",
        environment=normalized_environment,
        target_root=str(root),
        msp_configuration_revision=canonical_json_sha256(config),
        msp_policy_revision=canonical_json_sha256(policy),
        host=host,
        actions=canonical_layout(root),
    )


def apply_layout(plan: CleanInstallPlan) -> Path:
    if plan.environment not in SUPPORTED_ENVIRONMENTS:
        raise PermissionError("bootstrap apply is non-production only")
    target_root = Path(plan.target_root)
    if target_root == Path("/"):
        raise PermissionError("bootstrap apply may not target /")

    for action in plan.actions:
        if action.action == "create_directory":
            Path(action.target).mkdir(parents=True, exist_ok=True)

    identity = target_root / "var/lib/jason/deployment-bootstrap.json"
    payload = {
        "schema_version": plan.schema_version,
        "environment": plan.environment,
        "target_root": plan.target_root,
        "msp_configuration_revision": plan.msp_configuration_revision,
        "msp_policy_revision": plan.msp_policy_revision,
        "host": asdict(plan.host),
        "planned_networks": [
            action.target
            for action in plan.actions
            if action.action == "validate_network"
        ],
    }
    identity.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return identity


def _default_schema_root() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "schemas"


def main() -> int:
    parser = argparse.ArgumentParser(description="Jason v1 clean-install planner")
    parser.add_argument("--environment", required=True, choices=sorted(SUPPORTED_ENVIRONMENTS))
    parser.add_argument("--target-root", required=True)
    parser.add_argument("--msp-config", required=True)
    parser.add_argument("--msp-policy", required=True)
    parser.add_argument("--schema-root", default=str(_default_schema_root()))
    parser.add_argument("--apply-layout", action="store_true")
    args = parser.parse_args()

    host = observe_host()
    plan = build_plan(
        environment=args.environment,
        target_root=args.target_root,
        msp_configuration_path=args.msp_config,
        msp_policy_path=args.msp_policy,
        schema_root=args.schema_root,
        host=host,
    )
    print(json.dumps(asdict(plan), indent=2, sort_keys=True))
    if args.apply_layout:
        identity = apply_layout(plan)
        print(f"BOOTSTRAP_LAYOUT=PASS identity={identity}")
    else:
        print("BOOTSTRAP_PLAN=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
