from pathlib import Path
import json
import tempfile
import time
import unittest

from pm_v2.components import ComponentRunner
from pm_v2.config import load_config
from pm_v2.store import PMV2Store


def reap_until(runner, expected: int, timeout: float = 2.0):
    results = []
    deadline = time.monotonic() + timeout
    while len(results) < expected and time.monotonic() < deadline:
        results.extend(runner.reap())
        if len(results) < expected:
            time.sleep(0.02)
    return results


def dispatch_until(runner, expected: int, timeout: float = 2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        count = runner.dispatch_due()
        if count == expected:
            return count
        time.sleep(0.02)
    return runner.dispatch_due()


class PMV2ComponentRunnerTests(unittest.TestCase):
    def _config(self, root: Path, components):
        (root / "roadmap.md").write_text("", encoding="utf-8")
        (root / "SUPPORT.md").write_text("", encoding="utf-8")
        path = root / "config.json"
        path.write_text(json.dumps({
            "schema_version": "1.0",
            "instance_id": "node-a",
            "poll_interval_seconds": 1,
            "lease_seconds": 10,
            "max_concurrent_jobs": 1,
            "max_concurrent_components": 2,
            "state": {"database_path": str(root / "state.sqlite3")},
            "sources": {"roadmap_path": "roadmap.md", "support_path": "SUPPORT.md"},
            "workers": {},
            "components": components,
            "paths": {"legacy_spool": str(root / "legacy"),
                      "release_state": str(root / "release")},
            "recovery": {"snapshot_directory": str(root / "snapshot"),
                         "snapshot_interval_seconds": 60},
            "ownership": {"owned_todo_ids": []},
            "control": {
                "status_snapshot_path": str(root / "control" / "status.json"),
                "request_inbox": str(root / "control" / "requests"),
                "result_directory": str(root / "control" / "results")
            },
            "communications": {
                "required_status_fields": [
                    "Status", "Completed", "Still required",
                    "What I'm doing next", "What you need to do"
                ],
                "approval_channel": "microsoft_teams"
            }
        }), encoding="utf-8")
        return load_config(path, repo=root)

    @staticmethod
    def _component(owner, command):
        return {
            "owner": owner,
            "interval_seconds": 60,
            "timeout_seconds": 5,
            "max_attempts": 2,
            "retry_delay_seconds": 1,
            "blocked_recheck_seconds": 30,
            "command": command,
        }

    def test_v1_owned_component_is_observed_not_executed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            marker = root / "should-not-exist"
            config = self._config(root, {
                "external": self._component(
                    "v1", ["python3", "-c",
                           f"from pathlib import Path; Path({str(marker)!r}).touch()"]
                )
            })
            store = PMV2Store(config.database_path)
            store.initialize()
            runner = ComponentRunner(config=config, store=store, repo=root)
            try:
                self.assertEqual(runner.dispatch_due(), 0)
                self.assertFalse(marker.exists())
                state = store.component_snapshot()[0]
                self.assertEqual(state["owner"], "v1")
                self.assertEqual(state["state"], "external_v1")
            finally:
                runner.shutdown()

    def test_two_pm_v2_components_run_independently_in_parallel(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            component = self._component(
                "pm_v2",
                ["python3", "-c", "import time; time.sleep(0.1)"]
            )
            config = self._config(root, {"a": component, "b": component})
            store = PMV2Store(config.database_path)
            store.initialize()
            runner = ComponentRunner(config=config, store=store, repo=root)
            try:
                self.assertEqual(runner.dispatch_due(), 2)
                self.assertEqual(len(runner._running), 2)
                results = reap_until(runner, 2)
                self.assertEqual(len(results), 2)
                self.assertTrue(all(r.state == "healthy_wait" for r in results))
            finally:
                runner.shutdown()

    def test_repeated_component_failure_enters_slow_recheck_not_tight_loop(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            component = self._component(
                "pm_v2", ["python3", "-c", "raise SystemExit(9)"]
            )
            config = self._config(root, {"bad": component})
            store = PMV2Store(config.database_path)
            store.initialize()
            runner = ComponentRunner(config=config, store=store, repo=root)
            try:
                self.assertEqual(runner.dispatch_due(), 1)
                first = reap_until(runner, 1)
                self.assertEqual(len(first), 1)
                self.assertEqual(first[0].state, "retry_wait")
                self.assertEqual(dispatch_until(runner, 1), 1)
                second = reap_until(runner, 1)
                self.assertEqual(len(second), 1)
                self.assertEqual(second[0].state, "blocked_recheck")
                self.assertEqual(runner.dispatch_due(), 0)
                state = store.component_snapshot()[0]
                self.assertEqual(state["consecutive_failures"], 2)
            finally:
                runner.shutdown()
