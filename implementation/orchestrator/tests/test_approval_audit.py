from __future__ import annotations

import unittest
from datetime import datetime, timezone

from connectors.src.jason_connectors.approval_requests import ApprovalEvidenceReference
from orchestrator.approval_audit import (
    ApprovalAuditEvent,
    ApprovalAuditEventType,
    ApprovalAuditRecorder,
    InMemoryApprovalAuditSink,
)


NOW = datetime(2026, 8, 9, 17, 0, tzinfo=timezone.utc)


class ApprovalAuditTests(unittest.TestCase):
    def event(self, event_id: str, event_type=ApprovalAuditEventType.REQUEST_CREATED, **overrides):
        values = dict(
            event_id=event_id,
            event_type=event_type,
            occurred_at=NOW,
            approval_id="approval-1",
            request_id="execution-1",
            correlation_id="correlation-1",
            organization_id="org-1",
            client_id="client-1",
            actor_identity_id="requester-1",
            capability="capability.read",
        )
        values.update(overrides)
        return ApprovalAuditEvent(**values)

    def test_events_form_verifiable_hash_chain(self):
        sink = InMemoryApprovalAuditSink()
        recorder = ApprovalAuditRecorder(sink)
        first = recorder.record(self.event("event-1"))
        second = recorder.record(
            self.event(
                "event-2",
                ApprovalAuditEventType.RESPONSE_AUTHENTICATED,
                actor_identity_id="approver-1",
                channel="teams",
                channel_reference_id="response-1",
            )
        )
        self.assertEqual(second.previous_event_hash, first.event_hash)
        self.assertTrue(recorder.verify_chain(sink.events))

    def test_tampering_breaks_chain_verification(self):
        sink = InMemoryApprovalAuditSink()
        recorder = ApprovalAuditRecorder(sink)
        recorded = recorder.record(self.event("event-1"))
        tampered = self.event("event-1", reason_code="changed")
        tampered = ApprovalAuditEvent(
            **{name: getattr(tampered, name) for name in tampered.__dataclass_fields__ if name != "event_hash"},
            event_hash=recorded.event_hash,
        )
        self.assertFalse(recorder.verify_chain([tampered]))

    def test_cross_organization_evidence_is_rejected(self):
        evidence = ApprovalEvidenceReference(
            artifact_id="artifact-1",
            organization_id="org-2",
            content_sha256="a" * 64,
        )
        with self.assertRaises(ValueError):
            ApprovalAuditRecorder(InMemoryApprovalAuditSink()).record(
                self.event("event-1", evidence_references=(evidence,))
            )

    def test_duplicate_event_id_is_rejected(self):
        sink = InMemoryApprovalAuditSink()
        recorder = ApprovalAuditRecorder(sink)
        recorder.record(self.event("event-1"))
        with self.assertRaises(ValueError):
            recorder.record(self.event("event-1", ApprovalAuditEventType.DELIVERY_RECORDED))

    def test_caller_cannot_splice_wrong_previous_hash(self):
        recorder = ApprovalAuditRecorder(InMemoryApprovalAuditSink())
        recorder.record(self.event("event-1"))
        with self.assertRaises(ValueError):
            recorder.record(self.event("event-2", previous_event_hash="f" * 64))


if __name__ == "__main__":
    unittest.main()
