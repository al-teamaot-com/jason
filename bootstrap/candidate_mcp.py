from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any, Callable, Mapping, Sequence

from jsonschema import Draft202012Validator

from bootstrap.candidate_host import (
    CandidateHostIdentity,
    validate_candidate_host_identity,
)
from bootstrap.candidate_runtime import (
    CandidateRuntimePlan,
    validate_candidate_runtime_environment_file,
)


class CandidateMcpError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CandidateMcpPlan:
    schema_version: str
    instance_id: str
    deployment_identity_sha256: str
    source_sha: str
    dockerfile: str
    build_context: str
    base_runtime_image: str
    image: str
    container_name: str
    host_health_port: int
    health_url: str
    env_file: str
    networks: tuple[str, ...]
    state_mounts: tuple[tuple[str, str, str], ...]
    secret_mounts: tuple[tuple[str, str, str], ...]


Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]
HttpGetter = Callable[[str], tuple[int, Mapping[str, Any]]]


def _default_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        text=True,
        capture_output=True,
        check=False,
    )


def load_candidate_mcp_config(
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
        raise CandidateMcpError(
            "candidate MCP config invalid: " + errors[0].message
        )
    if "jason-core" not in document["networks"]:
        raise CandidateMcpError(
            "candidate MCP networks must include jason-core"
        )
    return document


def _read_candidate_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise CandidateMcpError(
                "candidate environment contains an invalid line"
            )
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def validate_candidate_mcp_environment(
    *,
    env_file: str | Path,
    runtime_config: Mapping[str, Any],
    mcp_config: Mapping[str, Any],
) -> dict[str, Any]:
    runtime_summary = validate_candidate_runtime_environment_file(
        env_file=env_file,
        runtime_config=runtime_config,
    )
    environment = _read_candidate_env(Path(env_file))
    required = (
        "JASON_MCP_ENTRA_TENANT_ID",
        "JASON_MCP_ENTRA_CLIENT_ID",
        "JASON_MCP_RESOURCE_URL",
        "JASON_PROVIDER_HEALTH_CANARY_ORGANIZATION_ID",
        "JASON_PROVIDER_HEALTH_CANARY_PROVIDERS",
    )
    missing = [
        name
        for name in required
        if not environment.get(name, "").strip()
    ]
    if missing:
        raise CandidateMcpError(
            "candidate MCP environment is incomplete: "
            + ",".join(missing)
        )
    expected_resource = (
        "http://127.0.0.1:"
        + str(int(mcp_config["host_health_port"]))
        + "/mcp"
    )
    if environment["JASON_MCP_RESOURCE_URL"] != expected_resource:
        raise CandidateMcpError(
            "candidate MCP resource URL does not match candidate host port"
        )
    return {
        "tenant_id_present": True,
        "client_id_present": True,
        "resource_url": expected_resource,
        "runtime_secret_mount_count": runtime_summary[
            "secret_mount_count"
        ],
        "canary_organization_id": environment[
            "JASON_PROVIDER_HEALTH_CANARY_ORGANIZATION_ID"
        ],
        "canary_providers": tuple(
            sorted(
                item.strip()
                for item in environment[
                    "JASON_PROVIDER_HEALTH_CANARY_PROVIDERS"
                ].split(",")
                if item.strip()
            )
        ),
        "direct_secret_values_observed": False,
    }


def build_candidate_mcp_plan(
    *,
    target_root: str | Path,
    candidate_identity: CandidateHostIdentity,
    runtime_plan: CandidateRuntimePlan,
    runtime_config: Mapping[str, Any],
    mcp_config: Mapping[str, Any],
    env_file: str | Path,
) -> CandidateMcpPlan:
    validate_candidate_host_identity(candidate_identity)
    root = Path(target_root)
    if not root.is_absolute():
        raise CandidateMcpError("candidate target root must be absolute")
    if runtime_plan.instance_id != candidate_identity.instance_id:
        raise CandidateMcpError(
            "candidate Runtime and MCP instance identities differ"
        )

    validate_candidate_mcp_environment(
        env_file=env_file,
        runtime_config=runtime_config,
        mcp_config=mcp_config,
    )
    environment = _read_candidate_env(Path(env_file))

    relative = Path(str(mcp_config["dockerfile_relative_path"]))
    if relative.is_absolute() or ".." in relative.parts:
        raise CandidateMcpError("candidate MCP Dockerfile path is unsafe")
    dockerfile = root / relative
    if dockerfile.is_symlink():
        dockerfile = dockerfile.resolve()
    if not dockerfile.is_file():
        raise CandidateMcpError(
            "candidate MCP Dockerfile is unavailable"
        )

    current = root / "opt/jason/current"
    build_context = current.resolve() if current.is_symlink() else current
    if not build_context.is_dir():
        raise CandidateMcpError(
            "candidate MCP build context is unavailable"
        )

    source_sha = runtime_plan.image.rsplit("-", 1)[-1]
    image = str(mcp_config["candidate_image_prefix"]) + source_sha

    state_mounts = []
    for item in runtime_config["state_mounts"]:
        source = root / Path(str(item["source_relative_path"]))
        source.mkdir(parents=True, exist_ok=True)
        state_mounts.append(
            (
                str(source),
                str(item["destination"]),
                str(item["mode"]),
            )
        )

    secret_mounts = []
    for item in runtime_config["secret_mounts"]:
        variable = str(item["environment_variable"])
        source = environment.get(variable, "").strip()
        if not source:
            raise CandidateMcpError(
                "candidate MCP missing protected mount path "
                + variable
            )
        secret_mounts.append(
            (
                source,
                str(item["destination"]),
                str(item["mode"]),
            )
        )

    health_port = int(mcp_config["host_health_port"])
    expected_health = f"http://127.0.0.1:{health_port}/healthz"
    if str(mcp_config["health_url"]) != expected_health:
        raise CandidateMcpError(
            "candidate MCP health URL does not match host port"
        )

    return CandidateMcpPlan(
        schema_version="1.0",
        instance_id=candidate_identity.instance_id,
        deployment_identity_sha256=runtime_plan.deployment_identity_sha256,
        source_sha=source_sha,
        dockerfile=str(dockerfile),
        build_context=str(build_context),
        base_runtime_image=runtime_plan.image,
        image=image,
        container_name=str(mcp_config["candidate_container_name"]),
        host_health_port=health_port,
        health_url=expected_health,
        env_file=str(env_file),
        networks=tuple(str(item) for item in mcp_config["networks"]),
        state_mounts=tuple(state_mounts),
        secret_mounts=tuple(secret_mounts),
    )


def _mount_args(
    mounts: Sequence[tuple[str, str, str]],
) -> list[str]:
    result: list[str] = []
    for source, destination, mode in mounts:
        value = (
            "type=bind,src="
            + source
            + ",dst="
            + destination
        )
        if mode == "ro":
            value += ",readonly"
        result.extend(("--mount", value))
    return result


def execute_candidate_mcp_start(
    *,
    plan: CandidateMcpPlan,
    candidate_identity: CandidateHostIdentity,
    runner: Runner = _default_runner,
    http_getter: HttpGetter,
    health_timeout_seconds: float = 90.0,
    poll_interval_seconds: float = 1.0,
) -> dict[str, Any]:
    validate_candidate_host_identity(candidate_identity)
    if plan.instance_id != candidate_identity.instance_id:
        raise CandidateMcpError(
            "candidate MCP plan instance does not match host identity"
        )

    base = runner(("docker", "image", "inspect", plan.base_runtime_image))
    if base.returncode != 0:
        raise CandidateMcpError(
            "candidate Runtime base image is unavailable for MCP build"
        )

    build = runner(
        (
            "docker",
            "build",
            "--build-arg",
            "BASE_IMAGE=" + plan.base_runtime_image,
            "--label",
            "org.opencontainers.image.revision=" + plan.source_sha,
            "-f",
            plan.dockerfile,
            "-t",
            plan.image,
            plan.build_context,
        )
    )
    if build.returncode != 0:
        raise CandidateMcpError("candidate MCP image build failed")

    runner(("docker", "rm", "-f", plan.container_name))

    command = [
        "docker",
        "run",
        "-d",
        "--name",
        plan.container_name,
        "--restart",
        "no",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "--network",
        plan.networks[0],
        "-p",
        f"127.0.0.1:{plan.host_health_port}:8000",
        "--env-file",
        plan.env_file,
    ]
    command.extend(
        _mount_args(plan.state_mounts + plan.secret_mounts)
    )
    command.append(plan.image)
    started = runner(tuple(command))
    if started.returncode != 0:
        raise CandidateMcpError("candidate MCP container start failed")

    for network in plan.networks[1:]:
        connected = runner(
            (
                "docker",
                "network",
                "connect",
                network,
                plan.container_name,
            )
        )
        if connected.returncode != 0:
            raise CandidateMcpError(
                "failed to connect candidate MCP network " + network
            )

    deadline = time.monotonic() + float(health_timeout_seconds)
    last_status = 0
    while True:
        status, payload = http_getter(plan.health_url)
        last_status = status
        if status == 200 and payload.get("status") == "ok":
            break
        if time.monotonic() >= deadline:
            raise CandidateMcpError(
                "candidate MCP health did not become ready "
                f"(last_http_status={last_status})"
            )
        time.sleep(float(poll_interval_seconds))

    postcheck = runner(
        (
            "docker",
            "exec",
            plan.container_name,
            "python",
            "-c",
            (
                "import jason_mcp.server as s; "
                "x=s.jason_mcp_status(); "
                "assert x['status']=='ok'; "
                "assert x['governed_execution']=='central-orchestrator'; "
                "assert x['generic_execution_tool'] is True; "
                "assert x['direct_provider_access'] is False"
            ),
        )
    )
    if postcheck.returncode != 0:
        raise CandidateMcpError(
            "candidate MCP governance postcheck failed"
        )

    return {
        "status": "mcp_healthy",
        "container_name": plan.container_name,
        "image": plan.image,
        "base_runtime_image": plan.base_runtime_image,
        "governance_postcheck": "pass",
        "production_deploy_script_used": False,
    }


def run_candidate_provider_canaries(
    *,
    plan: CandidateMcpPlan,
    target_root: str | Path,
    required_providers: Sequence[str],
    runner: Runner = _default_runner,
) -> dict[str, Any]:
    completed = runner(
        (
            "docker",
            "exec",
            plan.container_name,
            "python",
            "-m",
            "jason_mcp.provider_health_canary",
        )
    )
    if completed.returncode != 0:
        raise CandidateMcpError(
            "candidate provider canary runner failed"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise CandidateMcpError(
            "candidate provider canary returned invalid JSON"
        ) from exc

    if payload.get("schema_version") != 1:
        raise CandidateMcpError(
            "candidate provider canary schema is unsupported"
        )
    grouped: dict[str, list[bool]] = {}
    for item in payload.get("results", ()):
        if not isinstance(item, Mapping):
            continue
        provider = str(item.get("provider") or "")
        healthy = item.get("healthy")
        if provider and isinstance(healthy, bool):
            grouped.setdefault(provider, []).append(healthy)

    unhealthy = [
        str(provider)
        for provider in required_providers
        if not grouped.get(str(provider))
        or not all(grouped[str(provider)])
    ]
    if unhealthy:
        raise CandidateMcpError(
            "candidate provider canaries are not healthy: "
            + ",".join(sorted(unhealthy))
        )

    root = Path(target_root)
    output = root / "var/lib/jason/provider-health-canaries.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=".provider-health-canaries-",
        suffix=".json",
        dir=output.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)

    return {
        "status": "provider_canaries_healthy",
        "required_providers": sorted(
            str(item) for item in required_providers
        ),
        "result_count": len(payload.get("results", ())),
        "output": str(output),
        "secret_values_observed": False,
    }
