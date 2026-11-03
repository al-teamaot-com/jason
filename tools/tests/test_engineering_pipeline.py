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
            "engineering_supervisor", "release_breaker_recovery_manager",
        ])
        self.assertEqual(self.state_file(), state)
        self.assertTrue(all(c["status"] == "succeeded" for c in state["stages"].values()))

    def test_stalled_work_stays_degraded_without_false_failed_controller(self):
        self.spool.mkdir(parents=True, exist_ok=True)
        (self.spool / "todo-intake-state.json").write_text(json.dumps({
            "status": "stalled_upstream_or_downstream",
            "active_development_items": 0, "active_support_repairs": 0,
            "engineering_capacity": 3,
            "downstream_commitments": {"outstanding_count": 7},
        }))
        state = self.execute()
        self.assertEqual(state["status"], "degraded")
        self.assertEqual(pipeline.service_exit_code(state), 0)

    def test_blocked_p0_support_degrades_successful_pipeline(self):
        self.spool.mkdir(parents=True, exist_ok=True)
        repo = self.base / "repo"
        repo.mkdir(parents=True, exist_ok=True)
        (repo / "SUPPORT.md").write_text(
            "| SUPPORT-OPS-054 | P0 | Open | Critical | evidence | acceptance |\n"
            "| SUPPORT-OPS-077 | P0 | Closed 2026-10-17 | Historical | evidence | acceptance |\n"
            "| SUPPORT-OPS-088 | P0 | Open stale | Historical | evidence | acceptance |\n"
            "| SUPPORT-OPS-099 | P1 | Open | Routine | evidence | acceptance |\n"
        )
        (self.spool / "state.json").write_text(json.dumps({
            "items": {"SUPPORT-OPS-054": {"phase": "blocked"},
                      "SUPPORT-OPS-077": {"phase": "blocked"},
                      "SUPPORT-OPS-088": {"phase": "blocked"},
                      "SUPPORT-OPS-099": {"phase": "blocked"}},
            "support_state_mismatches": {"support_open_issue_not_open": ["SUPPORT-OPS-088"]},
            "admission_audit": {"unadmitted_p0": []},
        }))
        state = self.execute()
        self.assertEqual(state["status"], "degraded")
        self.assertEqual(state["critical_support_blocker"]["blocked_items"], ["SUPPORT-OPS-054"])
        self.assertEqual(state["failed_or_skipped_stages"], [])
        self.assertEqual(pipeline.service_exit_code(state), 0)

    def test_unadmitted_p0_is_visible_not_silently_healthy(self):
        self.spool.mkdir(parents=True, exist_ok=True)
        repo = self.base / "repo"
        repo.mkdir(parents=True, exist_ok=True)
        (repo / "SUPPORT.md").write_text("")
        (self.spool / "state.json").write_text(json.dumps({
            "items": {}, "admission_audit": {"unadmitted_p0": ["SUPPORT-OPS-888"]},
        }))
        state = self.execute()
        self.assertEqual(state["critical_support_blocker"]["unadmitted_items"], ["SUPPORT-OPS-888"])
        self.assertEqual(state["status"], "degraded")

    def test_unavailable_authoritative_main_is_reported_unknown(self):
        self.spool.mkdir(parents=True, exist_ok=True)
        repo = self.base / "repo"
        repo.mkdir(parents=True, exist_ok=True)
        (repo / ".git").write_text("gitdir: /nonexistent/worktree")
        (repo / "SUPPORT.md").write_text("| SUPPORT-OPS-054 | P0 | Open | X | e | a |\n")
        (self.spool / "state.json").write_text(json.dumps({
            "items": {"SUPPORT-OPS-054": {"phase": "blocked"}},
            "admission_audit": {"unadmitted_p0": []},
        }))
        state = self.execute()
        self.assertEqual(state["status"], "degraded")
        self.assertEqual(state["critical_support_blocker"]["reason"], "support_health_unknown")

    def test_pending_p0_not_mistaken_for_stalled(self):
        self.spool.mkdir(parents=True, exist_ok=True)
        repo = self.base / "repo"
        repo.mkdir(parents=True, exist_ok=True)
        (repo / "SUPPORT.md").write_text(
            "| SUPPORT-OPS-054 | P0 | Open | Critical | evidence | acceptance |\n")
        (self.spool / "state.json").write_text(json.dumps({
            "items": {"SUPPORT-OPS-054": {"phase": "diagnosing"}},
            "admission_audit": {"unadmitted_p0": []},
        }))
        self.assertEqual(self.execute()["status"], "healthy")

    def test_healthy_pipeline_exits_successfully(self):
        state = self.execute()
        self.assertEqual(pipeline.service_exit_code(state), 0)

    def test_bounded_support_discovery_failure_is_isolated_from_systemd_drift(self):
        # A malformed GitHub issue listing is a work admission error.
        # Downstream admission is skipped, the independent control lane runs,
        # and the durable status remains degraded instead of falsely healthy.
        state = self.execute(failed={"support_repair_host_worker"})
        self.assertEqual(pipeline.service_exit_code(state), 0)
        self.assertEqual(state["status"], "degraded")
        self.assertEqual(state["failure_domain"], "engineering_operations")
        self.assertEqual(state["failed_work_stages"], [
            "development", "support_repair", "todo_intake"])
        self.assertEqual(state["failed_control_stages"], [])
        self.assertEqual(state["stages"]["todo_intake"]["status"], "skipped_dependency")
        self.assertEqual(self.state_file(), state)

    def test_worker_returncode_failure_stays_durable_not_a_production_breaker(self):
        for stage_name in ("todo_engineering_intake", "owner_approved_development_worker"):
            self.calls.clear()
            state = self.execute(failed={stage_name})
            self.assertEqual(pipeline.service_exit_code(state), 0)
            self.assertEqual(state["status"], "degraded")
            self.assertEqual(state["failure_domain"], "engineering_operations")
            self.assertIn("failed", [x["status"] for x in state["stages"].values()])

    def test_release_control_and_supervision_failures_still_fail_the_unit(self):
        for stage_name in ("todo_release_bridge", "engineering_supervisor",
                           "release_breaker_recovery_manager"):
            self.calls.clear()
            state = self.execute(failed={stage_name})
            self.assertEqual(pipeline.service_exit_code(state), 1)
            self.assertEqual(state["status"], "degraded")
            self.assertEqual(state["failure_domain"], "control")
            self.assertEqual(len(state["failed_control_stages"]), 1)

    def test_process_launch_and_timeout_still_hard_fail(self):
        for exception in ("launch_error", "support_repair_host_worker"):
            self.calls.clear()
            state = self.execute(exception=exception)
            self.assertEqual(pipeline.service_exit_code(state), 1)
            self.assertEqual(state["status"], "degraded")

    def test_unverified_or_tampered_pipeline_summary_cannot_claim_isolation(self):
        state = self.execute(failed={"todo_engineering_intake"})
        self.assertEqual(pipeline.service_exit_code(state), 0)
        for broken in (
            {**state, "finished_at": None},
            {**state, "status": "healthy"},
            {**state, "failed_or_skipped_stages": []},
            {**state, "stages": {**state["stages"], "ghost": {"status": "succeeded"}}},
            {**state, "stages": {}},
        ):
            self.assertEqual(pipeline.service_exit_code(broken), 1)

    def test_upstream_stall_is_degraded_even_when_all_stages_succeed(self):
        self.spool.mkdir(parents=True, exist_ok=True)
        (self.spool / "todo-intake-state.json").write_text(json.dumps({
            "status": "stalled_upstream_or_downstream",
            "active_development_items": 0,
            "active_support_repairs": 0,
            "engineering_capacity": 3,
            "downstream_commitments": {"outstanding_count": 7},
        }))
        state = self.execute()
        self.assertEqual(state["status"], "degraded")
        self.assertEqual(state["operational_blocker"]["reason"], "approved_work_stalled")
        self.assertEqual(state["failed_or_skipped_stages"], [])
        self.assertEqual(self.state_file(), state)

    def test_active_work_is_not_falsely_reported_stalled(self):
        self.spool.mkdir(parents=True, exist_ok=True)
        (self.spool / "todo-intake-state.json").write_text(json.dumps({
            "status": "stalled_upstream_or_downstream",
            "active_development_items": 1,
            "active_support_repairs": 0,
            "engineering_capacity": 2,
            "downstream_commitments": {"outstanding_count": 7},
        }))
        self.assertEqual(self.execute()["status"], "healthy")

    def test_support_failure_blocks_new_admission_but_reconciles_release(self):
        state = self.execute(failed={"support_repair_host_worker"})
        self.assertEqual([c[0] for c in self.calls], [
            "support_repair_host_worker", "todo_release_bridge",
            "engineering_supervisor", "release_breaker_recovery_manager",
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
            "engineering_supervisor", "release_breaker_recovery_manager",
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
        bridge = next(call[1] for call in self.calls if call[0] == "todo_release_bridge")
        self.assertEqual(bridge[bridge.index("--release-state")+1], str(self.base / "releases"))
        recovery = next(call[1] for call in self.calls if call[0] == "release_breaker_recovery_manager")
        self.assertEqual(recovery[recovery.index("--release-state")+1], str(self.base / "releases"))

    def test_durable_report_restricts_permissions(self):
        self.execute(failed={"todo_engineering_intake"})
        self.assertEqual(self.state_file()["status"], "degraded")
        self.assertEqual(self.spool.joinpath("engineering-pipeline-state.json").stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()


def test_signaled_work_item_process_is_not_mistaken_for_recoverable_data_failure(tmp_path):
    def terminated_runner(argv, **kwargs):
        return subprocess.CompletedProcess(argv, -9 if Path(argv[1]).name == 'support_repair_host_worker.py' else 0)

    state = pipeline.run_pipeline(
        scripts=tmp_path / 'tools', repo=tmp_path / 'repo',
        spool=tmp_path / 'spool', release_state=tmp_path / 'releases',
        runner=terminated_runner,
    )
    assert state['status'] == 'degraded'
    assert 'support_repair' in state['failed_work_stages']
    assert pipeline.service_exit_code(state) == 1
