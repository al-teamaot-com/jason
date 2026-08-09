from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from orchestrator.approval_audit import ApprovalAuditEvent, ApprovalAuditEventType, ApprovalAuditRecorder
from orchestrator.approval_audit_sqlite import SQLiteApprovalAuditSink


NOW = datetime(2026, 8, 9, 16, 30, tzinfo=timezone.utc)


def event(event_id: str, organization_id: str = "org-1") -> ApprovalAuditEvent:
    return ApprovalAuditEvent(
        event_id=event_id,
        event_type=ApprovalAuditEventType.RESPONSE_AUTHENTICATED,
        occurred_at=NOW,
        approval_id="approval-1",
        request_id="execution-1",
        correlation_id="correlation-1",
        organization_id=organization_id,
        client_id="client-1",
        actor_identity_id="identity-1",
        capability="microsoft.graph.resource",
    )


class SQLiteApprovalAuditSinkTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "approval-audit.sqlite3")
        self.sink = SQLiteApprovalAuditSink(self.path)
        self.sink.initialize()
        self.recorder = ApprovalAuditRecorder(self.sink)

    def tearDown(self):
        self.temp.cleanup()

    def test_events_survive_new_sink_instance_and_chain_verifies(self):
        first = self.recorder.record(event("event-1"))
        second = self.recorder.record(event("event-2"))

        reopened = SQLiteApprovalAuditSink(self.path)
        stored = reopened.list_for_approval(approval_id="approval-1", organization_id="org-1")

        self.assertEqual((first.event_hash, second.event_hash), tuple(item.event_hash for item in stored))
        self.assertTrue(ApprovalAuditRecorder.verify_chain(stored))

    def test_duplicate_event_id_fails_closed(self):
        self.recorder.record(event("event-1"))
        with self.assertRaises(ValueError):
            self.recorder.record(event("event-1"))

    def test_cross_tenant_append_for_same_approval_fails_closed(self):
        self.recorder.record(event("event-1"))
        with self.assertRaises(PermissionError):
            self.recorder.record(event("event-2", organization_id="org-2"))

    def test_direct_append_rejects_invalid_hash(self):
        invalid = replace(event("event-1"), event_hash="0" * 64)
        with self.assertRaises(ValueError):
            self.sink.append(invalid)

    def test_direct_append_rejects_chain_race(self):
        first = self.recorder.record(event("event-1"))
        stale = replace(
            event("event-2"),
            previous_event_hash=None,
        )
        stale = replace(stale, event_hash=stale.calculated_hash())
        with self.assertRaises(ValueError):
            self.sink.append(stale)
        self.assertIsNotNone(first.event_hash)

    def test_queries_require_organization_scope(self):
        self.recorder.record(event("event-1"))
        self.assertEqual(
            (),
            self.sink.list_for_approval(approval_id="approval-1", organization_id="org-2"),
        )


if __name__ == "__main__":
    unittest.main()
