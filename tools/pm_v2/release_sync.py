from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .store import PMV2Store


REQUIRED_RELEASE_CHECKS = (
    "release_closed",
    "teams_owner_approval",
    "exact_live_sha",
    "functional_verification",
    "ccc_post_mutation",
    "desired_state_converged",
    "documentation_closeout",
    "teams_start_delivery",
    "teams_result_delivery",
)


def _json_object(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def verify_release_evidence(
    *,
    state_root: Path,
    release_id: str,
    expected_sha: str,
) -> dict[str, dict[str, Any]]:
    record = _json_object(state_root / "records" / f"{release_id}.json")
    if not record:
        return {
            name: {"status": "unknown", "reason": "release_record_unavailable"}
            for name in REQUIRED_RELEASE_CHECKS
        }

    candidate = record.get("release_candidate") or {}
    production = record.get("production") or {}
    ccc = record.get("ccc_post_mutation_gate") or {}
    closeout = record.get("administrative_closeout") or {}
    results: dict[str, dict[str, Any]] = {}

    results["release_closed"] = {
        "status": "pass" if record.get("state") == "closed" else "fail",
        "observed_state": record.get("state"),
    }
    approval = record.get("owner_approval") or {}
    approval_source = str(approval.get("source") or "")
    teams_approved = (
        approval.get("approved") is True
        and approval.get("candidate_sha") == expected_sha
        and approval_source.startswith("authenticated_mobile_teams_owner:")
    )
    results["teams_owner_approval"] = {
        "status": "pass" if teams_approved else "fail",
        "approved": approval.get("approved"),
        "candidate_sha": approval.get("candidate_sha"),
        "source": approval_source,
    }
    exact = (
        candidate.get("candidate_sha") == expected_sha
        and production.get("live_sha") == expected_sha
        and bool(production.get("verified_at"))
    )
    results["exact_live_sha"] = {
        "status": "pass" if exact else "fail",
        "candidate_sha": candidate.get("candidate_sha"),
        "live_sha": production.get("live_sha"),
    }
    functional = (
        production.get("health_passed") is True
        and production.get("functional_smoke_tests_passed") is True
    )
    results["functional_verification"] = {
        "status": "pass" if functional else "fail",
        "health_passed": production.get("health_passed"),
        "functional_smoke_tests_passed": production.get("functional_smoke_tests_passed"),
    }
    results["ccc_post_mutation"] = {
        "status": "pass" if ccc.get("status") == "PASS" else "fail",
        "run_id": ccc.get("run_id"),
        "candidate_sha": ccc.get("candidate_sha"),
    }
    desired = (
        production.get("desired_state_converged") is True
        and production.get("production_manifest_complete") is True
    )
    results["desired_state_converged"] = {
        "status": "pass" if desired else "fail",
        "desired_state_converged": production.get("desired_state_converged"),
        "production_manifest_complete": production.get("production_manifest_complete"),
    }

    doc_status = str(production.get("documentation_reconciliation") or "")
    board_status = str(production.get("control_board_publication") or "")
    if closeout:
        doc_entry = closeout.get("documentation_control_board") or {}
        if isinstance(doc_entry, dict) and doc_entry.get("status") == "pass":
            doc_status = board_status = "pass"
    docs = doc_status == "pass" and board_status == "pass"
    results["documentation_closeout"] = {
        "status": "pass" if docs else "pending",
        "documentation_reconciliation": doc_status,
        "control_board_publication": board_status,
    }

    for check_name, event_name in (
        ("teams_start_delivery", "production_push_started"),
        ("teams_result_delivery", "production_push_result"),
    ):
        delivered = state_root / "owner-notification-delivered" / (
            f"{release_id}-{event_name}.json"
        )
        receipt = _json_object(delivered)
        is_delivered = bool(
            receipt
            and isinstance(receipt.get("message_id"), str)
            and receipt.get("message_id")
            and receipt.get("delivery_state") == "provider_message_reference_recorded"
        )
        results[check_name] = {
            "status": "pass" if is_delivered else "pending",
            "message_id": receipt.get("message_id") if receipt else None,
            "event_type": event_name,
        }
    return results


def _phase_progress(phase: str) -> int:
    return {
        "waiting_development_start": 5,
        "development_in_progress": 20,
        "waiting_development_merge": 35,
        "development_complete_unmerged": 40,
        "waiting_operational_acceptance": 45,
        "release_prepare_blocked": 45,
        "waiting_release": 60,
        "release_blocked": 60,
        "closure_validating": 90,
        "closure_blocked": 90,
        "complete": 95,
    }.get(phase, 10)


def reconcile_release_bridge(
    *,
    store: PMV2Store,
    spool: Path,
    state_root: Path,
) -> dict[str, int]:
    state = _json_object(spool / "todo-release-state.json")
    if not state or not isinstance(state.get("items"), dict):
        return {"observed": 0, "completed": 0, "blocked": 0}

    observed = completed = blocked = 0
    by_ref = {row.source_ref: row for row in store.list_assignments()}
    for todo_id, bridge in state["items"].items():
        if not isinstance(bridge, dict):
            continue
        assignment = by_ref.get(todo_id)
        if assignment is None:
            continue
        observed += 1
        phase = str(bridge.get("phase") or "unknown")
        reason = str(bridge.get("reason") or "")
        if phase == "complete":
            rid = str(bridge.get("release_id") or "")
            sha = str(bridge.get("merge_sha") or bridge.get("production_sha") or "")
            checks = verify_release_evidence(
                state_root=state_root,
                release_id=rid,
                expected_sha=sha,
            )
            for name, result in checks.items():
                store.record_validation(
                    assignment_id=assignment.assignment_id,
                    check_name=name,
                    status=str(result["status"]),
                    evidence=result,
                )
            all_pass = all(item["status"] == "pass" for item in checks.values())
            if all_pass:
                store.update_state(
                    assignment.assignment_id,
                    state="complete",
                    runnable=False,
                    completion_percent=100,
                    reason=None,
                    payload={"release_id": rid, "production_sha": sha},
                )
                completed += 1
            else:
                store.update_state(
                    assignment.assignment_id,
                    state="validation_pending",
                    runnable=False,
                    completion_percent=95,
                    reason="release_evidence_incomplete",
                    payload={"release_id": rid, "production_sha": sha},
                )
            continue

        if "blocked" in phase:
            store.update_state(
                assignment.assignment_id,
                state="blocked",
                runnable=False,
                completion_percent=max(
                    assignment.completion_percent, _phase_progress(phase)
                ),
                reason=reason or phase,
                payload={
                    "bridge_phase": phase,
                    "blocker_category": bridge.get("blocker_category"),
                    "next_action": bridge.get("next_action"),
                },
            )
            blocked += 1
            continue

        # The bridge is authoritative for downstream progress after dispatch.
        if assignment.state not in {"queued", "running", "retry_ready"}:
            store.update_state(
                assignment.assignment_id,
                state="in_progress",
                runnable=False,
                completion_percent=max(
                    assignment.completion_percent, _phase_progress(phase)
                ),
                reason=reason or None,
                payload={"bridge_phase": phase, "release_id": bridge.get("release_id")},
            )

    return {"observed": observed, "completed": completed, "blocked": blocked}
