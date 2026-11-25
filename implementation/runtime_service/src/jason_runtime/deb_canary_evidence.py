"""Strict reduction of the reviewed DEB read-only component's governed output.

No execution, provider access, approval, ticket completion or secret retention.
Only the existing orchestrator may supply these invocation-bound receipts and
the server-owned expected job/device/component selectors. Caller assertions
are not evidence. This reducer alone does not wire a production JSON runner.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping


class DebCanaryEvidenceError(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DebCanaryEvidenceError("DEB_CANARY_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _evidence(receipt: Mapping[str, Any], capability: str) -> Mapping[str, Any]:
    if (not isinstance(receipt, Mapping) or receipt.get("status") != "succeeded"
            or receipt.get("capability") != capability
            or not receipt.get("correlation_id")):
        raise DebCanaryEvidenceError("DEB_CANARY_GOVERNED_READ_UNVERIFIED")
    evidence = receipt.get("evidence")
    if not isinstance(evidence, Mapping) or evidence.get("provider") != "datto_rmm":
        raise DebCanaryEvidenceError("DEB_CANARY_PROVIDER_CHANGED")
    if evidence.get("warnings"):
        raise DebCanaryEvidenceError("DEB_CANARY_READ_WARNING")
    data = evidence.get("data")
    if not isinstance(data, Mapping) or data.get("discovery_complete") is not True:
        raise DebCanaryEvidenceError("DEB_CANARY_INCOMPLETE_READ")
    return data


def reduce_deb_canary(*, job_uid: str, device_uid: str, component_uid: str,
                      job_receipt: Mapping[str, Any],
                      stdout_receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    """Produce narrow observations only, after independent job/output reads.

The expected component identity/file hashes and same-company device binding
must already be established by existing server governance. The RMM catalog
metadata fingerprint is not an immutable script hash; neither this reducer
nor a successful read-only canary can establish standing execution authority.
"""
    if not all(isinstance(v, str) and v.strip() for v in (job_uid, device_uid, component_uid)):
        raise DebCanaryEvidenceError("DEB_CANARY_EXACT_SELECTORS_REQUIRED")
    job_data = _evidence(job_receipt, "automation.job.read")
    job = job_data.get("job")
    if not isinstance(job, Mapping) or job.get("resource_id") != job_uid:
        raise DebCanaryEvidenceError("DEB_CANARY_JOB_CHANGED")
    if str(job.get("status", "")).casefold() != "completed":
        raise DebCanaryEvidenceError("DEB_CANARY_JOB_NOT_TERMINAL")
    data = _evidence(stdout_receipt, "automation.job.output.read")
    expected = {"resource_id": job_uid, "device_uid": device_uid,
                "component_uid": component_uid, "stream": "stdout"}
    if any(data.get(k) != v for k, v in expected.items()):
        raise DebCanaryEvidenceError("DEB_CANARY_OUTPUT_SCOPE_CHANGED")
    outputs = data.get("outputs")
    if (not isinstance(outputs, list) or len(outputs) != 1
            or data.get("match_count") != 1 or data.get("output_bounded") is not False):
        raise DebCanaryEvidenceError("DEB_CANARY_OUTPUT_NOT_UNIQUE_OR_COMPLETE")
    output = outputs[0]
    if (not isinstance(output, Mapping) or output.get("component_uid") != component_uid
            or output.get("stream") != "stdout" or output.get("truncated") is not False):
        raise DebCanaryEvidenceError("DEB_CANARY_OUTPUT_RECORD_CHANGED")
    text = output.get("text")
    if not isinstance(text, str) or len(text) > 65536:
        raise DebCanaryEvidenceError("DEB_CANARY_OUTPUT_INVALID")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != 1:
        raise DebCanaryEvidenceError("DEB_CANARY_JSON_NOT_UNIQUE")
    try:
        record = json.loads(lines[0], object_pairs_hook=_unique_object)
    except (ValueError, TypeError) as exc:
        raise DebCanaryEvidenceError("DEB_CANARY_JSON_INVALID") from exc
    if not isinstance(record, dict):
        raise DebCanaryEvidenceError("DEB_CANARY_JSON_NOT_OBJECT")
    keys = {"mode", "source_state", "service_state", "original_registration_verified",
            "changed", "installer_executed", "backup_started", "production_acceptance_complete"}
    if set(record) != keys or record["mode"] != "native_readonly_canary":
        raise DebCanaryEvidenceError("DEB_CANARY_OUTPUT_SCHEMA_CHANGED")
    if any(record[k] is not False for k in (
        "changed", "installer_executed", "backup_started", "production_acceptance_complete")):
        raise DebCanaryEvidenceError("DEB_CANARY_READONLY_BOUNDARY_CHANGED")
    source, service = record["source_state"], record["service_state"]
    if not isinstance(source, str) or source not in {"AlreadyMatched", "WouldCreate"}:
        raise DebCanaryEvidenceError("DEB_CANARY_SOURCE_RESULT_UNRECOGNIZED")
    if not isinstance(service, str) or service not in {"RunningOriginalPairing", "WouldStartService"}:
        raise DebCanaryEvidenceError("DEB_CANARY_SERVICE_RESULT_UNRECOGNIZED")
    paired = service == "RunningOriginalPairing"
    if record["original_registration_verified"] is not paired:
        raise DebCanaryEvidenceError("DEB_CANARY_PAIRING_RESULT_CONTRADICTORY")
    facts = {
        "native_source_and_registration_verified": paired,
        "source_alias_missing": source == "WouldCreate",
        "existing_agent_stopped": service == "WouldStartService",
        "source_alias_state": source,
        "agent_service_state": service,
        "job_uid": job_uid,
        "provider_mutation_allowed": False,
        "production_acceptance_complete": False,
    }
    facts["native_canary_evidence_sha256"] = sha256(json.dumps(
        facts, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return facts
