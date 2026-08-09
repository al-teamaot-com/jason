from datetime import datetime, timedelta, timezone
import unittest

from connectors.src.jason_connectors.approval_requests import (
    ApprovalEvidenceReference,
    ApprovalRequest,
    ApprovalRequestService,
    InMemoryApprovalRequestRepository,
)
from orchestrator.approval_audit import ApprovalAuditEventType, ApprovalAuditRecorder, InMemoryApprovalAuditSink
from orchestrator.approval_delivery import (
    ApprovalDeliveryReceipt,
    ApprovalRequestDeliveryCoordinator,
)


NOW = datetime(2026, 8, 9, 17, 0, tzinfo=timezone.utc)


class AllowAuthority:
    def can_approve(self, **kwargs):
        return True


class RecordingChannel:
    def __init__(self):
        self.requests = []

    def deliver(self, request):
        self.requests.append(request)
        return ApprovalDeliveryReceipt(
            channel="microsoft_teams",
            channel_reference_id="teams-message-1",
            delivered_at=NOW + timedelta(seconds=2),
        )


class FailingChannel:
    def deliver(self, request):
        raise RuntimeError("provider unavailable")


class FailingAuditSink(InMemoryApprovalAuditSink):
    def append(self, event):
        raise RuntimeError("audit unavailable")


def request():
    return ApprovalRequest(
        approval_id="approval-1",
        request_id="exec-1",
        correlation_id="corr-1",
        organization_id="org-1",
        client_id="client-1",
        requested_by="requester-1",
        capability="microsoft.resource.update",
        requested_mode="execute",
        requested_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
        authorized_approver_ids=("approver-1",),
        evidence_references=(
            ApprovalEvidenceReference(
                artifact_id="artifact-1",
                organization_id="org-1",
                content_sha256="a" * 64,
            ),
        ),
    )


class ApprovalDeliveryTests(unittest.TestCase):
    def service(self):
        return ApprovalRequestService(InMemoryApprovalRequestRepository(), AllowAuthority())

    def test_create_and_delivery_are_audited_in_order(self):
        sink = InMemoryApprovalAuditSink()
        channel = RecordingChannel()
        ids = iter(("event-1", "event-2"))
        coordinator = ApprovalRequestDeliveryCoordinator(
            approval_service=self.service(),
            audit=ApprovalAuditRecorder(sink),
            channel=channel,
            event_id_factory=lambda: next(ids),
        )

        receipt = coordinator.create_and_deliver(request(), now=NOW)

        self.assertEqual(receipt.channel_reference_id, "teams-message-1")
        self.assertEqual(len(channel.requests), 1)
        self.assertEqual(
            [event.event_type for event in sink.events],
            [ApprovalAuditEventType.REQUEST_CREATED, ApprovalAuditEventType.DELIVERY_RECORDED],
        )
        self.assertEqual(sink.events[1].previous_event_hash, sink.events[0].event_hash)
        self.assertEqual(sink.events[0].evidence_references[0].artifact_id, "artifact-1")

    def test_audit_failure_prevents_channel_delivery(self):
        channel = RecordingChannel()
        coordinator = ApprovalRequestDeliveryCoordinator(
            approval_service=self.service(),
            audit=ApprovalAuditRecorder(FailingAuditSink()),
            channel=channel,
        )

        with self.assertRaisesRegex(RuntimeError, "audit unavailable"):
            coordinator.create_and_deliver(request(), now=NOW)
        self.assertEqual(channel.requests, [])

    def test_delivery_failure_is_audited_and_does_not_create_authority(self):
        sink = InMemoryApprovalAuditSink()
        ids = iter(("event-1", "event-2"))
        coordinator = ApprovalRequestDeliveryCoordinator(
            approval_service=self.service(),
            audit=ApprovalAuditRecorder(sink),
            channel=FailingChannel(),
            event_id_factory=lambda: next(ids),
        )

        with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
            coordinator.create_and_deliver(request(), now=NOW)
        self.assertEqual(
            [event.event_type for event in sink.events],
            [ApprovalAuditEventType.REQUEST_CREATED, ApprovalAuditEventType.PROCESSING_FAILED],
        )
        self.assertEqual(sink.events[1].metadata["stage"], "delivery")

    def test_expired_request_never_reaches_channel_or_audit(self):
        sink = InMemoryApprovalAuditSink()
        channel = RecordingChannel()
        coordinator = ApprovalRequestDeliveryCoordinator(
            approval_service=self.service(),
            audit=ApprovalAuditRecorder(sink),
            channel=channel,
        )

        with self.assertRaisesRegex(ValueError, "already expired"):
            coordinator.create_and_deliver(request(), now=NOW + timedelta(minutes=11))
        self.assertEqual(channel.requests, [])
        self.assertEqual(sink.events, [])


if __name__ == "__main__":
    unittest.main()
