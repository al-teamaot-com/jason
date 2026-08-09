from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from connectors.microsoft_graph.teams_approval_ingress import VerifiedMicrosoftPrincipal
from connectors.src.jason_connectors.approval_requests import AcceptedApproval
from orchestrator.approval_audit import (
    ApprovalAuditEventType,
    ApprovalAuditRecorder,
    InMemoryApprovalAuditSink,
)
from orchestrator.teams_approval_flow import TeamsApprovalFlow


NOW = datetime(2026, 8, 9, 16, 30, tzinfo=timezone.utc)


@dataclass
class OriginalRequest:
    execution_id: str = "execution-1"
    correlation_id: str = "correlation-1"
    principal_id: str = "requester-1"
    organization_id: str = "org-1"
    client_id: str | None = "client-1"
    capability_name: str = "capability.read"


@dataclass
class ResumedRequest:
    authority_context_id: str = "authority-context-1"


@dataclass
class StubTokenVerifier:
    principal: VerifiedMicrosoftPrincipal
    calls: int = 0

    def verify(self, token: str) -> VerifiedMicrosoftPrincipal:
        self.calls += 1
        if token != "signed-token":
            raise PermissionError("bad token")
        return self.principal


@dataclass
class StubIngress:
    response: object
    calls: int = 0

    def accept_verified_interaction(self, **kwargs):
        self.calls += 1
        return self.response


@dataclass
class StubApprovalService:
    accepted: AcceptedApproval
    calls: int = 0
    error: Exception | None = None

    def accept_response(self, response, *, now=None):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.accepted


@dataclass
class StubResumeBridge:
    resumed: object
    calls: int = 0
    assurance: str | None = None

    def resume(self, *, original_request, accepted, authentication_assurance):
        self.calls += 1
        self.assurance = authentication_assurance
        return self.resumed


class TeamsApprovalFlowTests(unittest.TestCase):
    def principal(self):
        return VerifiedMicrosoftPrincipal(
            tenant_id="tenant-1",
            object_id="object-1",
            subject="subject-1",
            audience="api://jason",
            issuer="https://login.microsoftonline.com/tenant-1/v2.0",
            authentication_assurance="mfa",
        )

    def accepted(self, status="approved"):
        return AcceptedApproval(
            approval_id="approval-1",
            request_id="execution-1",
            capability="capability.read",
            organization_id="org-1",
            client_id="client-1",
            requested_by="requester-1",
            status=status,
            decided_by="approver-1",
            decided_at=NOW,
            expires_at=NOW + timedelta(minutes=10),
            channel="teams",
            channel_response_id="response-1",
            evidence_references=(),
        )

    def flow(self, token, ingress, approval, bridge):
        sink = InMemoryApprovalAuditSink()
        ids = iter(f"event-{index}" for index in range(20))
        return TeamsApprovalFlow(
            token,
            ingress,
            approval,
            bridge,
            ApprovalAuditRecorder(sink),
            event_id_factory=lambda: next(ids),
        ), sink

    def test_approved_response_records_authentication_decision_and_resume(self):
        token = StubTokenVerifier(self.principal())
        ingress = StubIngress(response=object())
        approval = StubApprovalService(self.accepted())
        bridge = StubResumeBridge(resumed=ResumedRequest())
        flow, sink = self.flow(token, ingress, approval, bridge)

        result = flow.handle_response(
            token="signed-token",
            payload={"approval_id": "approval-1"},
            original_request=OriginalRequest(),
            decided_at=NOW,
            now=NOW,
        )

        self.assertEqual(result.resumed_request.authority_context_id, "authority-context-1")
        self.assertEqual(bridge.assurance, "mfa")
        self.assertEqual(
            [event.event_type for event in sink.events],
            [
                ApprovalAuditEventType.RESPONSE_AUTHENTICATED,
                ApprovalAuditEventType.RESPONSE_ACCEPTED,
                ApprovalAuditEventType.JKD_REAUTHORIZED,
                ApprovalAuditEventType.ORCHESTRATOR_RESUMED,
            ],
        )
        self.assertTrue(ApprovalAuditRecorder.verify_chain(sink.events))
        self.assertEqual(sink.events[-1].authority_context_id, "authority-context-1")

    def test_denial_is_audited_and_never_resumes_execution(self):
        bridge = StubResumeBridge(resumed=ResumedRequest())
        flow, sink = self.flow(
            StubTokenVerifier(self.principal()),
            StubIngress(response=object()),
            StubApprovalService(self.accepted(status="denied")),
            bridge,
        )
        result = flow.handle_response(
            token="signed-token",
            payload={"approval_id": "approval-1"},
            original_request=OriginalRequest(),
            decided_at=NOW,
            now=NOW,
        )
        self.assertIsNone(result.resumed_request)
        self.assertEqual(bridge.calls, 0)
        self.assertEqual(sink.events[-1].event_type, ApprovalAuditEventType.RESPONSE_DENIED)

    def test_authentication_failure_stops_before_ingress_and_is_audited(self):
        ingress = StubIngress(response=object())
        flow, sink = self.flow(
            StubTokenVerifier(self.principal()),
            ingress,
            StubApprovalService(self.accepted()),
            StubResumeBridge(resumed=ResumedRequest()),
        )
        with self.assertRaises(PermissionError):
            flow.handle_response(
                token="forged-token",
                payload={"approval_id": "approval-1"},
                original_request=OriginalRequest(),
                decided_at=NOW,
                now=NOW,
            )
        self.assertEqual(ingress.calls, 0)
        self.assertEqual(sink.events[-1].event_type, ApprovalAuditEventType.PROCESSING_FAILED)
        self.assertEqual(sink.events[-1].metadata["stage"], "token_verification")

    def test_ingress_rejection_is_audited_and_stops_before_approval_authority(self):
        class RejectingIngress:
            def accept_verified_interaction(self, **kwargs):
                raise PermissionError("tenant mismatch")

        approval = StubApprovalService(self.accepted())
        flow, sink = self.flow(
            StubTokenVerifier(self.principal()),
            RejectingIngress(),
            approval,
            StubResumeBridge(resumed=ResumedRequest()),
        )
        with self.assertRaises(PermissionError):
            flow.handle_response(
                token="signed-token",
                payload={"approval_id": "approval-1"},
                original_request=OriginalRequest(),
                decided_at=NOW,
                now=NOW,
            )
        self.assertEqual(approval.calls, 0)
        self.assertEqual(sink.events[-1].event_type, ApprovalAuditEventType.AUTHORIZATION_REJECTED)

    def test_expiration_is_recorded_without_resume(self):
        approval = StubApprovalService(self.accepted(), error=PermissionError("approval request expired"))
        bridge = StubResumeBridge(resumed=ResumedRequest())
        flow, sink = self.flow(
            StubTokenVerifier(self.principal()),
            StubIngress(response=object()),
            approval,
            bridge,
        )
        with self.assertRaises(PermissionError):
            flow.handle_response(
                token="signed-token",
                payload={"approval_id": "approval-1"},
                original_request=OriginalRequest(),
                decided_at=NOW,
                now=NOW,
            )
        self.assertEqual(bridge.calls, 0)
        self.assertEqual(sink.events[-1].event_type, ApprovalAuditEventType.REQUEST_EXPIRED)

    def test_audit_failure_fails_closed_before_authority_progresses(self):
        class FailingAudit:
            def record(self, event):
                raise RuntimeError("audit unavailable")

        ingress = StubIngress(response=object())
        approval = StubApprovalService(self.accepted())
        bridge = StubResumeBridge(resumed=ResumedRequest())
        flow = TeamsApprovalFlow(
            StubTokenVerifier(self.principal()),
            ingress,
            approval,
            bridge,
            FailingAudit(),
        )
        with self.assertRaises(RuntimeError):
            flow.handle_response(
                token="signed-token",
                payload={"approval_id": "approval-1"},
                original_request=OriginalRequest(),
                decided_at=NOW,
                now=NOW,
            )
        self.assertEqual(ingress.calls, 0)
        self.assertEqual(approval.calls, 0)
        self.assertEqual(bridge.calls, 0)


if __name__ == "__main__":
    unittest.main()
