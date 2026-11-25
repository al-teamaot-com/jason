"""Reuse the existing durable Windows Time shadow evidence/audit projection.

This is a pure read-only classification persistence adapter, not an endpoint,
ticket or alert provider mutation. It projects only a fully verified
JSON-interpreter decision into the existing legacy-compatible state table.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from typing import Mapping

from autonomous_remediation.json_shadow_integration import (
    JsonShadowBoundaryError, JsonShadowResult,
)
from .windows_time_source_shadow import (
    TimeSourceDecision, SQLiteWindowsTimeSourceShadowState,
)


TERMINAL_CLASSIFICATIONS = {
    "classified_current": "CURRENT_TIME_SOURCE_MISMATCH",
    "classified_recurring": "RECURRING_FAILURE",
    "classified_waiting": "WAITING_DEVICE_ACCESS",
}


def project_windows_time_json_decision(
    *,
    result: JsonShadowResult,
    state: SQLiteWindowsTimeSourceShadowState,
    at: datetime,
    audit=None,
) -> bool | None:
    """Persist exact verified read-only source classification and audit.

    Returns None when the JSON decision is not a classifiable current alert.
    Returns False for unchanged evidence; True for a newly observed change.
    Does not mark an entire scheduled sweep complete: the existing durable
    cadence state is advanced by the separately governed sweep coordinator.
    """
    if not isinstance(at, datetime) or at.tzinfo is None:
        raise JsonShadowBoundaryError("TIME_SOURCE_PROJECTION_AWARE_CLOCK_REQUIRED")
    expected_classification = TERMINAL_CLASSIFICATIONS.get(result.step_id)
    if result.status != "completed_readonly" or not expected_classification:
        return None
    facts = result.facts
    if facts.get("classification") != expected_classification:
        raise JsonShadowBoundaryError("TIME_SOURCE_PROJECTION_CLASSIFICATION_CHANGED")
    if facts.get("verified_site_client_binding") is not True:
        raise JsonShadowBoundaryError("TIME_SOURCE_PROJECTION_CLIENT_SCOPE_MISSING")
    if facts.get("endpoint_identity_verified") is not True:
        raise JsonShadowBoundaryError("TIME_SOURCE_PROJECTION_DEVICE_IDENTITY_MISSING")
    if not any(
        step.get("result") == "governed_read_normalized"
        for step in result.history
    ):
        raise JsonShadowBoundaryError("TIME_SOURCE_PROJECTION_NO_GOVERNED_READ")
    required = (
        "alert_uid", "device_uid", "hostname", "site", "observed_source",
        "approved_sources", "recurrence_count", "classification_reason",
        "decision_fingerprint",
    )
    if any(key not in facts for key in required):
        raise JsonShadowBoundaryError("TIME_SOURCE_PROJECTION_EVIDENCE_INCOMPLETE")
    approved = facts["approved_sources"]
    if (not isinstance(approved, list) or not approved or
        any(not isinstance(x, str) or not x.strip() for x in approved)):
        raise JsonShadowBoundaryError("TIME_SOURCE_PROJECTION_APPROVED_SET_INVALID")
    try:
        count = int(facts["recurrence_count"])
    except (ValueError, TypeError) as exc:
        raise JsonShadowBoundaryError("TIME_SOURCE_PROJECTION_RECURRENCE_INVALID") from exc
    if count < 0:
        raise JsonShadowBoundaryError("TIME_SOURCE_PROJECTION_RECURRENCE_INVALID")
    if (expected_classification == "WAITING_DEVICE_ACCESS" and (
        count != 0 or facts.get("device_online") is True
    )):
        raise JsonShadowBoundaryError("TIME_SOURCE_PROJECTION_WAITING_CONTRADICTORY")
    if expected_classification == "RECURRING_FAILURE" and count < 3:
        raise JsonShadowBoundaryError("TIME_SOURCE_PROJECTION_RECURRENCE_CONTRADICTORY")
    if expected_classification == "CURRENT_TIME_SOURCE_MISMATCH" and (
        count not in {1, 2} or facts.get("device_online") is not True
    ):
        raise JsonShadowBoundaryError("TIME_SOURCE_PROJECTION_CURRENT_CONTRADICTORY")
    material = {
        "alert_uid": str(facts["alert_uid"]),
        "device_uid": str(facts["device_uid"]),
        "hostname": str(facts["hostname"]),
        "site": str(facts["site"]),
        "observed_source": str(facts["observed_source"]),
        "approved_sources": tuple(approved),
        "recurrence_count": count,
        "classification": expected_classification,
        "reason": str(facts["classification_reason"]),
    }
    if not all(str(material[key]).strip() for key in (
        "alert_uid", "device_uid", "hostname", "site", "observed_source", "reason"
    )):
        raise JsonShadowBoundaryError("TIME_SOURCE_PROJECTION_IDENTITY_INCOMPLETE")
    fingerprint = sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if fingerprint != str(facts["decision_fingerprint"]):
        raise JsonShadowBoundaryError("TIME_SOURCE_PROJECTION_FINGERPRINT_MISMATCH")

    decision = TimeSourceDecision(
        alert_uid=material["alert_uid"],
        device_uid=material["device_uid"],
        hostname=material["hostname"],
        site=material["site"],
        observed_source=material["observed_source"],
        approved_sources=tuple(approved),
        recurrence_count=count,
        classification=expected_classification,
        reason=material["reason"],
        fingerprint=fingerprint,
    )
    changed = state.put(decision, when=at)
    if audit is not None:
        audit.record(
            "autonomy.windows_time_source_shadow",
            {
                "alert_uid": decision.alert_uid,
                "device_uid": decision.device_uid,
                "hostname": decision.hostname,
                "site": decision.site,
                "observed_source": decision.observed_source,
                "approved_sources": list(decision.approved_sources),
                "recurrence_count": decision.recurrence_count,
                "classification": decision.classification,
                "reason": decision.reason,
                "changed": changed,
                "mutated": False,
            },
        )
    return changed
