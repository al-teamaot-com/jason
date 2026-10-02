from __future__ import annotations

import json
from pathlib import Path
import subprocess
import time
from typing import Any, Callable, Mapping, Sequence

from bootstrap.candidate_ready import (
    enabled_provider_ids,
    required_network_names,
    required_unit_names,
)
from bootstrap.secret_requirements import load_secret_presence_attestation
from jason_runtime.deployment_identity import FileDeploymentManifestProvider


class CandidateEvidenceError(ValueError):
    pass


Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]
HttpGetter = Callable[[str], tuple[int, Mapping[str, Any]]]


def _default_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        text=True,
        capture_output=True,
        check=False,
    )


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CandidateEvidenceError(f"required evidence file missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CandidateEvidenceError(f"evidence file is invalid JSON: {path}") from exc
    if not isinstance(payload, Mapping):
        raise CandidateEvidenceError(f"evidence file must contain an object: {path}")
    return payload


def _classify_units(
    *,
    unit_names: Sequence[str],
    runner: Runner,
) -> dict[str, str]:
    result: dict[str, str] = {}
    for unit in unit_names:
        completed = runner(("systemctl", "is-enabled", unit))
        output = ((completed.stdout or "") + "\n" + (completed.stderr or "")).lower()
        if completed.returncode == 0 and "enabled" in output:
            result[unit] = "enabled"
        elif "not-found" in output or "not found" in output or "no such file" in output:
            result[unit] = "missing"
        elif "failed" in output:
            result[unit] = "failed"
        else:
            result[unit] = "disabled"
    return result


def _classify_networks(
    *,
    network_names: Sequence[str],
    runner: Runner,
) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in network_names:
        completed = runner(("docker", "network", "inspect", name))
        result[name] = "present" if completed.returncode == 0 else "missing"
    return result


def _governance_health(
    path: Path,
    *,
    now_epoch: float,
    max_age_seconds: float,
) -> str:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return "unavailable"
    if now_epoch - stat.st_mtime > max_age_seconds:
        return "unavailable"
    report = _read_json(path)
    return "healthy" if report.get("status") == "pass" else "unhealthy"


def _provider_health(
    *,
    path: Path,
    enabled_providers: Sequence[str],
    now_epoch: float,
    max_age_seconds: float,
) -> dict[str, str]:
    result = {provider: "unavailable" for provider in enabled_providers}
    try:
        report = _read_json(path)
    except CandidateEvidenceError:
        return result

    generated = report.get("generated_at_epoch")
    if isinstance(generated, bool) or not isinstance(generated, (int, float)):
        return result
    if now_epoch - float(generated) > max_age_seconds:
        return result

    grouped: dict[str, list[bool]] = {}
    for item in report.get("results", ()):
        if not isinstance(item, Mapping):
            continue
        provider = str(item.get("provider") or "")
        if provider not in result:
            continue
        healthy = item.get("healthy")
        if isinstance(healthy, bool):
            grouped.setdefault(provider, []).append(healthy)

    for provider in result:
        checks = grouped.get(provider, [])
        if checks and all(checks):
            result[provider] = "ready"
        elif checks:
            result[provider] = "degraded"
    return result


def collect_candidate_readiness_evidence(
    *,
    target_root: str | Path,
    resources: Mapping[str, Any],
    msp_configuration: Mapping[str, Any],
    secret_presence_attestation_path: str | Path,
    runtime_health_url: str,
    runner: Runner,
    http_getter: HttpGetter,
    now_epoch: float | None = None,
    governance_max_age_seconds: float = 900,
    provider_max_age_seconds: float = 900,
) -> dict[str, Any]:
    root = Path(target_root)
    if root == Path("/"):
        # Collection on an actual candidate host is allowed; this function is read-only.
        pass
    elif not root.is_absolute():
        raise CandidateEvidenceError("target_root must be absolute")

    manifest = FileDeploymentManifestProvider(
        root / "var/lib/jason/deployment-manifest.json"
    ).read()
    bootstrap = _read_json(
        root / "var/lib/jason/candidate-bootstrap-result.json"
    )

    available_references = load_secret_presence_attestation(
        secret_presence_attestation_path
    )
    network_names = required_network_names(resources)
    unit_names = required_unit_names(resources)
    providers = enabled_provider_ids(msp_configuration)

    code, health_payload = http_getter(runtime_health_url)
    if code == 200 and health_payload.get("status") == "ok":
        runtime_status = "healthy"
        runtime_identity = health_payload.get("deployment_identity_sha256")
    elif code <= 0:
        runtime_status = "unavailable"
        runtime_identity = None
    else:
        runtime_status = "unhealthy"
        runtime_identity = health_payload.get("deployment_identity_sha256")

    current = float(time.time() if now_epoch is None else now_epoch)
    governance_status = _governance_health(
        root / "var/lib/jason/openclaw/operational-health.json",
        now_epoch=current,
        max_age_seconds=governance_max_age_seconds,
    )
    provider_status = _provider_health(
        path=root / "var/lib/jason/provider-health-canaries.json",
        enabled_providers=providers,
        now_epoch=current,
        max_age_seconds=provider_max_age_seconds,
    )

    return {
        "schema_version": "1.0",
        "instance_id": str(manifest["instance_id"]),
        "deployment_identity_sha256": str(manifest["identity_sha256"]),
        "bootstrap_status": str(
            dict(bootstrap.get("readiness") or {}).get("status") or "blocked"
        ),
        "available_secret_references": list(available_references),
        "networks": _classify_networks(
            network_names=network_names,
            runner=runner,
        ),
        "units": _classify_units(
            unit_names=unit_names,
            runner=runner,
        ),
        "runtime_health": {
            "status": runtime_status,
            "deployment_identity_sha256": runtime_identity,
        },
        "governance_health": {"status": governance_status},
        "providers": provider_status,
    }
