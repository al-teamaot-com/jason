from pathlib import Path
import json
import tempfile
import time
import unittest

from pm_v2.config import load_config
from pm_v2.control import consume_control_requests, publish_status_snapshot
from pm_v2.scheduler import Scheduler
from pm_v2.store import PMV2Store


class PMV2ControlTests(unittest.TestCase):
    def _store(self, root):
        store = PMV2Store(root / "state.sqlite3")
        store.initialize()
        store.upsert_assignment(
            assignment_id="a1", source="test", source_ref="1",
            title="controlled", priority=5, work_type="development",
            runnable=True, scope_hash="sha256:1", metadata={},
        )
        return store

    def test_pause_resume_and_priority_are_audited_state_changes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = self._store(root)
            paused = store.apply_owner_control(
                assignment_id="a1", action="pause",
                principal_id="owner", request_id="r1",
            )
            self.assertEqual(paused["state"], "paused")
            self.assertFalse(store.get_assignment("a1").runnable)
            store.apply_owner_control(
                assignment_id="a1", action="priority", priority=1,
                principal_id="owner", request_id="r2",
            )
            self.assertEqual(store.get_assignment("a1").priority, 1)
            resumed = store.apply_owner_control(
                assignment_id="a1", action="resume",
                principal_id="owner", request_id="r3",
            )
            self.assertEqual(resumed["state"], "queued")
            self.assertTrue(store.get_assignment("a1").runnable)

    def test_cancel_queued_work_is_immediate_and_terminal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = self._store(root)
            result = store.apply_owner_control(
                assignment_id="a1", action="cancel",
                principal_id="owner", request_id="r1",
            )
            self.assertEqual(result["state"], "cancelled")
            self.assertFalse(store.get_assignment("a1").runnable)

    def test_governed_control_request_is_consumed_once(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = self._store(root)
            inbox = root / "requests"
            results = root / "results"
            inbox.mkdir()
            request = {
                "schema_version": "1.0",
                "request_id": "request-1",
                "principal_id": "owner",
                "organization_id": "aot",
                "assignment_id": "a1",
                "action": "pause",
                "priority": None,
                "source": "governed_runtime_authenticated_request"
            }
            (inbox / "request-1.json").write_text(json.dumps(request))
            first = consume_control_requests(
                store=store, inbox=inbox, results=results
            )
            second = consume_control_requests(
                store=store, inbox=inbox, results=results
            )
            self.assertEqual(first["applied"], 1)
            self.assertEqual(second["skipped"], 1)
            self.assertEqual(store.get_assignment("a1").state, "paused")

    def test_unauthenticated_control_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = self._store(root)
            inbox = root / "requests"
            results = root / "results"
            inbox.mkdir()
            (inbox / "bad.json").write_text(json.dumps({
                "schema_version": "1.0",
                "request_id": "bad",
                "principal_id": "owner",
                "organization_id": "aot",
                "assignment_id": "a1",
                "action": "cancel",
                "source": "terminal"
            }))
            result = consume_control_requests(
                store=store, inbox=inbox, results=results
            )
            self.assertEqual(result["rejected"], 1)
            self.assertEqual(store.get_assignment("a1").state, "queued")

    def test_status_snapshot_is_bounded_and_read_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = self._store(root)
            path = root / "status.json"
            payload = publish_status_snapshot(store=store, path=path)
            self.assertEqual(payload["summary"]["assignment_count"], 1)
            self.assertEqual(payload["assignments"][0]["assignment_id"], "a1")
            self.assertEqual(store.get_assignment("a1").state, "queued")


class PMV2RunningControlTests(unittest.TestCase):
    def test_pause_running_work_waits_for_bounded_worker_return(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "roadmap.md").write_text("")
            (root / "SUPPORT.md").write_text("")
            config_path = root / "config.json"
            config_path.write_text(json.dumps({
                "schema_version": "1.0",
                "instance_id": "test",
                "poll_interval_seconds": 1,
                "lease_seconds": 10,
                "max_concurrent_jobs": 1,
                "max_concurrent_components": 1,
                "state": {"database_path": str(root / "state.sqlite3")},
                "sources": {"roadmap_path": "roadmap.md", "support_path": "SUPPORT.md"},
                "workers": {"development": {
                    "enabled": True, "max_concurrency": 1,
                    "max_attempts": 2, "retry_delay_seconds": 1,
                    "timeout_seconds": 5,
                    "command": ["python3", "-c", "import time; time.sleep(0.2)"]
                }},
                "components": {},
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
                        "Status","Completed","Still required",
                        "What I'm doing next","What you need to do"
                    ],
                    "approval_channel": "microsoft_teams"
                }
            }))
            config = load_config(config_path, repo=root)
            store = PMV2Store(config.database_path)
            store.initialize()
            store.upsert_assignment(
                assignment_id="a1", source="test", source_ref="1",
                title="run", priority=1, work_type="development",
                runnable=True, scope_hash="sha256:1", metadata={},
            )
            scheduler = Scheduler(config=config, store=store, repo=root)
            try:
                self.assertEqual(scheduler.dispatch_available(), 1)
                store.apply_owner_control(
                    assignment_id="a1", action="pause",
                    principal_id="owner", request_id="pause-1",
                )
                self.assertEqual(store.get_assignment("a1").state, "pause_requested")
                deadline = time.monotonic() + 2.0
                while time.monotonic() < deadline:
                    scheduler.reap()
                    if store.get_assignment("a1").state == "paused":
                        break
                    time.sleep(0.02)
                self.assertEqual(store.get_assignment("a1").state, "paused")
            finally:
                scheduler.shutdown()
