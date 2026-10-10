import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("engineering_pipeline", ROOT / "tools/engineering_pipeline.py")
pipeline = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = pipeline
spec.loader.exec_module(pipeline)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.spool = self.base / "state"
        self.calls = []

    def execute(self, failed=(), exception=None):
        def runner(argv, **kwargs):
            stage = Path(argv[1]).stem
            self.calls.append((stage, list(argv), kwargs))
            if stage == exception:
                raise subprocess.TimeoutExpired(argv, 900)
            if exception == "launch_error" and stage == "support_repair_host_worker":
                raise OSError("simulated interpreter failure")
            return subprocess.CompletedProcess(argv, 1 if stage in failed else 0)
        return pipeline.run_pipeline(
            scripts=self.base / "tools", repo=self.base / "repo",
            spool=self.spool, release_state=self.base / "releases", runner=runner
        )

    def state_file(self):
        return json.loads((self.spool / "engineering-pipeline-state.json").read_text())

    def test_all_stages_run_in_order_and_are_healthy(self):
        state = self.execute()
        self.assertEqual(state["status"], "healthy")
        self.assertEqual([c[0] for c in self.calls], [
            "support_repair_host_worker", "todo_engineering_intake",
            "owner_approved_development_worker", "todo_release_bridge",
        ])
        self.assertEqual(self.state_file(), state)
        self.assertTrue(all(c["status"] == "succeeded" for c in state["stages"].values()))

    def test_support_failure_blocks_new_admission_but_reconciles_release(self):
        state = self.execute(failed={"support_repair_host_worker"})
        self.assertEqual([c[0] for c in self.calls], [
            "support_repair_host_worker", "todo_release_bridge",
        ])
        self.assertEqual(state["status"], "degraded")
        self.assertEqual(state["stages"]["todo_intake"]["status"], "skipped_dependency")
        self.assertEqual(state["stages"]["development"]["status"], "skipped_dependency")
        self.assertEqual(state["stages"]["release_bridge"]["status"], "succeeded")
        self.assertEqual(self.state_file(), state)

    def test_todo_intake_failure_does_not_stop_preapproved_development(self):
        state = self.execute(failed={"todo_engineering_intake"})
        self.assertEqual([c[0] for c in self.calls], [
            "support_repair_host_worker", "todo_engineering_intake",
            "owner_approved_development_worker", "todo_release_bridge",
        ])
        self.assertEqual(state["status"], "degraded")
        self.assertEqual(state["stages"]["development"]["status"], "succeeded")

    def test_development_failure_does_not_stop_release_reconciliation(self):
        state = self.execute(failed={"owner_approved_development_worker"})
        self.assertEqual(state["status"], "degraded")
        self.assertEqual(state["stages"]["release_bridge"]["status"], "succeeded")

    def test_timeout_is_recorded_and_independent_stage_continues(self):
        state = self.execute(exception="support_repair_host_worker")
        self.assertEqual(state["stages"]["support_repair"]["reason"], "stage_timeout")
        self.assertEqual(state["stages"]["release_bridge"]["status"], "succeeded")
        self.assertNotIn("todo_engineering_intake", [c[0] for c in self.calls])

    def test_launch_error_does_not_bypass_support_gate_or_suppress_bridge(self):
        state = self.execute(exception="launch_error")
        self.assertEqual(state["stages"]["support_repair"]["reason"], "stage_process_launch_failed")
        self.assertEqual(state["stages"]["todo_intake"]["status"], "skipped_dependency")
        self.assertEqual(state["stages"]["release_bridge"]["status"], "succeeded")

    def test_release_bridge_receives_authoritative_release_state(self):
        self.execute()
        bridge = self.calls[-1][1]
        self.assertEqual(bridge[bridge.index("--release-state")+1], str(self.base / "releases"))

    def test_durable_report_restricts_permissions(self):
        self.execute(failed={"todo_engineering_intake"})
        self.assertEqual(self.state_file()["status"], "degraded")
        self.assertEqual(self.spool.joinpath("engineering-pipeline-state.json").stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
