from __future__ import annotations
import copy
import json
from pathlib import Path
import sys
import unittest
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"tools"))
import pmv3_work_engine as engine
from pmv4_workboard_reconciliation import reconciled_card

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
CARD={"id":"workboard-staged-uuid-001","status":"ready","agentId":"j-dev",
      "metadata":{"proof":[]}}

def state_with_card(*,idempotent=True):
    state=engine.empty_state()
    from hashlib import sha256
    item_id="PMV4-WB-"+sha256(CARD["id"].encode()).hexdigest()[:16].upper()
    engine.admit(state,engine.make_item(item_id,"offline_review",idempotent=idempotent))
    return state,item_id


class WorkboardReconciliationTests(unittest.TestCase):
    def test_only_existing_engine_owns_job_lifecycle(self):
        state,item_id=state_with_card()
        result=reconciled_card(CARD,state)
        self.assertEqual(result["disposition"],"IN_PROGRESS")
        self.assertEqual(result["work_item_id"],item_id)
        self.assertFalse(result["eligible_for_automated_retry"])
        self.assertFalse(result["operational_completion_verified"])
        self.assertEqual(state["items"][item_id]["phase"],"runnable")

    def test_missing_engine_record_cannot_auto_execute(self):
        result=reconciled_card(CARD,engine.empty_state())
        self.assertEqual(result["disposition"],"NOT_ADMITTED")
        self.assertFalse(result["eligible_for_automated_retry"])

    def test_untrusted_agent_is_rejected(self):
        altered={**CARD,"agentId":"j-release-root"}
        result=reconciled_card(altered,engine.empty_state())
        self.assertEqual(result["disposition"],"BLOCKED")
        self.assertEqual(result["reason"],"agent_not_allowlisted")

    def test_workboard_done_without_engine_receipt_never_verified(self):
        state,item_id=state_with_card()
        card={**CARD,"status":"done"}
        result=reconciled_card(card,state)
        self.assertEqual(result["disposition"],"RECONCILE")
        self.assertFalse(result["operational_completion_verified"])

    def test_durable_receipt_plus_card_proof_still_requires_independent_acceptance(self):
        state,item_id=state_with_card()
        key=engine.action_key(item_id,"offline_review",1)
        state["items"][item_id]["phase"]="complete"
        state["receipts"][key]={"item_id":item_id,"receipt":"readback-receipt"}
        card={**CARD,"status":"done","metadata":{"proof":[
            {"id":"proof-1","status":"passed","note":"offline test only"}]}}
        result=reconciled_card(card,state)
        self.assertEqual(result["disposition"],"REVIEW")
        self.assertFalse(result["operational_completion_verified"])
        state["receipts"].clear()
        result=reconciled_card(card,state)
        self.assertEqual(result["disposition"],"BLOCKED")
        self.assertEqual(result["reason"],"work_item_complete_without_durable_receipt")

    def test_nonidempotent_unknown_must_wait_for_reconciliation(self):
        state,item_id=state_with_card(idempotent=False)
        state["items"][item_id]["phase"]="running"
        engine.execute_cycle(state,facts={},handler=lambda *_: (_ for _ in ()).throw(AssertionError("unsafe retry")),now=NOW)
        result=reconciled_card(CARD,state)
        self.assertEqual(result["disposition"],"WAITING")
        self.assertEqual(result["reason"],"indeterminate_execution_requires_reconciliation")
        self.assertFalse(result["eligible_for_automated_retry"])

    def test_pure_reconciliation_does_not_mutate_sources(self):
        state,item_id=state_with_card()
        before=copy.deepcopy(state),copy.deepcopy(CARD)
        for _ in range(3):
            reconciled_card(CARD,state)
        self.assertEqual((state,CARD),before)


if __name__=="__main__":
    unittest.main()
