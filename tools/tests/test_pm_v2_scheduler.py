from pathlib import Path
import json
import tempfile
import time
import unittest

from pm_v2.config import load_config
from pm_v2.scheduler import Scheduler
from pm_v2.store import PMV2Store


def reap_until(scheduler, expected: int, timeout: float = 2.0):
    results = []
    deadline = time.monotonic() + timeout
    while len(results) < expected and time.monotonic() < deadline:
        results.extend(scheduler.reap())
        if len(results) < expected:
            time.sleep(0.02)
    return results


def dispatch_until(scheduler, expected: int, timeout: float = 2.5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        count = scheduler.dispatch_available()
        if count == expected:
            return count
        time.sleep(0.02)
    return scheduler.dispatch_available()


class PMV2SchedulerTests(unittest.TestCase):
    def _config(self, root: Path, command=None):
        (root / "roadmap.md").write_text("", encoding="utf-8")
        (root / "SUPPORT.md").write_text("", encoding="utf-8")
        cfg = {
            "schema_version": "1.0",
            "instance_id": "test",
            "poll_interval_seconds": 1,
            "lease_seconds": 10,
            "max_concurrent_jobs": 2,
            "max_concurrent_components": 1,
            "components": {},
            "state": {"database_path": str(root / "state.sqlite3")},
            "sources": {"roadmap_path": "roadmap.md", "support_path": "SUPPORT.md"},
            "workers": {
                "development": {
                    "enabled": True,
                    "max_concurrency": 2,
                    "max_attempts": 2,
                    "retry_delay_seconds": 1,
                    "timeout_seconds": 5,
                    "command": command or ["python3", "-c", "import time; time.sleep(0.1)"]
                }
            },
            "paths": {"legacy_spool": "/tmp/legacy", "release_state": "/tmp/release"},
            "recovery": {
                "snapshot_directory": str(root / "snapshot"),
                "snapshot_interval_seconds": 300
            },
            "ownership": {"owned_todo_ids": []},
            "control": {
                "status_snapshot_path": str(root / "control" / "status.json"),
                "request_inbox": str(root / "control" / "requests"),
                "result_directory": str(root / "control" / "results")
            },
            "communications": {
                "required_status_fields": [
                    "Status","Completed","Still required",
                    "What I'm doing next","What you need to do"
                ],
                "approval_channel": "microsoft_teams"
            }
        }
        p = root / "config.json"
        p.write_text(json.dumps(cfg), encoding="utf-8")
        return load_config(p, repo=root)

    def _add(self, store, n):
        store.upsert_assignment(
            assignment_id=f"a{n}", source="test", source_ref=str(n),
            title=f"job {n}", priority=1, work_type="development",
            runnable=True, scope_hash=f"sha256:{n}", metadata={},
        )

    def test_independent_work_dispatches_in_parallel(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = self._config(root)
            store = PMV2Store(config.database_path)
            store.initialize()
            self._add(store, 1)
            self._add(store, 2)
            scheduler = Scheduler(config=config, store=store, repo=root)
            try:
                self.assertEqual(scheduler.dispatch_available(), 2)
                self.assertEqual(len(scheduler._running), 2)
                results = reap_until(scheduler, 2)
                self.assertEqual(len(results), 2)
                states = {r.state for r in store.list_assignments()}
                self.assertEqual(states, {"validation_ready"})
            finally:
                scheduler.shutdown()

    def test_worker_success_does_not_claim_assignment_complete(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = self._config(root, ["python3", "-c", "pass"])
            store = PMV2Store(config.database_path)
            store.initialize()
            self._add(store, 1)
            scheduler = Scheduler(config=config, store=store, repo=root)
            try:
                self.assertEqual(scheduler.dispatch_available(), 1)
                results = reap_until(scheduler, 1)
                self.assertEqual(len(results), 1)
                row = store.list_assignments()[0]
                self.assertEqual(row.state, "validation_ready")
                self.assertEqual(row.completion_percent, 50)
            finally:
                scheduler.shutdown()


class PMV2BoundedRetryTests(unittest.TestCase):
    def test_repeated_worker_failure_blocks_only_that_assignment(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "roadmap.md").write_text("", encoding="utf-8")
            (root / "SUPPORT.md").write_text("", encoding="utf-8")
            cfg = {
                "schema_version": "1.0",
                "instance_id": "test",
                "poll_interval_seconds": 1,
                "lease_seconds": 10,
                "max_concurrent_jobs": 2,
            "max_concurrent_components": 1,
            "components": {},
                "state": {"database_path": str(root / "state.sqlite3")},
                "sources": {"roadmap_path": "roadmap.md", "support_path": "SUPPORT.md"},
                "workers": {
                    "development": {
                        "enabled": True, "max_concurrency": 2,
                        "max_attempts": 2, "retry_delay_seconds": 1,
                        "command": ["python3", "-c", "raise SystemExit(7)"]
                    }
                },
                "paths": {"legacy_spool": "/tmp/legacy", "release_state": "/tmp/release"},
                "recovery": {
                    "snapshot_directory": str(root / "snapshot"),
                    "snapshot_interval_seconds": 300
                },
                "ownership": {"owned_todo_ids": []},
                "control": {
                    "status_snapshot_path": str(root / "control" / "status.json"),
                    "request_inbox": str(root / "control" / "requests"),
                    "result_directory": str(root / "control" / "results")
                },
                "communications": {
                    "required_status_fields": [
                        "Status","Completed","Still required",
                        "What I'm doing next","What you need to do"
                    ],
                    "approval_channel": "microsoft_teams"
                }
            }
            path = root / "config.json"
            path.write_text(json.dumps(cfg), encoding="utf-8")
            config = load_config(path, repo=root)
            store = PMV2Store(config.database_path)
            store.initialize()
            for n in (1, 2):
                store.upsert_assignment(
                    assignment_id=f"a{n}", source="test", source_ref=str(n),
                    title=f"job {n}", priority=n, work_type="development",
                    runnable=True, scope_hash=f"sha256:{n}", metadata={},
                )
            scheduler = Scheduler(config=config, store=store, repo=root)
            try:
                self.assertEqual(scheduler.dispatch_available(), 2)
                self.assertEqual(len(reap_until(scheduler, 2)), 2)
                self.assertEqual({r.state for r in store.list_assignments()},
                                 {"retry_ready"})
                self.assertEqual(dispatch_until(scheduler, 2), 2)
                self.assertEqual(len(reap_until(scheduler, 2)), 2)
                rows = store.list_assignments()
                self.assertTrue(all(r.state == "blocked" for r in rows))
                self.assertTrue(all(r.attempt_count == 2 for r in rows))
            finally:
                scheduler.shutdown()
