from pathlib import Path
import json
import tempfile
import time
import unittest

from pm_v2.config import load_config
from pm_v2.scheduler import Scheduler
from pm_v2.store import PMV2Store


def reap_until_states(scheduler, store, expected_states, timeout_seconds=5.0):
    """Wait for real worker completion instead of assuming 100ms process startup.

    CI executors may queue subprocesses longer than an arbitrary sleep; this
    helper neither dispatches additional work nor changes scheduler semantics.
    """
    deadline = time.monotonic() + timeout_seconds
    while True:
        scheduler.reap()
        rows = store.list_assignments()
        if rows and {row.state for row in rows} == set(expected_states):
            return rows
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"worker completion timeout: expected={expected_states}, "
                f"actual={[(row.assignment_id,row.state) for row in rows]}"
            )
        time.sleep(0.025)


def dispatch_until_count(scheduler, expected_count, timeout_seconds=5.0):
    """Wait for independently timed retry delays without changing scheduler semantics."""
    deadline = time.monotonic() + timeout_seconds
    total = 0
    while total < expected_count:
        total += scheduler.dispatch_available()
        if total >= expected_count:
            return total
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"dispatch timeout: expected={expected_count}, actual={total}"
            )
        time.sleep(0.025)
    return total


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
                started = time.monotonic()
                self.assertEqual(scheduler.dispatch_available(), 2)
                time.sleep(0.25)
                results = scheduler.reap()
                elapsed = time.monotonic() - started
                self.assertEqual(len(results), 2)
                self.assertLess(elapsed, 0.6)
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
                rows = reap_until_states(scheduler, store, {"validation_ready"})
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0].completion_percent, 50)
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
                reap_until_states(scheduler, store, {"retry_ready"})
                self.assertEqual(dispatch_until_count(scheduler, 2), 2)
                rows = reap_until_states(scheduler, store, {"blocked"})
                self.assertTrue(all(r.attempt_count == 2 for r in rows))
            finally:
                scheduler.shutdown()
