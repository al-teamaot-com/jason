from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import tempfile
import unittest

from connectors.src.jason_connectors.approval_requests import (
    ApprovalDecision,
    ApprovalRequestService,
    ApprovalResponse,
    SQLiteApprovalRequestRepository,
)
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
from orchestrator.approval_continuation_guard import SQLiteApprovalContinuationGuard
from orchestrator.approvals import ApprovalResumeBridge, JKD001ApprovalAuthorityChecker
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.production_promotion_approval import (
    OwnerApprovalAuthorityChecker,
    ProductionPromotionApprovalConsumer,
    ProductionPromotionApprovalScope,
)


NOW = datetime(2026, 10, 2, 14, 0, tzinfo=timezone.utc)
PLAN = "a" * 64


class Contexts:
    def __init__(self) -> None:
        self.records = {}

    def put_context(self, context) -> None:
        self.records[context.context_id] = context


def orchestration_request(plan: str = PLAN) -> OrchestrationRequest:
    return OrchestrationRequest(
        execution_id="promotion-exec-1",
        correlation_id="promotion-corr-1",
        principal_id="release-coordinator",
        organization_id="org-a",
        client_id=None,
        capability_name="jason.deployment.apply",
        capability_version="1",
        requested_mode="execute",
        orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=False,
        approval_present=False,
        risk="critical",
        data_handling=DataHandlingPolicy(
            classification="internal",
            hosted_processing_allowed=False,
            retention_allowed=False,
        ),
        budget=ExecutionBudget(
            maximum_estimated_cost=Decimal("0"),
            maximum_attempts=1,
        ),
        arguments={
            "target_environment": "production",
            "promotion_id": "promotion-1",
            "plan_sha256": plan,
        },
    )


class ProductionPromotionApprovalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.identities = InMemoryIdentityRepository()
        self.grants = InMemoryAuthorityGrantRepository()
        self.formal_approvals = InMemoryApprovalRepository()
        self.contexts = Contexts()

        for identity_id in ("release-coordinator", "owner-al", "technician"):
            self.identities.put(IdentityRecord(identity_id, "human", "org-a"))

        self.grants.put(
            AuthorityGrant(
                "grant-requester",
                "release-coordinator",
                "jason.deployment.apply",
                "org-a",
                None,
                PermissionMode.EXECUTE,
                approval_required=True,
            )
        )
        self.grants.put(
            AuthorityGrant(
                "grant-owner",
                "owner-al",
                "jason.deployment.apply",
                "org-a",
                None,
                PermissionMode.EXECUTE,
            )
        )
        self.grants.put(
            AuthorityGrant(
                "grant-tech",
                "technician",
                "jason.deployment.apply",
                "org-a",
                None,
                PermissionMode.EXECUTE,
            )
        )

        self.authority = IdentityAuthorityService(
            self.identities,
            self.grants,
            self.formal_approvals,
            contexts=self.contexts,
            clock=lambda: NOW,
        )
        delegate = JKD001ApprovalAuthorityChecker(
            self.identities,
            self.grants,
            clock=lambda: NOW,
        )
        self.owner_checker = OwnerApprovalAuthorityChecker(
            delegate=delegate,
            owner_identity_ids={"owner-al"},
        )
        self.requests = SQLiteApprovalRequestRepository(
            self.tempdir.name + "/approval-requests.sqlite3"
        )
        self.service = ApprovalRequestService(self.requests, self.owner_checker)
        self.guard = SQLiteApprovalContinuationGuard(
            self.tempdir.name + "/continuations.sqlite3"
        )
        self.guard.initialize()
        self.consumer = ProductionPromotionApprovalConsumer(
            approval_requests=self.requests,
            resume_bridge=ApprovalResumeBridge(self.formal_approvals, self.authority),
            continuation_guard=self.guard,
        )

    def tearDown(self) -> None:
        self.requests.close()
        self.tempdir.cleanup()

    def create_request(self, authorized_owner_ids=("owner-al",)):
        request = ProductionPromotionApprovalScope(
            approval_id="prod-approval-1",
            execution_id="promotion-exec-1",
            correlation_id="promotion-corr-1",
            organization_id="org-a",
            requested_by="release-coordinator",
            promotion_id="promotion-1",
            plan_sha256=PLAN,
            requested_at=NOW,
            expires_at=NOW + timedelta(minutes=15),
            authorized_owner_ids=authorized_owner_ids,
        ).build_request()
        return self.service.create(request, now=NOW)

    def approve(self, approver: str = "owner-al"):
        return self.service.accept_response(
            ApprovalResponse(
                approval_id="prod-approval-1",
                organization_id="org-a",
                approver_identity_id=approver,
                decision=ApprovalDecision.APPROVE,
                decided_at=NOW + timedelta(minutes=1),
                channel="microsoft_teams",
                channel_response_id="teams-response-1",
            ),
            now=NOW + timedelta(minutes=1),
        )

    def test_owner_approval_binds_exact_plan_and_is_consumed_once(self):
        self.create_request()
        accepted = self.approve()
        resumed, authorization = self.consumer.authorize_for_apply(
            original_request=orchestration_request(),
            accepted=accepted,
            authentication_assurance="mfa",
            promotion_id="promotion-1",
            plan_sha256=PLAN,
            now=NOW + timedelta(minutes=2),
        )
        self.assertTrue(resumed.authority_allowed)
        self.assertTrue(resumed.approval_present)
        self.assertEqual(authorization.plan_sha256, PLAN)
        self.assertEqual(authorization.decided_by, "owner-al")

        with self.assertRaises(PermissionError):
            self.consumer.authorize_for_apply(
                original_request=orchestration_request(),
                accepted=accepted,
                authentication_assurance="mfa",
                promotion_id="promotion-1",
                plan_sha256=PLAN,
                now=NOW + timedelta(minutes=3),
            )

    def test_non_owner_cannot_approve_even_with_execute_grant(self):
        self.create_request(authorized_owner_ids=("technician",))
        with self.assertRaises(PermissionError):
            self.approve("technician")

    def test_plan_drift_after_owner_approval_fails_closed(self):
        self.create_request()
        accepted = self.approve()
        with self.assertRaises(PermissionError):
            self.consumer.authorize_for_apply(
                original_request=orchestration_request("b" * 64),
                accepted=accepted,
                authentication_assurance="mfa",
                promotion_id="promotion-1",
                plan_sha256="b" * 64,
                now=NOW + timedelta(minutes=2),
            )

    def test_cross_environment_apply_fails_closed(self):
        self.create_request()
        accepted = self.approve()
        bad = replace(
            orchestration_request(),
            arguments={
                "target_environment": "candidate",
                "promotion_id": "promotion-1",
                "plan_sha256": PLAN,
            },
        )
        with self.assertRaises(PermissionError):
            self.consumer.authorize_for_apply(
                original_request=bad,
                accepted=accepted,
                authentication_assurance="mfa",
                promotion_id="promotion-1",
                plan_sha256=PLAN,
                now=NOW + timedelta(minutes=2),
            )

    def test_expired_approval_fails_closed(self):
        self.create_request()
        accepted = self.approve()
        with self.assertRaises(PermissionError):
            self.consumer.authorize_for_apply(
                original_request=orchestration_request(),
                accepted=accepted,
                authentication_assurance="mfa",
                promotion_id="promotion-1",
                plan_sha256=PLAN,
                now=NOW + timedelta(minutes=16),
            )


if __name__ == "__main__":
    unittest.main()
