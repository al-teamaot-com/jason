from pathlib import Path
import json
import tempfile
import time
import unittest

from pm_v2.config import load_config
from pm_v2.scheduler import Scheduler
from pm_v2.store import PMV2Store


class PMV2FaultInjectionTests(unittest.TestCase):
    def test_failure_blocker_and_expired_lease_do_not_stop_other_work(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "roadmap.md").write_text("", encoding="utf-8")
            (root / "SUPPORT.md").write_text("", encoding="utf-8")
            cfg = {
                "schema_version": "1.0",
                "instance_id": "fault-test",
                "poll_interval_seconds": 1,
                "lease_seconds": 3,
                "max_concurrent_jobs": 3,
                "max_concurrent_components": 1,
                "state": {"database_path": str(root / "state.sqlite3")},
                "sources": {
                    "roadmap_path": "roadmap.md",
                    "support_path": "SUPPORT.md",
                },
                "workers": {
                    "success": {
                        "enabled": True,
                        "max_concurrency": 2,
                        "max_attempts": 2,
                        "retry_delay_seconds": 1,
                        "command": ["python3", "-c", "pass"],
                    },
                    "failure": {
                        "enabled": True,
                        "max_concurrency": 1,
                        "max_attempts": 2,
                        "retry_delay_seconds": 1,
                        "command": ["python3", "-c", "raise SystemExit(9)"],
                    },
                },
                "components": {},
                "paths": {
                    "legacy_spool": str(root / "legacy"),
                    "release_state": str(root / "release"),
                },
                "recovery": {
                    "snapshot_directory": str(root / "snapshot"),
                    "snapshot_interval_seconds": 60,
                    "replica_directories": [],
                },
                "ownership": {"owned_todo_ids": []},
                "control": {
                    "status_snapshot_path": str(root / "control/status.json"),
                    "request_inbox": str(root / "control/requests"),
                    "result_directory": str(root / "control/results"),
                },
                "communications": {
                    "required_status_fields": [
                        "Status", "Completed", "Still required",
                        "What I'm doing next", "What you need to do",
                    ],
                    "approval_channel": "microsoft_teams",
                },
            }
            path = root / "config.json"
            path.write_text(json.dumps(cfg), encoding="utf-8")
            config = load_config(path, repo=root)
            store = PMV2Store(config.database_path)
            store.initialize()

            def add(identifier, work_type):
                store.upsert_assignment(
                    assignment_id=identifier,
                    source="fault-test",
                    source_ref=identifier,
                    title=identifier,
                    priority=1,
                    work_type=work_type,
                    runnable=True,
                    scope_hash="sha256:" + identifier,
                    metadata={},
                )

            add("good-1", "success")
            add("bad-1", "failure")
            add("blocked-1", "success")
            store.update_state(
                "blocked-1",
                state="blocked",
                runnable=False,
                completion_percent=10,
                reason="external_dependency_unavailable",
            )

            scheduler = Scheduler(config=config, store=store, repo=root)

            def reap_until(identifier, expected_state, timeout=3.0):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    scheduler.reap()
                    state = store.get_assignment(identifier).state
                    if state == expected_state:
                        return
                    time.sleep(0.02)
                self.fail(
                    f"{identifier} did not reach {expected_state}; "
                    f"final state={store.get_assignment(identifier).state}"
                )

            try:
                self.assertEqual(scheduler.dispatch_available(), 2)
                reap_until("good-1", "validation_ready")
                reap_until("bad-1", "retry_ready")
                states = {row.assignment_id: row.state for row in store.list_assignments()}
                self.assertEqual(states["good-1"], "validation_ready")
                self.assertEqual(states["bad-1"], "retry_ready")
                self.assertEqual(states["blocked-1"], "blocked")

                # Second identical failure blocks only the failed assignment.
                time.sleep(1.05)
                self.assertEqual(scheduler.dispatch_available(), 1)
                reap_until("bad-1", "blocked")

                # New healthy work still starts and finishes after the failure.
                add("good-2", "success")
                self.assertEqual(scheduler.dispatch_available(), 1)
                reap_until("good-2", "validation_ready")
                self.assertEqual(
                    store.get_assignment("good-2").state,
                    "validation_ready",
                )

                # A simulated dead worker lease is recovered durably.
                add("recovered-1", "success")
                claimed = store.claim_next(
                    instance_id="dead-worker",
                    lease_seconds=1,
                    work_type="success",
                )
                self.assertEqual(claimed.assignment_id, "recovered-1")
                time.sleep(1.05)
                self.assertEqual(store.release_expired_leases(), 1)
                self.assertEqual(
                    store.get_assignment("recovered-1").state,
                    "retry_ready",
                )
                self.assertEqual(scheduler.dispatch_available(), 1)
                reap_until("recovered-1", "validation_ready")
                self.assertEqual(
                    store.get_assignment("recovered-1").state,
                    "validation_ready",
                )
            finally:
                scheduler.shutdown()
