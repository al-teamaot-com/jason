from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator

from bootstrap.secret_requirements import (
    build_secret_requirements,
    evaluate_secret_readiness,
)
from bootstrap.candidate_activation import CandidateHostIdentity
from jason_runtime.deployment_identity import FileDeploymentManifestProvider


class CandidateReadinessError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CandidateReadyResult:
    schema_version: str
    instance_id: str
    deployment_identity_sha256: str
    status: str
    checks: Mapping[str, str]
    blockers: tuple[str, ...]


def _load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _validate_evidence(
    evidence: Mapping[str, Any],
    *,
    schema: Mapping[str, Any],
) -> None:
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(evidence),
        key=lambda item: list(item.absolute_path),
    )
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.absolute_path) or "<root>"
        raise CandidateReadinessError(
            f"candidate readiness evidence invalid at {location}: {first.message}"
        )


def required_unit_names(resources: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        sorted(
            Path(str(unit["source"])).name
            for unit in resources["systemd_units"]
            if bool(unit["portable"])
        )
    )


def required_network_names(resources: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        sorted(
            str(network["name"])
            for network in resources["networks"]
            if bool(network["required"])
        )
    )


def enabled_provider_ids(
    msp_configuration: Mapping[str, Any],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            str(provider_id)
            for provider_id, raw in dict(
                msp_configuration.get("providers") or {}
            ).items()
            if bool(dict(raw or {}).get("enabled"))
        )
    )


def evaluate_candidate_ready(
    *,
    target_root: str | Path,
    resources: Mapping[str, Any],
    msp_configuration: Mapping[str, Any],
    evidence: Mapping[str, Any],
    evidence_schema: Mapping[str, Any],
    candidate_identity: CandidateHostIdentity | None = None,
) -> CandidateReadyResult:
    root = Path(target_root)
    if root == Path("/"):
        if candidate_identity is None:
            raise PermissionError(
                "candidate host identity is required for live-root READY evaluation"
            )
        if (
            candidate_identity.environment != "candidate"
            or not candidate_identity.bootstrap_authorized
        ):
            raise PermissionError(
                "live-root READY evaluation requires an authorized candidate host"
            )

    _validate_evidence(evidence, schema=evidence_schema)
    manifest = FileDeploymentManifestProvider(
        root / "var/lib/jason/deployment-manifest.json"
    ).read()

    expected_identity = str(manifest["identity_sha256"])
    expected_instance = str(manifest["instance_id"])
    blockers: list[str] = []
    checks: dict[str, str] = {}

    if str(manifest.get("environment")) != "candidate":
        blockers.append("manifest_environment_not_candidate")
        checks["manifest"] = "fail"
    elif str(evidence["deployment_identity_sha256"]) != expected_identity:
        blockers.append("evidence_manifest_identity_mismatch")
        checks["manifest"] = "fail"
    elif str(evidence["instance_id"]) != expected_instance:
        blockers.append("evidence_instance_id_mismatch")
        checks["manifest"] = "fail"
    else:
        checks["manifest"] = "pass"

    if evidence["bootstrap_status"] != "ready_for_runtime_activation":
        blockers.append("bootstrap_not_ready")
        checks["bootstrap"] = "fail"
    else:
        checks["bootstrap"] = "pass"

    requirements = build_secret_requirements(msp_configuration)
    secret_status = evaluate_secret_readiness(
        requirements=requirements,
        available_references=tuple(evidence["available_secret_references"]),
    )
    if secret_status["status"] != "ready":
        blockers.extend(
            "secret_missing:" + item
            for item in secret_status["missing_references"]
        )
        checks["secrets"] = "fail"
    else:
        checks["secrets"] = "pass"

    network_evidence = dict(evidence["networks"])
    missing_networks = [
        name
        for name in required_network_names(resources)
        if network_evidence.get(name) != "present"
    ]
    if missing_networks:
        blockers.extend("network_missing:" + item for item in missing_networks)
        checks["networks"] = "fail"
    else:
        checks["networks"] = "pass"

    unit_evidence = dict(evidence["units"])
    bad_units = [
        name
        for name in required_unit_names(resources)
        if unit_evidence.get(name) != "enabled"
    ]
    if bad_units:
        blockers.extend("unit_not_enabled:" + item for item in bad_units)
        checks["units"] = "fail"
    else:
        checks["units"] = "pass"

    runtime_health = dict(evidence["runtime_health"])
    if runtime_health.get("status") != "healthy":
        blockers.append("runtime_health_not_healthy")
        checks["runtime_health"] = "fail"
    elif runtime_health.get("deployment_identity_sha256") != expected_identity:
        blockers.append("runtime_manifest_identity_mismatch")
        checks["runtime_health"] = "fail"
    else:
        checks["runtime_health"] = "pass"

    governance_health = dict(evidence["governance_health"])
    if governance_health.get("status") != "healthy":
        blockers.append("governance_health_not_healthy")
        checks["governance"] = "fail"
    else:
        checks["governance"] = "pass"

    provider_evidence = dict(evidence["providers"])
    unavailable = [
        provider_id
        for provider_id in enabled_provider_ids(msp_configuration)
        if provider_evidence.get(provider_id) != "ready"
    ]
    if unavailable:
        blockers.extend("provider_not_ready:" + item for item in unavailable)
        checks["providers"] = "fail"
    else:
        checks["providers"] = "pass"

    return CandidateReadyResult(
        schema_version="1.0",
        instance_id=expected_instance,
        deployment_identity_sha256=expected_identity,
        status="READY" if not blockers else "BLOCKED",
        checks=checks,
        blockers=tuple(blockers),
    )


def write_ready_result(
    *,
    target_root: str | Path,
    result: CandidateReadyResult,
) -> Path:
    root = Path(target_root)
    if root == Path("/"):
        raise PermissionError("candidate READY result may not target /")
    output = root / "var/lib/jason/candidate-ready.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(asdict(result), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output
