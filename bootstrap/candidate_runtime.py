from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import stat
import subprocess
import time
from typing import Any, Callable, Mapping, Sequence

from jsonschema import Draft202012Validator

from bootstrap.candidate_host import (
    CandidateHostIdentity,
    validate_candidate_host_identity,
)
from bootstrap.secret_requirements import (
    build_secret_requirements,
    evaluate_secret_readiness,
    load_secret_presence_attestation,
)
from jason_runtime.deployment_identity import FileDeploymentManifestProvider


class CandidateRuntimeError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CandidateRuntimePlan:
    schema_version: str
    instance_id: str
    deployment_identity_sha256: str
    compose_file: str
    overlay_file: str
    env_file: str
    project_name: str
    service: str
    container_name: str
    image: str
    external_networks: tuple[str, ...]
    host_health_port: int
    health_url: str


Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]
HttpGetter = Callable[[str], tuple[int, Mapping[str, Any]]]


def _default_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        text=True,
        capture_output=True,
        check=False,
    )


def load_candidate_runtime_config(
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
        raise CandidateRuntimeError(
            "candidate runtime config invalid: " + errors[0].message
        )
    return document


def _safe_relative(value: str, *, label: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not value.strip():
        raise CandidateRuntimeError(f"unsafe {label}: {value!r}")
    return path


def _safe_env_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise CandidateRuntimeError(
            f"candidate runtime environment file is unavailable: {path}"
        )
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o022:
        raise CandidateRuntimeError(
            "candidate runtime environment file must not be group/world writable"
        )




def _read_env_file(path: Path) -> dict[str, str]:
    _safe_env_file(path)
    values: dict[str, str] = {}
    for line_number, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise CandidateRuntimeError(
                f"candidate runtime env line {line_number} is invalid"
            )
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in values:
            raise CandidateRuntimeError(
                f"candidate runtime env key is invalid or duplicate: {key!r}"
            )
        lowered = key.casefold()
        is_path_reference = key.endswith("_HOST_PATH") or key.endswith("_FILE")
        if (
            any(marker in lowered for marker in ("password", "token", "private_key"))
            and not is_path_reference
        ):
            raise CandidateRuntimeError(
                f"candidate runtime env may not contain direct sensitive key {key}"
            )
        if "secret" in lowered and not is_path_reference:
            raise CandidateRuntimeError(
                f"candidate runtime env may not contain direct sensitive key {key}"
            )
        values[key] = value
    return values


def _private_mount_source(path: Path, *, variable: str) -> None:
    if not path.is_absolute():
        raise CandidateRuntimeError(
            f"candidate mount {variable} must be absolute"
        )
    if path.is_symlink() or not path.is_file():
        raise CandidateRuntimeError(
            f"candidate mount {variable} is unavailable"
        )
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o022:
        raise CandidateRuntimeError(
            f"candidate mount {variable} is writable by group/world"
        )


def _overlay_text(
    *,
    service: str,
    container_name: str,
    image: str,
    host_health_port: int,
    root: Path,
    runtime_config: Mapping[str, Any],
    environment: Mapping[str, str],
) -> str:
    lines = [
        "services:",
        f"  {service}:",
        f"    image: {image}",
        f"    container_name: {container_name}",
        '    restart: "no"',
        "    ports:",
        f'      - "127.0.0.1:{host_health_port}:8080"',
        "    volumes: !override",
    ]
    for item in runtime_config["state_mounts"]:
        relative = _safe_relative(
            str(item["source_relative_path"]),
            label="state mount source",
        )
        source = root / relative
        source.mkdir(parents=True, exist_ok=True)
        destination = str(item["destination"])
        mode = str(item["mode"])
        lines.append(f"      - {source}:{destination}:{mode}")

    for item in runtime_config["secret_mounts"]:
        variable = str(item["environment_variable"])
        source_value = environment.get(variable, "").strip()
        if not source_value:
            raise CandidateRuntimeError(
                f"candidate runtime env is missing {variable}"
            )
        source = Path(source_value)
        _private_mount_source(source, variable=variable)
        destination = str(item["destination"])
        mode = str(item["mode"])
        lines.append(f"      - {source}:{destination}:{mode}")

    return "\n".join(lines) + "\n"




def validate_candidate_runtime_environment_file(
    *,
    env_file: str | Path,
    runtime_config: Mapping[str, Any],
) -> dict[str, Any]:
    environment_file = Path(env_file)
    environment = _read_env_file(environment_file)
    for required_name in (
        "JASON_OLLAMA_MODEL",
        "JASON_SES_DEFAULT_SENDER",
    ):
        if not environment.get(required_name, "").strip():
            raise CandidateRuntimeError(
                f"candidate runtime env is missing {required_name}"
            )

    mount_count = 0
    for item in runtime_config["secret_mounts"]:
        variable = str(item["environment_variable"])
        source_value = environment.get(variable, "").strip()
        if not source_value:
            raise CandidateRuntimeError(
                f"candidate runtime env is missing {variable}"
            )
        _private_mount_source(
            Path(source_value),
            variable=variable,
        )
        mount_count += 1

    return {
        "ollama_model": environment["JASON_OLLAMA_MODEL"].strip(),
        "ses_default_sender": environment[
            "JASON_SES_DEFAULT_SENDER"
        ].strip(),
        "secret_mount_count": mount_count,
        "direct_secret_values_observed": False,
    }


def build_candidate_runtime_plan(
    *,
    target_root: str | Path,
    candidate_identity: CandidateHostIdentity,
    runtime_config: Mapping[str, Any],
    msp_configuration: Mapping[str, Any],
    secret_presence_attestation_path: str | Path,
    env_file: str | Path,
) -> CandidateRuntimePlan:
    validate_candidate_host_identity(candidate_identity)
    root = Path(target_root)
    if not root.is_absolute():
        raise CandidateRuntimeError("target_root must be absolute")

    compose_relative = _safe_relative(
        str(runtime_config["compose_relative_path"]),
        label="compose path",
    )
    compose_file = root / compose_relative
    if compose_file.is_symlink():
        # /opt/jason/current is expected to be a symlink, but the compose file itself
        # must resolve to a regular file under the selected immutable release.
        compose_file = compose_file.resolve()
    if not compose_file.is_file():
        raise CandidateRuntimeError(
            f"candidate runtime compose file is unavailable: {compose_file}"
        )

    manifest = FileDeploymentManifestProvider(
        root / "var/lib/jason/deployment-manifest.json"
    ).read()
    if manifest.get("environment") != "candidate":
        raise CandidateRuntimeError("deployment manifest is not candidate")
    if manifest.get("instance_id") != candidate_identity.instance_id:
        raise CandidateRuntimeError(
            "candidate host identity does not match deployment manifest instance"
        )

    requirements = build_secret_requirements(msp_configuration)
    available = load_secret_presence_attestation(
        secret_presence_attestation_path
    )
    secret_readiness = evaluate_secret_readiness(
        requirements=requirements,
        available_references=available,
    )
    if secret_readiness["status"] != "ready":
        raise CandidateRuntimeError(
            "required secret references are unavailable: "
            + ",".join(secret_readiness["missing_references"])
        )

    environment_file = Path(env_file)
    runtime_environment = validate_candidate_runtime_environment_file(
        env_file=environment_file,
        runtime_config=runtime_config,
    )
    environment = _read_env_file(environment_file)

    host_health_port = int(runtime_config["host_health_port"])
    expected_health_url = (
        f"http://127.0.0.1:{host_health_port}/healthz"
    )
    if str(runtime_config["runtime_health_url"]) != expected_health_url:
        raise CandidateRuntimeError(
            "candidate runtime health URL does not match host health port"
        )

    source_sha = str(manifest["platform"]["source_sha"])
    image = str(runtime_config["candidate_image_prefix"]) + source_sha[:12]
    overlay = root / "var/lib/jason/candidate-runtime.override.yaml"
    overlay.parent.mkdir(parents=True, exist_ok=True)
    overlay.write_text(
        _overlay_text(
            service=str(runtime_config["service"]),
            container_name=str(runtime_config["candidate_container_name"]),
            image=image,
            host_health_port=host_health_port,
            root=root,
            runtime_config=runtime_config,
            environment=environment,
        ),
        encoding="utf-8",
    )
    overlay.chmod(0o640)

    return CandidateRuntimePlan(
        schema_version="1.0",
        instance_id=candidate_identity.instance_id,
        deployment_identity_sha256=str(manifest["identity_sha256"]),
        compose_file=str(compose_file),
        overlay_file=str(overlay),
        env_file=str(environment_file),
        project_name="jason-candidate",
        service=str(runtime_config["service"]),
        container_name=str(runtime_config["candidate_container_name"]),
        image=image,
        host_health_port=host_health_port,
        external_networks=tuple(
            str(item) for item in runtime_config["external_networks"]
        ),
        health_url=str(runtime_config["runtime_health_url"]),
    )


def execute_candidate_runtime_start(
    *,
    plan: CandidateRuntimePlan,
    candidate_identity: CandidateHostIdentity,
    runner: Runner = _default_runner,
    http_getter: HttpGetter,
    health_timeout_seconds: float = 90.0,
    poll_interval_seconds: float = 1.0,
) -> dict[str, Any]:
    validate_candidate_host_identity(candidate_identity)
    if candidate_identity.instance_id != plan.instance_id:
        raise CandidateRuntimeError(
            "candidate identity does not match runtime plan instance"
        )
    if Path(plan.overlay_file).anchor != "/":
        raise CandidateRuntimeError("candidate runtime plan paths must be absolute")

    network_results: list[dict[str, str]] = []
    for network in plan.external_networks:
        inspect = runner(("docker", "network", "inspect", network))
        if inspect.returncode == 0:
            network_results.append(
                {"network": network, "result": "already_present"}
            )
            continue
        create = runner(("docker", "network", "create", network))
        if create.returncode != 0:
            raise CandidateRuntimeError(
                f"failed to create candidate runtime network {network}"
            )
        network_results.append({"network": network, "result": "created"})

    command_prefix = (
        "docker",
        "compose",
        "--project-name",
        plan.project_name,
        "--env-file",
        plan.env_file,
        "-f",
        plan.compose_file,
        "-f",
        plan.overlay_file,
    )
    rendered = runner(command_prefix + ("config", "--quiet"))
    if rendered.returncode != 0:
        raise CandidateRuntimeError(
            "candidate runtime compose validation failed"
        )

    started = runner(
        command_prefix
        + (
            "up",
            "-d",
            "--build",
            "--no-deps",
            plan.service,
        )
    )
    if started.returncode != 0:
        raise CandidateRuntimeError(
            "candidate runtime compose startup failed"
        )

    deadline = time.monotonic() + float(health_timeout_seconds)
    last_status = 0
    while True:
        status, payload = http_getter(plan.health_url)
        last_status = status
        if (
            status == 200
            and payload.get("status") == "ok"
            and payload.get("deployment_identity_sha256")
            == plan.deployment_identity_sha256
        ):
            return {
                "status": "runtime_healthy",
                "instance_id": plan.instance_id,
                "deployment_identity_sha256": (
                    plan.deployment_identity_sha256
                ),
                "container_name": plan.container_name,
                "image": plan.image,
                "networks": network_results,
                "compose_validated": True,
                "health_identity_match": True,
                "production_deploy_script_used": False,
            }
        if time.monotonic() >= deadline:
            raise CandidateRuntimeError(
                "candidate runtime health did not become ready "
                f"(last_http_status={last_status})"
            )
        time.sleep(float(poll_interval_seconds))


def plan_json(plan: CandidateRuntimePlan) -> str:
    return json.dumps(asdict(plan), indent=2, sort_keys=True) + "\n"
