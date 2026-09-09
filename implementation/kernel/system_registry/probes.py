from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Mapping, Sequence

from kernel.system_registry.contracts import Observation
from kernel.system_registry.repository import InMemorySystemRegistry


ALLOWED_PROBE_TYPES = frozenset(
    {
        "docker_container",
        "docker_file_sha256",
        "file_sha256",
        "file_exists",
    }
)


class ProbeExecutionError(RuntimeError):
    """Raised when a read-only System Registry observation cannot complete."""


@dataclass(frozen=True, slots=True)
class VerificationCheck:
    registry_id: str
    method: str
    probe: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class VerificationPlan:
    source: str
    checks: tuple[VerificationCheck, ...]


def load_verification_plan(
    path: Path,
    *,
    registry: InMemorySystemRegistry,
) -> VerificationPlan:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != "1.0":
        raise ValueError("Unsupported System Registry verification-plan version.")
    source = str(raw.get("source", "")).strip()
    if not source:
        raise ValueError("Verification plan requires a non-empty source.")

    checks: list[VerificationCheck] = []
    seen: set[str] = set()
    for item in raw.get("checks", []):
        registry_id = str(item.get("registry_id", "")).strip()
        method = str(item.get("method", "")).strip()
        probe = {str(key): str(value) for key, value in item.get("probe", {}).items()}
        probe_type = probe.get("type", "")
        if registry_id in seen:
            raise ValueError(f"Duplicate verification-plan registry ID: {registry_id}")
        seen.add(registry_id)
        entity = registry.get(registry_id)
        if method not in entity.verification_methods:
            raise ValueError(
                f"Verification method is not registered for {registry_id}: {method}"
            )
        if probe_type not in ALLOWED_PROBE_TYPES:
            raise ValueError(
                f"Unsupported read-only System Registry probe type: {probe_type}"
            )
        _validate_probe(probe)
        checks.append(
            VerificationCheck(
                registry_id=registry_id,
                method=method,
                probe=probe,
            )
        )

    if not checks:
        raise ValueError("Verification plan must contain at least one check.")
    return VerificationPlan(source=source, checks=tuple(checks))


def _validate_probe(probe: Mapping[str, str]) -> None:
    probe_type = probe["type"]
    if probe_type in {"docker_container", "docker_file_sha256"}:
        if not probe.get("container_name", "").strip():
            raise ValueError(f"{probe_type} requires container_name.")
    if probe_type in {"docker_file_sha256", "file_sha256", "file_exists"}:
        path = probe.get("path", "").strip()
        if not path or not Path(path).is_absolute():
            raise ValueError(f"{probe_type} requires an absolute path.")


CommandRunner = Callable[[Sequence[str]], str]


class HostObservationRunner:
    """Run a bounded set of non-mutating host probes.

    The runner deliberately exposes no arbitrary-shell probe. Each probe is a fixed
    read operation with structured output so verification cannot become a hidden
    remediation or general remote-execution mechanism.
    """

    def __init__(self, command_runner: CommandRunner | None = None) -> None:
        self._command_runner = command_runner or _run_command

    def observe(
        self,
        *,
        check: VerificationCheck,
        source: str,
        observed_at: datetime,
        evidence_reference: str | None = None,
    ) -> Observation:
        probe_type = check.probe["type"]
        if probe_type == "docker_container":
            state = self._docker_container(check.probe)
        elif probe_type == "docker_file_sha256":
            state = self._docker_file_sha256(check.probe)
        elif probe_type == "file_sha256":
            state = self._file_sha256(check.probe)
        elif probe_type == "file_exists":
            state = self._file_exists(check.probe)
        else:  # load_verification_plan prevents this; retain fail-closed behavior.
            raise ProbeExecutionError(f"Unsupported probe type: {probe_type}")

        evidence = () if evidence_reference is None else (evidence_reference,)
        return Observation(
            registry_id=check.registry_id,
            source=f"{source}:{probe_type}",
            observed_at=observed_at,
            observed_state=state,
            evidence_references=evidence,
        )

    def _docker_container(self, probe: Mapping[str, str]) -> Mapping[str, str]:
        container_name = probe["container_name"]
        raw = self._command_runner(("docker", "inspect", container_name))
        try:
            items = json.loads(raw)
            if not isinstance(items, list) or len(items) != 1:
                raise ValueError("expected one container")
            item = items[0]
            state = item["State"]
            config = item["Config"]
            host_config = item["HostConfig"]
            network_settings = item["NetworkSettings"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ProbeExecutionError(
                f"Docker inspect returned invalid data for {container_name}."
            ) from error

        health = state.get("Health", {}).get("Status", "not-configured")
        cap_drop = ",".join(sorted(str(value) for value in host_config.get("CapDrop") or []))
        security_options = [str(value) for value in host_config.get("SecurityOpt") or []]
        no_new_privileges = any(
            value == "no-new-privileges" or value.startswith("no-new-privileges:true")
            for value in security_options
        )
        networks = ",".join(sorted(str(value) for value in (network_settings.get("Networks") or {})))
        return {
            "container_name": str(item.get("Name", "")).lstrip("/") or container_name,
            "image": str(config.get("Image", "")),
            "service_state": str(state.get("Status", "unknown")),
            "health": str(health),
            "user": str(config.get("User", "")),
            "read_only": _boolean(host_config.get("ReadonlyRootfs", False)),
            "no_new_privileges": _boolean(no_new_privileges),
            "cap_drop": cap_drop,
            "networks": networks,
        }

    def _docker_file_sha256(self, probe: Mapping[str, str]) -> Mapping[str, str]:
        container_name = probe["container_name"]
        path = probe["path"]
        raw = self._command_runner(("docker", "exec", container_name, "sha256sum", path))
        digest = raw.split(maxsplit=1)[0].strip().lower()
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ProbeExecutionError(
                f"Docker file digest was invalid for {container_name}:{path}."
            )
        return {"container_name": container_name, "path": path, "sha256": digest}

    @staticmethod
    def _file_sha256(probe: Mapping[str, str]) -> Mapping[str, str]:
        path = Path(probe["path"])
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as error:
            raise ProbeExecutionError(f"Unable to read file for digest: {path}") from error
        return {"path": str(path), "sha256": digest}

    @staticmethod
    def _file_exists(probe: Mapping[str, str]) -> Mapping[str, str]:
        path = Path(probe["path"])
        return {"path": str(path), "exists": _boolean(path.exists())}


def _run_command(arguments: Sequence[str]) -> str:
    try:
        completed = subprocess.run(
            list(arguments),
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ProbeExecutionError("Read-only host probe could not start.") from error
    if completed.returncode != 0:
        raise ProbeExecutionError(
            "Read-only host probe failed: " + " ".join(arguments[:2])
        )
    return completed.stdout.strip()


def _boolean(value: object) -> str:
    return "true" if bool(value) else "false"
