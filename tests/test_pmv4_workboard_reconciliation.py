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
from pmv4_workboard_reconciliation import reconciled_card, assess_governed_stale_recovery, native_task_terminal_evidence

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


# A sanitized clone of the native card schema observed during an isolated
# Workboard Gateway stale-claim block; not a live production Workboard card.
STALE_NATIVE_CARD = {
    "id": "pmv4-isolated-native-workboard-uuid",
    "status": "blocked",
    "agentId": "j-dev",
    "sessionKey": "agent:j-dev:subagent:workboard-offline",
    "runId": "workboard:isolated-test:run-1",
    "execution": {
        "status": "blocked", "runId": "workboard:isolated-test:run-1",
        "sessionKey": "agent:j-dev:subagent:workboard-offline",
    },
    "metadata": {
        "failureCount": 1,
        "attempts": [{
            "id": "attempt-1", "status": "blocked",
            "runId": "workboard:isolated-test:run-1",
            "error": "Claim expired without a recent heartbeat.",
        }],
        "automation": {"maxRetries": 3},
    },
}



def native_task_for(card=STALE_NATIVE_CARD, *, status="failed"):
    # Native OpenClaw tasks-show JSON field contract; identity values are
    # synthetic and no real OpenClaw run is created in this unit test.
    return {
        "taskId": "offline-task-ledger-uuid",
        "runtime": "subagent",
        "sourceId": card["runId"],
        "runId": card["runId"],
        "childSessionKey": card["sessionKey"],
        "agentId": card["agentId"],
        "status": status,
        "startedAt": 1794398639402,
        "endedAt": 1794398728854,
    }


def interrupted_engine_state(*, idempotent=True, approved=True, approval_required=False):
    state = engine.empty_state()
    from hashlib import sha256
    work_id = "PMV4-WB-" + sha256(STALE_NATIVE_CARD["id"].encode()).hexdigest()[:16].upper()
    entry = engine.make_item(
        work_id,
        "offline_readonly_review",
        idempotent=idempotent,
        approved=approved,
        approval_required=approval_required,
        approval_request_id="preprod-scope-1" if approval_required else "",
    )
    assert engine.admit(state, entry)
    state["items"][work_id]["phase"] = "running"
    state["items"][work_id]["attempts"] = 1
    return state, work_id


def advice(card, state, **kwargs):
    return assess_governed_stale_recovery(
        card, state,
        authorized_readonly_actions=frozenset({"offline_readonly_review"}),
        native_task=kwargs.pop("native_task", native_task_for(card)),
        **kwargs,
    )


class PMV4NativeRecoveryDecisionTests(unittest.TestCase):
    def test_blocked_native_readonly_idempotent_work_can_be_reconciled_by_existing_engine(self):
        state, work_id = interrupted_engine_state()
        original_card = copy.deepcopy(STALE_NATIVE_CARD)
        before_card = copy.deepcopy(STALE_NATIVE_CARD)
        before_state = copy.deepcopy(state)
        result = advice(original_card, state)
        self.assertEqual(result["disposition"], "GOVERNED_ENGINE_CANDIDATE")
        self.assertTrue(result["governed_engine_recovery_candidate"])
        self.assertFalse(result["workboard_auto_reset_allowed"])
        self.assertFalse(result["provider_action_authorized"])
        self.assertFalse(result["operational_completion_verified"])
        self.assertEqual((original_card, state), (before_card, before_state))

        calls = []
        def handler(item, key):
            calls.append((item["id"], key))
            return engine.Outcome("complete", receipt="independently-observed-offline-result")

        # ONLY the existing work engine handles safe recovery. No Workboard mutation.
        engine.execute_cycle(state, facts={}, handler=handler, now=NOW)
        self.assertEqual(state["items"][work_id]["phase"], "complete")
        self.assertEqual(len(calls), 1)
        engine.execute_cycle(state, facts={}, handler=handler, now=NOW)
        self.assertEqual(len(calls), 1)
        self.assertEqual(reconciled_card(original_card, state)["disposition"], "RECONCILE")
        self.assertEqual(original_card, before_card)

    def test_no_implicit_action_allowlist_or_identity_authority(self):
        state, _ = interrupted_engine_state()
        result = assess_governed_stale_recovery(
            STALE_NATIVE_CARD, state,
            native_task=native_task_for(STALE_NATIVE_CARD),
        )
        self.assertEqual(result["disposition"], "HOLD")
        self.assertEqual(result["reason"], "read_only_action_not_authorized_by_runtime")

    def test_unverified_or_active_native_ledger_never_allows_recovery(self):
        state, _ = interrupted_engine_state()
        for task, expected in (
            (None, "native_openclaw_task_status_unavailable"),
            (native_task_for(status="running"), "native_agent_not_terminal_failed"),
            (native_task_for(status="queued"), "native_agent_not_terminal_failed"),
            (native_task_for(status="lost"), "native_task_lost_is_not_verified_termination"),
            ({**native_task_for(), "endedAt": None}, "native_task_terminal_timestamp_invalid"),
            ({**native_task_for(), "runId": "different-run"}, "native_task_workboard_identity_mismatch"),
            ({**native_task_for(), "sourceId": "different-source"}, "native_task_workboard_identity_mismatch"),
            ({**native_task_for(), "childSessionKey": "another-session"}, "native_task_workboard_identity_mismatch"),
            ({**native_task_for(), "agentId": "j-qa"}, "native_task_workboard_identity_mismatch"),
            ({**native_task_for(), "runtime": "cron"}, "native_task_workboard_identity_mismatch"),
        ):
            result = assess_governed_stale_recovery(
                STALE_NATIVE_CARD, state,
                authorized_readonly_actions=frozenset({"offline_readonly_review"}),
                native_task=task,
            )
            self.assertEqual(result["disposition"], "HOLD")
            self.assertEqual(result["reason"], expected)

    def test_native_task_succeeded_requires_readback_instead_of_replay(self):
        state, _ = interrupted_engine_state()
        task=native_task_for(status="succeeded")
        observed=native_task_terminal_evidence(STALE_NATIVE_CARD,task)
        self.assertEqual(observed["disposition"],"RECONCILE")
        self.assertTrue(observed["native_termination_confirmed"])
        self.assertFalse(observed["independent_operational_completion_verified"])
        result=assess_governed_stale_recovery(
            STALE_NATIVE_CARD,state,
            authorized_readonly_actions=frozenset({"offline_readonly_review"}),
            native_task=task,
        )
        self.assertEqual(result["disposition"],"RECONCILE")
        self.assertEqual(result["reason"],"native_agent_succeeded_but_workboard_blocked")
        self.assertFalse(result["governed_engine_recovery_candidate"])

    def test_native_terminal_failures_are_candidates_only_not_automatic_execution(self):
        state, _ = interrupted_engine_state()
        for status in ("failed", "timed_out", "cancelled"):
            task=native_task_for(status=status)
            native=native_task_terminal_evidence(STALE_NATIVE_CARD,task)
            self.assertEqual(native["disposition"],"TERMINATED")
            self.assertFalse(native["independent_operational_completion_verified"])
            decision=assess_governed_stale_recovery(
                STALE_NATIVE_CARD,state,
                authorized_readonly_actions=frozenset({"offline_readonly_review"}),
                native_task=task,
            )
            self.assertEqual(decision["disposition"],"GOVERNED_ENGINE_CANDIDATE")
            self.assertFalse(decision["workboard_auto_reset_allowed"])
            self.assertFalse(decision["provider_action_authorized"])
            self.assertEqual(decision["native_terminal_task_id"],task["taskId"])

    def test_active_claim_cannot_replay_even_with_readonly_action(self):
        state, _ = interrupted_engine_state()
        card = copy.deepcopy(STALE_NATIVE_CARD)
        card["metadata"]["claim"] = {"token": "still-claimed"}
        result = advice(card, state)
        self.assertEqual(result["disposition"], "HOLD")
        self.assertEqual(result["reason"], "workboard_claim_still_present")

    def test_only_native_stale_block_with_consistent_run_identity_qualifies(self):
        state, _ = interrupted_engine_state()
        for update, reason in (
            ({"status": "running"}, "workboard_not_blocked"),
            ({"execution": {"status": "running", "runId": STALE_NATIVE_CARD["runId"],
                             "sessionKey": STALE_NATIVE_CARD["sessionKey"]}}, "workboard_execution_not_blocked"),
            ({"runId": "different-run"}, "native_worker_linkage_mismatch"),
        ):
            card = {**STALE_NATIVE_CARD, **update}
            self.assertEqual(advice(card, state)["reason"], reason)
        card = copy.deepcopy(STALE_NATIVE_CARD)
        card["metadata"]["attempts"][-1]["error"] = "Owner approval required"
        self.assertEqual(advice(card, state)["reason"], "non_stale_failure_requires_review")
        card["metadata"]["attempts"][-1]["error"] = "Claim expired without a recent heartbeat."
        card["metadata"]["attempts"][-1]["runId"] = "unrelated-run"
        self.assertEqual(advice(card, state)["reason"], "native_attempt_not_stale_blocked_run")

    def test_nonidempotent_unapproved_and_approval_required_work_never_qualifies(self):
        for override, expected in (
            ({"idempotent": False}, "non_idempotent_action_must_be_reconciled"),
            ({"approved": False}, "existing_engine_authority_not_satisfied"),
            ({"approval_required": True}, "existing_engine_authority_not_satisfied"),
        ):
            state, item_id = interrupted_engine_state()
            state["items"][item_id].update(override)
            r = advice(STALE_NATIVE_CARD, state)
            self.assertEqual(r["disposition"], "HOLD")
            self.assertEqual(r["reason"], expected)

    def test_exhausted_budgets_and_unreconciled_receipts_never_replay(self):
        state, item_id = interrupted_engine_state()
        state["items"][item_id]["attempts"] = state["items"][item_id]["max_attempts"]
        self.assertEqual(advice(STALE_NATIVE_CARD, state)["reason"],
                         "existing_engine_retry_budget_exhausted")
        state["items"][item_id]["attempts"] = 1
        card = copy.deepcopy(STALE_NATIVE_CARD)
        card["metadata"]["automation"]["maxRetries"] = 1
        self.assertEqual(advice(card, state)["reason"], "native_retry_budget_exhausted")
        action_key = engine.action_key(item_id, state["items"][item_id]["action"], 1)
        state["receipts"][action_key] = {"item_id": item_id, "receipt": "existing-receipt"}
        r = advice(STALE_NATIVE_CARD, state)
        self.assertEqual(r["disposition"], "RECONCILE")
        self.assertEqual(r["reason"], "existing_durable_receipt_requires_readback_not_replay")
        self.assertFalse(r["governed_engine_recovery_candidate"])

    def test_untrusted_agent_unknown_item_and_unrelated_scope_are_held(self):
        state, item_id = interrupted_engine_state()
        card = {**STALE_NATIVE_CARD, "agentId": "j-root"}
        self.assertEqual(advice(card, state)["reason"], "agent_not_allowlisted")
        empty = engine.empty_state()
        self.assertEqual(advice(STALE_NATIVE_CARD, empty)["reason"], "existing_work_engine_record_absent")
        state["items"][item_id]["action"] = "live_provider_write"
        self.assertEqual(advice(STALE_NATIVE_CARD, state)["reason"],
                         "read_only_action_not_authorized_by_runtime")

    def test_approved_stale_readonly_work_resumes_once_across_fresh_processes(self):
        """Old engine persists work, new process assesses and resumes, third does not replay."""
        import os
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory(prefix="pmv4-offline-native-") as td:
            from pathlib import Path
            state_path = Path(td) / "engine.json"
            card_path = Path(td) / "native.json"
            run_log = Path(td) / "offline-readonly-calls.txt"
            state, work_id = interrupted_engine_state()
            engine.atomic_write(state_path, state)
            card_path.write_text(json.dumps(STALE_NATIVE_CARD))
            script = """
import json,sys
from pathlib import Path
import pmv3_work_engine as engine
from pmv4_workboard_reconciliation import assess_governed_stale_recovery
step,engine_file,card_file,log_file=sys.argv[1:]
state=engine.load_state(Path(engine_file))
card=json.loads(Path(card_file).read_text())
decision=assess_governed_stale_recovery(
    card, state,
    authorized_readonly_actions=frozenset({"offline_readonly_review"}),
    native_task={
        "taskId":"isolated-ledger-task","runtime":"subagent",
        "sourceId":card["runId"],"runId":card["runId"],
        "childSessionKey":card["sessionKey"],"agentId":card["agentId"],
        "status":"failed","startedAt":1794398639402,"endedAt":1794398728854,
    },
)
if step == "recover":
    assert decision["disposition"] == "GOVERNED_ENGINE_CANDIDATE",decision
    def handler(item,key):
        with Path(log_file).open("a") as f: f.write(key+"\\n")
        return engine.Outcome("complete",receipt="offline-readonly-result-1")
    engine.execute_cycle(state,facts={},handler=handler,checkpoint=lambda s:engine.atomic_write(Path(engine_file),s))
    engine.atomic_write(Path(engine_file),state)
else:
    assert decision["disposition"] != "GOVERNED_ENGINE_CANDIDATE",decision
    def handler(item,key):
        raise AssertionError("unapproved duplicate action execution")
    engine.execute_cycle(state,facts={},handler=handler)
    engine.atomic_write(Path(engine_file),state)
"""
            env={**os.environ, "PYTHONPATH":str(ROOT/"tools")}
            for step in ("recover","repeat"):
                completed=subprocess.run(
                    [sys.executable,"-c",script,step,str(state_path),str(card_path),str(run_log)],
                    text=True,capture_output=True,timeout=10,env=env,
                )
                self.assertEqual(completed.returncode,0,completed.stderr)
            recovered=engine.load_state(state_path)
            self.assertEqual(recovered["items"][work_id]["phase"],"complete")
            self.assertEqual(len(run_log.read_text().splitlines()),1)
            self.assertEqual(len(recovered["receipts"]),1)
            self.assertEqual(json.loads(card_path.read_text()),STALE_NATIVE_CARD)

    def test_unapproved_nonidempotent_stale_work_does_not_recover_in_separate_process(self):
        import os
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory(prefix="pmv4-no-replay-") as td:
            from pathlib import Path
            state_path=Path(td)/"engine.json"
            card_path=Path(td)/"native.json"
            state,_=interrupted_engine_state(idempotent=False)
            engine.atomic_write(state_path,state)
            card_path.write_text(json.dumps(STALE_NATIVE_CARD))
            script="""
import json,sys
from pathlib import Path
import pmv3_work_engine as engine
from pmv4_workboard_reconciliation import assess_governed_stale_recovery
state=engine.load_state(Path(sys.argv[1]))
card=json.loads(Path(sys.argv[2]).read_text())
decision=assess_governed_stale_recovery(
    card,state,authorized_readonly_actions=frozenset({"offline_readonly_review"}),
    native_task={
        "taskId":"isolated-ledger-task","runtime":"subagent",
        "sourceId":card["runId"],"runId":card["runId"],
        "childSessionKey":card["sessionKey"],"agentId":card["agentId"],
        "status":"failed","startedAt":1794398639402,"endedAt":1794398728854,
    },
)
assert decision["disposition"]=="HOLD",decision
assert decision["reason"]=="non_idempotent_action_must_be_reconciled",decision
def handler(item,key):
    raise AssertionError("indeterminate nonidempotent item must not execute")
engine.execute_cycle(state,facts={},handler=handler)
assert all(x["phase"]=="waiting" for x in state["items"].values()),state
"""
            result=subprocess.run([sys.executable,"-c",script,str(state_path),str(card_path)],
                                  env={**os.environ,"PYTHONPATH":str(ROOT/"tools")},
                                  capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_cannot_mutate_runtime_or_grant_authority_by_assessment(self):
        state, _ = interrupted_engine_state()
        card = copy.deepcopy(STALE_NATIVE_CARD)
        before_state, before_card = copy.deepcopy(state), copy.deepcopy(card)
        for _ in range(3):
            self.assertTrue(advice(card, state)["governed_engine_recovery_candidate"])
        self.assertEqual(state, before_state)
        self.assertEqual(card, before_card)


if __name__=="__main__":
    unittest.main()
