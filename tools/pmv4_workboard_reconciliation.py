#!/usr/bin/env python3
"""Read-only Workboard -> existing PMV3 work-engine reconciliation contract.

Source/preproduction prototype ONLY. Does not mutate Workboard, launch an agent,
issue approvals, or own another scheduler. Receipts and Workboard cards stay
in their respective canonical stores. All uncertainty fails closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

VALID_CARD = frozenset(("triage", "backlog", "todo", "scheduled", "ready",
                        "running", "review", "blocked", "done"))
VALID_WORK = frozenset(("runnable", "running", "verifying", "waiting",
                        "retry_wait", "blocked", "failed_external", "complete"))
WORKER_AGENTS = frozenset(("j-dev", "j-docs", "j-qa", "j-compliance",
                            "j-integrations", "j-observe", "j-release"))


def proof_reference(card: Mapping[str, Any]) -> bool:
    """Proof is a reference, not an independent acceptance certificate."""
    metadata = card.get("metadata")
    if not isinstance(metadata, Mapping):
        return False
    proofs = metadata.get("proof")
    if not isinstance(proofs, list):
        return False
    return any(isinstance(p, Mapping) and p.get("status") == "passed"
               and isinstance(p.get("id"), str) and bool(p["id"].strip())
               and (p.get("url") or p.get("note") or p.get("command"))
               for p in proofs)


def reconciled_card(card: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    """Classify disposition for a known card + existing work item, no side effects."""
    card_id = card.get("id")
    card_status = card.get("status")
    agent_id = card.get("agentId")
    result = {"card_id": card_id if isinstance(card_id, str) else None,
              "disposition": "BLOCKED",
              "reason": "invalid_or_untrusted_card",
              "eligible_for_automated_retry": False,
              "operational_completion_verified": False}
    if not isinstance(card_id, str) or not card_id or card_status not in VALID_CARD:
        return result
    if agent_id not in WORKER_AGENTS:
        result["reason"] = "agent_not_allowlisted"
        return result
    existing = state.get("items", {})
    if not isinstance(existing, Mapping):
        result["reason"] = "work_inventory_unavailable"
        return result
    work_id = "PMV4-WB-" + hashlib.sha256(card_id.encode()).hexdigest()[:16].upper()
    result["work_item_id"] = work_id
    item = existing.get(work_id)
    if not isinstance(item, Mapping):
        result["disposition"] = "NOT_ADMITTED"
        result["reason"] = "existing_work_engine_record_absent"
        return result
    phase = item.get("phase")
    if phase not in VALID_WORK or not isinstance(item.get("action"), str):
        result["reason"] = "invalid_existing_work_record"
        return result
    if phase == "complete":
        # Existing engine's durable receipt is necessary, not sufficient
        # for independent end-to-end operational proof.
        import pmv3_work_engine as engine
        try:
            key = engine.action_key(work_id, item["action"], int(item.get("generation") or 1))
        except (ValueError, TypeError):
            result["reason"] = "invalid_work_generation"
            return result
        receipts = state.get("receipts", {})
        receipt = receipts.get(key) if isinstance(receipts, Mapping) else None
        if not isinstance(receipt, Mapping) or receipt.get("item_id") != work_id or not receipt.get("receipt"):
            result["reason"] = "work_item_complete_without_durable_receipt"
            return result
        if card_status != "done":
            result["disposition"] = "RECONCILE"
            result["reason"] = "engine_complete_but_workboard_not_done"
            return result
        if not proof_reference(card):
            result["disposition"] = "RECONCILE"
            result["reason"] = "workboard_done_without_proof"
            return result
        result["disposition"] = "REVIEW"
        result["reason"] = "dual_completion_records_present_independent_acceptance_required"
        # Never claim complete purely from two self-reported state stores.
        return result
    if card_status == "done":
        result["disposition"] = "RECONCILE"
        result["reason"] = "workboard_done_engine_not_complete"
        return result
    if phase in {"running", "verifying", "retry_wait", "runnable"}:
        result["disposition"] = "IN_PROGRESS"
        result["reason"] = "existing_engine_owns_lifecycle"
        return result
    if phase == "waiting":
        result["disposition"] = "WAITING"
        result["reason"] = str(item.get("reason") or "dependency_unverified")[:120]
        return result
    result["reason"] = "engine_blocked_or_external_dependency"
    return result


def assess_governed_stale_recovery(
    card: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    authorized_readonly_actions: frozenset[str] = frozenset(),
    worker_termination_verified: bool = False,
    termination_evidence_id: str = "",
) -> dict[str, Any]:
    """Pure, fail-closed advice for existing PMV3 worker; never resumes Workboard.

    Caller MUST obtain termination evidence through a trusted runtime observer
    and supply an already-authorized read-only action allowlist. Neither a
    Workboard card nor a local caller flag confers provider or Owner authority.
    """
    import pmv3_work_engine as engine

    result: dict[str, Any] = {
        "disposition": "HOLD",
        "reason": "unverified_stale_work",
        "governed_engine_recovery_candidate": False,
        "workboard_auto_reset_allowed": False,
        "provider_action_authorized": False,
        "operational_completion_verified": False,
    }

    preliminary = reconciled_card(card, state)
    if preliminary["disposition"] in ("BLOCKED", "NOT_ADMITTED"):
        result["reason"] = str(preliminary["reason"])
        return result
    if card.get("status") != "blocked":
        result["reason"] = "workboard_not_blocked"
        return result

    meta = card.get("metadata")
    execution = card.get("execution")
    if not isinstance(meta, Mapping) or not isinstance(execution, Mapping):
        result["reason"] = "missing_native_workboard_execution"
        return result
    if meta.get("claim"):
        result["reason"] = "workboard_claim_still_present"
        return result
    if execution.get("status") != "blocked":
        result["reason"] = "workboard_execution_not_blocked"
        return result
    run_id = card.get("runId")
    session_key = card.get("sessionKey")
    if not isinstance(run_id, str) or not run_id or not isinstance(session_key, str) or not session_key:
        result["reason"] = "native_worker_linkage_missing"
        return result
    if execution.get("runId") != run_id or execution.get("sessionKey") != session_key:
        result["reason"] = "native_worker_linkage_mismatch"
        return result

    attempts = meta.get("attempts")
    if not isinstance(attempts, list) or not attempts or not isinstance(attempts[-1], Mapping):
        result["reason"] = "native_attempt_history_missing"
        return result
    latest = attempts[-1]
    if latest.get("status") != "blocked" or latest.get("runId") != run_id:
        result["reason"] = "native_attempt_not_stale_blocked_run"
        return result
    if latest.get("error") not in (
        "Claim expired without a recent heartbeat.",
        "Run exceeded the card max runtime.",
    ):
        result["reason"] = "non_stale_failure_requires_review"
        return result

    failure_count = meta.get("failureCount", 0)
    automation = meta.get("automation")
    max_retries = automation.get("maxRetries") if isinstance(automation, Mapping) else None
    if not isinstance(failure_count, int) or isinstance(failure_count, bool) or failure_count < 1:
        result["reason"] = "invalid_native_failure_count"
        return result
    if max_retries is not None:
        if not isinstance(max_retries, int) or isinstance(max_retries, bool) or max_retries < 1:
            result["reason"] = "invalid_native_retry_budget"
            return result
        if failure_count >= max_retries:
            result["reason"] = "native_retry_budget_exhausted"
            return result

    item_id = preliminary.get("work_item_id")
    item = state.get("items", {}).get(item_id)
    if not isinstance(item, Mapping):
        result["reason"] = "missing_existing_work_item"
        return result
    action = item.get("action")
    if not isinstance(action, str) or action not in authorized_readonly_actions:
        result["reason"] = "read_only_action_not_authorized_by_runtime"
        return result
    if item.get("approved") is not True or not engine.approval_satisfied(item):
        result["reason"] = "existing_engine_authority_not_satisfied"
        return result
    if item.get("idempotent") is not True:
        result["reason"] = "non_idempotent_action_must_be_reconciled"
        return result
    if item.get("phase") not in engine.ACTIVE:
        result["reason"] = "work_engine_not_interrupted_active"
        return result
    attempts_count = item.get("attempts")
    max_attempts = item.get("max_attempts")
    if (
        not isinstance(attempts_count, int) or isinstance(attempts_count, bool)
        or not isinstance(max_attempts, int) or isinstance(max_attempts, bool)
        or max_attempts <= 0 or attempts_count >= max_attempts
    ):
        result["reason"] = "existing_engine_retry_budget_exhausted"
        return result

    try:
        key = engine.action_key(str(item_id), action, int(item["generation"]))
    except (ValueError, TypeError, KeyError):
        result["reason"] = "invalid_work_action_generation"
        return result
    receipts = state.get("receipts")
    if not isinstance(receipts, Mapping):
        result["reason"] = "work_engine_receipts_unavailable"
        return result
    if key in receipts:
        result["disposition"] = "RECONCILE"
        result["reason"] = "existing_durable_receipt_requires_readback_not_replay"
        return result

    if worker_termination_verified is not True or not isinstance(termination_evidence_id, str) or not termination_evidence_id.strip():
        result["reason"] = "independent_worker_termination_not_verified"
        return result

    result.update({
        "disposition": "GOVERNED_ENGINE_CANDIDATE",
        "reason": "idempotent_readonly_task_may_be_recovered_by_existing_governed_worker",
        "work_item_id": item_id,
        "action_key": key,
        "termination_evidence_id": termination_evidence_id.strip(),
        "governed_engine_recovery_candidate": True,
    })
    # Candidate is NOT authority to reset the Workboard card or automatically
    # call a provider. Real adapter must re-read native claim and authority
    # immediately before a governed recovery through the existing worker.
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workboard-card", type=Path, required=True,
                        help="offline sanitized Workboard JSON card")
    parser.add_argument("--pmv3-state", type=Path, required=True,
                        help="offline disposable PMV3 state JSON")
    args = parser.parse_args()
    try:
        card = json.loads(args.workboard_card.read_text())
        state = json.loads(args.pmv3_state.read_text())
        if not isinstance(card, dict) or not isinstance(state, dict):
            raise ValueError("expected JSON objects")
        result = reconciled_card(card, state)
    except (OSError, ValueError, TypeError):
        result = {"disposition": "BLOCKED", "reason": "invalid_or_unavailable_offline_evidence",
                  "eligible_for_automated_retry": False,
                  "operational_completion_verified": False}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["disposition"] in {"IN_PROGRESS", "WAITING", "REVIEW", "RECONCILE", "NOT_ADMITTED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
