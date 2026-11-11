"""Offline fail-closed tests; mock only the native read subprocess."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from pmv4_native_task_observer import observe_native_task

RUN = "f3fe9ae8-4742-464e-ab60-148a6e8a4cd2"
CARD = {
    "runId": RUN,
    "sessionKey": "agent:j-dev:subagent:d082bea8-d13f-44c9-9d26-2c3eabde62cb",
    "agentId": "j-dev",
}
TASK = {
    "taskId": "task-id-native",
    "runtime": "subagent",
    "sourceId": RUN,
    "runId": RUN,
    "childSessionKey": CARD["sessionKey"],
    "agentId": "j-dev",
    "status": "failed",
    "startedAt": 1794398639402,
    "endedAt": 1794398728854,
}


class ObserverTests(unittest.TestCase):
    def fake(self, task=TASK, rc=0):
        def runner(argv, **kw):
            self.assertEqual(argv, ["/usr/local/bin/openclaw", "tasks", "show", RUN, "--json"])
            self.assertFalse(kw["shell"])
            self.assertTrue(kw["capture_output"])
            self.assertTrue(kw["text"])
            self.assertLessEqual(kw["timeout"], 30)
            return subprocess.CompletedProcess(argv, rc, json.dumps(task), "")
        return runner

    def test_terminal_failure_reports_evidence_only(self):
        before = copy.deepcopy(CARD)
        r = observe_native_task(CARD, runner=self.fake())
        self.assertEqual(r["disposition"], "TERMINATED")
        self.assertTrue(r["native_termination_confirmed"])
        self.assertFalse(r["provider_action_authorized"])
        self.assertFalse(r["independent_operational_completion_verified"])
        self.assertEqual(CARD, before)

    def test_succeeded_is_reconcile_never_retry(self):
        r = observe_native_task(CARD, runner=self.fake({**TASK, "status": "succeeded"}))
        self.assertEqual(r["disposition"], "RECONCILE")
        self.assertFalse(r["provider_action_authorized"])

    def test_missing_mismatch_active_lost_rejected(self):
        for modified in (
            {**TASK, "status": "running"},
            {**TASK, "status": "lost"},
            {**TASK, "endedAt": None},
            {**TASK, "sourceId": "unrelated"},
            {**TASK, "agentId": "j-root"},
        ):
            with self.subTest(modified=modified):
                self.assertEqual(observe_native_task(CARD, runner=self.fake(modified))["disposition"], "HOLD")

    def test_command_injection_and_ambiguous_identifiers_are_rejected_before_exec(self):
        for value in ("--help", "", "abc;touch /tmp/foo", RUN + " --help", "../"+RUN, " " + RUN, None):
            bad = {**CARD, "runId": value}
            self.assertEqual(observe_native_task(bad, runner=lambda *_args, **_kw: self.fail("executed"))["disposition"], "HOLD")

    def test_cli_path_must_be_absolute_and_pinned(self):
        for path in ("openclaw", "/tmp/../bin/openclaw", "/tmp/evil", "/usr/local/bin//openclaw"):
            self.assertEqual(
                observe_native_task(CARD, cli=path, runner=lambda *_args, **_kw: self.fail("executed"))["disposition"],
                "HOLD",
            )

    def test_errors_fail_closed(self):
        for failure in (OSError("missing"), subprocess.TimeoutExpired("openclaw", 10), ValueError("bad")):
            def runner(*args, **kwargs):
                raise failure
            self.assertEqual(observe_native_task(CARD, runner=runner)["reason"], "native_task_query_failed")
        self.assertEqual(observe_native_task(CARD, runner=self.fake(rc=1))["disposition"], "HOLD")

    def test_json_safety(self):
        for raw in ("not-json", "null", "[]", "{" + "x" * (128 * 1024) + "}"):
            def runner(argv, **kw):
                return subprocess.CompletedProcess(argv, 0, raw, "")
            self.assertEqual(observe_native_task(CARD, runner=runner)["reason"], "native_task_response_invalid")

    def test_no_direct_execution_or_workboard_mutation(self):
        import inspect
        from pmv4_native_task_observer import observe_native_task as observed
        source = inspect.getsource(observed)
        self.assertNotIn("execute_cycle(", source)
        self.assertNotIn("subprocess.Popen(", source)
        self.assertNotIn("workboard update", source)


if __name__ == "__main__":
    unittest.main()
