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
