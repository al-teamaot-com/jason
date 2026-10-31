from pathlib import Path
import json
import tempfile
import time
import unittest

from pm_v2.config import load_config
from pm_v2.scheduler import Scheduler
from pm_v2.store import PMV2Store


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
            "state": {"database_path": str(root / "state.sqlite3")},
            "sources": {"roadmap_path": "roadmap.md", "support_path": "SUPPORT.md"},
            "workers": {
                "development": {
                    "enabled": True,
                    "max_concurrency": 2,
                    "command": command or ["python3", "-c", "import time; time.sleep(0.1)"]
                }
            },
            "paths": {"legacy_spool": "/tmp/legacy", "release_state": "/tmp/release"},
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
                time.sleep(0.1)
                scheduler.reap()
                row = store.list_assignments()[0]
                self.assertEqual(row.state, "validation_ready")
                self.assertEqual(row.completion_percent, 50)
            finally:
                scheduler.shutdown()
