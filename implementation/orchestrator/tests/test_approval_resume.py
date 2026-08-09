from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from connectors.src.jason_connectors.approval_requests import AcceptedApproval
from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.identity_authority import (
    AuthorityGrant,
    IdentityAuthorityService,
    IdentityRecord,
    InMemoryApprovalRepository,
    InMemoryAuthorityGrantRepository,
    InMemoryIdentityRepository,
    PermissionMode,
)
from orchestrator.approvals import ApprovalResumeBridge, JKD001ApprovalAuthorityChecker
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest

NOW = datetime(2026, 8, 9, 16, 0, tzinfo=timezone.utc)


class Contexts:
    def __init__(self) -> None:
        self.records = {}
    def put_context(self, context) -> None:
        self.records[context.context_id] = context


def request() -> OrchestrationRequest:
    return OrchestrationRequest(
        execution_id="req-1", correlation_id="corr-1", principal_id="requester",
        organization_id="org-a", client_id="client-a", capability_name="microsoft.resource.execute",
        capability_version=None, requested_mode="execute", orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=False, approval_present=False, risk="high",
        data_handling=DataHandlingPolicy(), budget=ExecutionBudget(),
    )


def accepted(**overrides) -> AcceptedApproval:
    values = dict(
        approval_id="apr-1", request_id="req-1", capability="microsoft.resource.execute",
        organization_id="org-a", client_id="client-a", requested_by="requester", status="approved",
        decided_by="approver", decided_at=NOW, expires_at=NOW + timedelta(minutes=10),
        channel="microsoft_teams", channel_response_id="teams-1", evidence_references=(),
    )
    values.update(overrides)
    return AcceptedApproval(**values)


class ApprovalResumeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.identities = InMemoryIdentityRepository()
        self.grants = InMemoryAuthorityGrantRepository()
        self.approvals = InMemoryApprovalRepository()
        self.contexts = Contexts()
        self.identities.put(IdentityRecord("requester", "human", "org-a"))
        self.identities.put(IdentityRecord("approver", "human", "org-a"))
        self.grants.put(AuthorityGrant(
            "grant-requester", "requester", "microsoft.resource.execute", "org-a", "client-a",
            PermissionMode.EXECUTE, approval_required=True,
        ))
        self.grants.put(AuthorityGrant(
            "grant-approver", "approver", "microsoft.resource.execute", "org-a", "client-a",
            PermissionMode.EXECUTE,
        ))
        self.authority = IdentityAuthorityService(
            self.identities, self.grants, self.approvals, contexts=self.contexts, clock=lambda: NOW,
        )

    def test_jkd_checker_requires_exact_scope(self) -> None:
        checker = JKD001ApprovalAuthorityChecker(self.identities, self.grants, clock=lambda: NOW)
        self.assertTrue(checker.can_approve(
            approver_identity_id="approver", organization_id="org-a", client_id="client-a",
            capability="microsoft.resource.execute", requested_mode="execute",
        ))
        self.assertFalse(checker.can_approve(
            approver_identity_id="approver", organization_id="org-b", client_id="client-a",
            capability="microsoft.resource.execute", requested_mode="execute",
        ))

    def test_approved_response_is_persisted_then_reauthorized(self) -> None:
        resumed = ApprovalResumeBridge(self.approvals, self.authority).resume(
            original_request=request(), accepted=accepted(), authentication_assurance="mfa",
        )
        self.assertTrue(resumed.approval_present)
        self.assertTrue(resumed.authority_allowed)
        self.assertIsNotNone(resumed.authority_context_id)
        self.assertEqual(self.approvals.get("apr-1").decided_by, "approver")
        self.assertIn(resumed.authority_context_id, self.contexts.records)

    def test_cross_tenant_approval_fails_before_persistence(self) -> None:
        with self.assertRaises(PermissionError):
            ApprovalResumeBridge(self.approvals, self.authority).resume(
                original_request=request(), accepted=accepted(organization_id="org-b"),
                authentication_assurance="mfa",
            )
        self.assertIsNone(self.approvals.get("apr-1"))

    def test_approval_cannot_authorize_different_capability(self) -> None:
        with self.assertRaises(PermissionError):
            ApprovalResumeBridge(self.approvals, self.authority).resume(
                original_request=request(), accepted=accepted(capability="datto.resource.execute"),
                authentication_assurance="mfa",
            )


if __name__ == "__main__":
    unittest.main()
