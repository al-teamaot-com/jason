from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from connectors.microsoft_graph.teams_approval_ingress import VerifiedMicrosoftPrincipal
from connectors.src.jason_connectors.approval_requests import AcceptedApproval
from orchestrator.teams_approval_flow import TeamsApprovalFlow


NOW = datetime(2026, 8, 9, 16, 30, tzinfo=timezone.utc)


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

    def accept_response(self, response, *, now=None):
        self.calls += 1
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

    def test_approved_response_reaches_resume_only_after_all_prior_boundaries(self):
        token = StubTokenVerifier(self.principal())
        ingress = StubIngress(response=object())
        approval = StubApprovalService(self.accepted())
        resumed = object()
        bridge = StubResumeBridge(resumed=resumed)
        flow = TeamsApprovalFlow(token, ingress, approval, bridge)
        original = object()

        result = flow.handle_response(
            token="signed-token",
            payload={"approval_id": "approval-1"},
            original_request=original,
            decided_at=NOW,
            now=NOW,
        )

        self.assertIs(result.resumed_request, resumed)
        self.assertEqual(token.calls, 1)
        self.assertEqual(ingress.calls, 1)
        self.assertEqual(approval.calls, 1)
        self.assertEqual(bridge.calls, 1)
        self.assertEqual(bridge.assurance, "mfa")

    def test_denial_is_accepted_but_never_resumes_execution(self):
        bridge = StubResumeBridge(resumed=object())
        flow = TeamsApprovalFlow(
            StubTokenVerifier(self.principal()),
            StubIngress(response=object()),
            StubApprovalService(self.accepted(status="denied")),
            bridge,
        )

        result = flow.handle_response(
            token="signed-token",
            payload={},
            original_request=object(),
            decided_at=NOW,
            now=NOW,
        )

        self.assertEqual(result.accepted_approval.status, "denied")
        self.assertIsNone(result.resumed_request)
        self.assertEqual(bridge.calls, 0)

    def test_authentication_failure_stops_before_ingress(self):
        ingress = StubIngress(response=object())
        flow = TeamsApprovalFlow(
            StubTokenVerifier(self.principal()),
            ingress,
            StubApprovalService(self.accepted()),
            StubResumeBridge(resumed=object()),
        )

        with self.assertRaises(PermissionError):
            flow.handle_response(
                token="forged-token",
                payload={},
                original_request=object(),
                decided_at=NOW,
                now=NOW,
            )
        self.assertEqual(ingress.calls, 0)

    def test_ingress_failure_stops_before_approval_authority(self):
        class RejectingIngress:
            def accept_verified_interaction(self, **kwargs):
                raise PermissionError("tenant mismatch")

        approval = StubApprovalService(self.accepted())
        flow = TeamsApprovalFlow(
            StubTokenVerifier(self.principal()),
            RejectingIngress(),
            approval,
            StubResumeBridge(resumed=object()),
        )

        with self.assertRaises(PermissionError):
            flow.handle_response(
                token="signed-token",
                payload={},
                original_request=object(),
                decided_at=NOW,
                now=NOW,
            )
        self.assertEqual(approval.calls, 0)


if __name__ == "__main__":
    unittest.main()
