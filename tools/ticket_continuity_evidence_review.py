#!/usr/bin/env python3
"""Non-authorizing ticket continuity evidence preflight for PMV3 migration.

Checks integrity and completeness of externally obtained governed ticket readback,
controlled test action, and two postchange observations. Receipt strings alone
never constitute proof of provider identity or owner authority; the native
Release Manager must independently verify protected provider-backed evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from isolated_service_live_sources import bounded_json
    from isolated_service_common import atomic_json, now_iso
except ModuleNotFoundError:
    from tools.isolated_service_live_sources import bounded_json
    from tools.isolated_service_common import atomic_json, now_iso

SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
REQUIRED_SURFACES = frozenset({
    "ticket_intake", "queue_assignment", "ticket_read", "ticket_notes",
    "controlled_ticket_update", "worker_claim_idempotency", "alert_ticket_routing",
    "technician_notification",
})


def aware(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return instant.astimezone(timezone.utc) if instant.tzinfo else None


def evaluate(evidence: dict[str, Any], *, now: datetime | None = None,
             min_cycle_gap_seconds: int = 60, max_age_seconds: int = 3600) -> dict[str, Any]:
    """Return blocked or evidence_review_required; never production-approved."""
    at = now or datetime.now(timezone.utc)
    faults: list[str] = []
    if at.tzinfo is None:
        raise ValueError("now must be timezone aware")
    if evidence.get("schema_version") != "1.0":
        faults.append("schema_version_invalid")
    candidate = evidence.get("candidate_sha")
    rollback = evidence.get("rollback_sha")
    if not isinstance(candidate, str) or not SHA.fullmatch(candidate):
        faults.append("candidate_sha_missing_or_invalid")
    if not isinstance(rollback, str) or not SHA.fullmatch(rollback):
        faults.append("rollback_sha_missing_or_invalid")
    if candidate == rollback:
        faults.append("candidate_and_rollback_must_differ")
    ticket = evidence.get("controlled_test_ticket")
    ticket_id = ticket.get("ticket_id") if isinstance(ticket, dict) else None
    company_id = ticket.get("company_id") if isinstance(ticket, dict) else None
    if (type(ticket_id) is not int or ticket_id < 1 or
            type(company_id) is not int or company_id < 1 or
            not ticket.get("test_company") is True):
        faults.append("controlled_test_ticket_identity_not_verified")
    base = evidence.get("baseline")
    if not isinstance(base, dict):
        faults.append("ticket_baseline_missing")
        base = {}
    baseline_at = aware(base.get("observed_at"))
    if baseline_at is None or baseline_at > at or (at - baseline_at).total_seconds() > max_age_seconds:
        faults.append("ticket_baseline_stale_or_invalid")
    if base.get("runtime_healthy") is not True or base.get("mcp_read_available") is not True:
        faults.append("baseline_runtime_or_mcp_unhealthy")
    if base.get("ticket_id") != ticket_id or base.get("company_id") != company_id:
        faults.append("baseline_ticket_identity_mismatch")
    for key in ("queue_id", "status_id", "notes_count"):
        if type(base.get(key)) is not int or base[key] < 0:
            faults.append("baseline_" + key + "_invalid")
    action = evidence.get("governed_test_action")
    if not isinstance(action, dict):
        action = {}
    if (action.get("ticket_id") != ticket_id or action.get("company_id") != company_id or
            action.get("candidate_sha") != candidate or
            action.get("provider") != "autotask" or
            action.get("status") != "readback_verified"):
        faults.append("controlled_action_identity_or_readback_unverified")
    if action.get("field") not in {"status", "priority", "queue"} or action.get("field") == "dueDateTime":
        faults.append("controlled_action_field_not_reversible")
    if (action.get("before_value") is None or action.get("requested_value") is None or
            action.get("readback_value") != action.get("requested_value") or
            action.get("before_value") == action.get("requested_value")):
        faults.append("controlled_action_value_mismatch")
    for key in ("owner_approval_evidence_sha256", "governed_write_receipt_sha256", "governed_readback_receipt_sha256"):
        value = action.get(key)
        if not isinstance(value, str) or not DIGEST.fullmatch(value):
            faults.append("action_" + key + "_invalid")
    if (not isinstance(action.get("write_correlation_id"), str) or
            not action["write_correlation_id"].strip()):
        faults.append("controlled_action_write_correlation_missing")
    observed = evidence.get("postchange_observations")
    if not isinstance(observed, list) or len(observed) < 2:
        faults.append("two_postchange_observations_required")
        observed = []
    instants: list[datetime] = []
    for i, row in enumerate(observed):
        if not isinstance(row, dict):
            faults.append(f"observation_{i}_invalid")
            continue
        instant = aware(row.get("observed_at"))
        if (instant is None or instant > at or
                (at - instant).total_seconds() > max_age_seconds or
                (baseline_at is not None and instant <= baseline_at)):
            faults.append(f"observation_{i}_stale_or_out_of_order")
        else:
            instants.append(instant)
        if (row.get("ticket_id") != ticket_id or row.get("company_id") != company_id or
                row.get("runtime_healthy") is not True or row.get("mcp_read_available") is not True):
            faults.append(f"observation_{i}_ticket_or_runtime_failed")
        if type(row.get("notes_count")) is not int or (type(base.get("notes_count")) is int and row["notes_count"] < base["notes_count"]):
            faults.append(f"observation_{i}_notes_regressed")
        if type(row.get("duplicate_claims")) is not int or row["duplicate_claims"] != 0:
            faults.append(f"observation_{i}_duplicate_claims_detected")
        if type(row.get("lost_intake_items")) is not int or row["lost_intake_items"] != 0:
            faults.append(f"observation_{i}_lost_ticket_intake_detected")
        if row.get("governed_readback_verified") is not True:
            faults.append(f"observation_{i}_governed_readback_missing")
        surfaces = row.get("verified_surfaces")
        if not isinstance(surfaces, dict) or set(surfaces) != REQUIRED_SURFACES or any(v is not True for v in surfaces.values()):
            faults.append(f"observation_{i}_required_ticket_surfaces_not_verified")
        receipt_digest = row.get("evidence_sha256")
        if not isinstance(receipt_digest, str) or not DIGEST.fullmatch(receipt_digest):
            faults.append(f"observation_{i}_evidence_digest_missing")
    if len(instants) == len(observed) and len(instants) >= 2:
        ordered = sorted(instants)
        if len(set(instants)) != len(instants) or any((b-a).total_seconds() < min_cycle_gap_seconds for a,b in zip(ordered, ordered[1:])):
            faults.append("observation_cycles_not_independent")
    if evidence.get("source_mutation_performed_by_shadow_services") is not False:
        faults.append("shadow_services_mutation_boundary_unverified")
    # Do not expose source/customer ticket data in the conclusion. Fingerprint
    # the evaluated record for independent native release verification instead.
    fingerprint = hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "schema_version": "1.0", "service": "ticket_continuity_evidence_review",
        "status": "blocked" if faults else "evidence_review_required",
        "reason_codes": sorted(set(faults)), "source_sha256": "sha256:" + fingerprint,
        "candidate_sha": candidate if isinstance(candidate, str) and SHA.fullmatch(candidate) else None,
        "tested_surface_count": len(REQUIRED_SURFACES),
        "cycle_count": len(instants), "advisory_only": True,
        "production_authority": False, "native_provider_reverification_required": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, _ = bounded_json(args.input)
    result = {"observed_at": now_iso(), **evaluate(source)}
    atomic_json(args.output, result)
    print(result["status"])
    return 0 if result["status"] == "evidence_review_required" else 2


if __name__ == "__main__":
    raise SystemExit(main())
