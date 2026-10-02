from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AbstractSet

from connectors.src.jason_connectors.approval_requests import (
    AcceptedApproval,
    ApprovalAuthorityChecker,
    ApprovalEvidenceReference,
    ApprovalPresentation,
    ApprovalRequest,
    ApprovalRequestRepository,
    ApprovalRequestStatus,
)
from orchestrator.approval_continuation_guard import (
    ApprovalContinuationClaim,
    ApprovalContinuationGuard,
)
from orchestrator.approvals import ApprovalResumeBridge
from orchestrator.contracts import OrchestrationRequest


PRODUCTION_DEPLOYMENT_CAPABILITY = "jason.deployment.apply"
PRODUCTION_TARGET = "production"
PROMOTION_ID_KEY = "production_promotion_id"
PLAN_SHA256_KEY = "production_plan_sha256"
TARGET_ENVIRONMENT_KEY = "target_environment"
AUTHORITY_CLASS_KEY = "approval_authority"


def _require_sha256(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) != 64 or any(c not in "0123456789abcdef" for c in normalized):
        raise ValueError("production plan SHA-256 must contain 64 hexadecimal characters")
    return normalized


@dataclass(frozen=True, slots=True)
class OwnerApprovalAuthorityChecker:
    delegate: ApprovalAuthorityChecker
    owner_identity_ids: AbstractSet[str]

    def can_approve(
        self,
        *,
        approver_identity_id: str,
        organization_id: str,
        client_id: str | None,
        capability: str,
        requested_mode: str,
    ) -> bool:
        if approver_identity_id not in self.owner_identity_ids:
            return False
        if capability != PRODUCTION_DEPLOYMENT_CAPABILITY:
            return False
        if requested_mode != "execute":
            return False
        return self.delegate.can_approve(
            approver_identity_id=approver_identity_id,
            organization_id=organization_id,
            client_id=client_id,
            capability=capability,
            requested_mode=requested_mode,
        )


@dataclass(frozen=True, slots=True)
class ProductionPromotionApprovalScope:
    approval_id: str
    execution_id: str
    correlation_id: str
    organization_id: str
    requested_by: str
    promotion_id: str
    plan_sha256: str
    requested_at: datetime
    expires_at: datetime
    authorized_owner_ids: tuple[str, ...]
    evidence_references: tuple[ApprovalEvidenceReference, ...] = ()

    def build_request(self) -> ApprovalRequest:
        if not self.promotion_id.strip():
            raise ValueError("promotion_id must be non-empty")
        if not self.authorized_owner_ids:
            raise ValueError("at least one Owner identity is required")
        digest = _require_sha256(self.plan_sha256)
        return ApprovalRequest(
            approval_id=self.approval_id,
            request_id=self.execution_id,
            correlation_id=self.correlation_id,
            organization_id=self.organization_id,
            client_id=None,
            requested_by=self.requested_by,
            capability=PRODUCTION_DEPLOYMENT_CAPABILITY,
            requested_mode="execute",
            requested_at=self.requested_at,
            expires_at=self.expires_at,
            authorized_approver_ids=self.authorized_owner_ids,
            evidence_references=self.evidence_references,
            presentation=ApprovalPresentation(
                title="Jason Production Promotion",
                summary="Approve the exact immutable Production promotion plan.",
                facts=(
                    ("Promotion", self.promotion_id),
                    ("Plan SHA-256", digest),
                    ("Target", PRODUCTION_TARGET),
                ),
            ),
            metadata={
                PROMOTION_ID_KEY: self.promotion_id.strip(),
                PLAN_SHA256_KEY: digest,
                TARGET_ENVIRONMENT_KEY: PRODUCTION_TARGET,
                AUTHORITY_CLASS_KEY: "owner",
            },
            status=ApprovalRequestStatus.PENDING,
        )


@dataclass(frozen=True, slots=True)
class ProductionPromotionAuthorization:
    approval_id: str
    promotion_id: str
    plan_sha256: str
    authority_context_id: str
    decided_by: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ProductionPromotionApprovalConsumer:
    approval_requests: ApprovalRequestRepository
    resume_bridge: ApprovalResumeBridge
    continuation_guard: ApprovalContinuationGuard

    def authorize_for_apply(
        self,
        *,
        original_request: OrchestrationRequest,
        accepted: AcceptedApproval,
        authentication_assurance: str,
        promotion_id: str,
        plan_sha256: str,
        now: datetime | None = None,
    ) -> tuple[OrchestrationRequest, ProductionPromotionAuthorization]:
        digest = _require_sha256(plan_sha256)
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("authorization clock must be timezone-aware")
        current = current.astimezone(timezone.utc)

        if original_request.capability_name != PRODUCTION_DEPLOYMENT_CAPABILITY:
            raise PermissionError("request is not the Production deployment capability")
        if original_request.requested_mode != "execute":
            raise PermissionError("Production deployment must request execute authority")
        if original_request.client_id is not None:
            raise PermissionError("Production deployment approval is MSP-scoped, not client-scoped")

        args = dict(original_request.arguments)
        if args.get("target_environment") != PRODUCTION_TARGET:
            raise PermissionError("orchestration target is not Production")
        if args.get("promotion_id") != promotion_id:
            raise PermissionError("orchestration promotion ID mismatch")
        if args.get("plan_sha256") != digest:
            raise PermissionError("orchestration plan fingerprint mismatch")

        request = self.approval_requests.get(accepted.approval_id)
        if request is None:
            raise PermissionError("Production approval request is not registered")
        if request.status is not ApprovalRequestStatus.APPROVED:
            raise PermissionError("Production approval request is not approved")
        if current >= request.expires_at or current >= accepted.expires_at:
            raise PermissionError("Production approval has expired")

        metadata = request.metadata
        if metadata.get(PROMOTION_ID_KEY) != promotion_id:
            raise PermissionError("approved promotion ID does not match apply request")
        if metadata.get(PLAN_SHA256_KEY) != digest:
            raise PermissionError("approved plan fingerprint does not match apply request")
        if metadata.get(TARGET_ENVIRONMENT_KEY) != PRODUCTION_TARGET:
            raise PermissionError("approved target environment is not Production")
        if metadata.get(AUTHORITY_CLASS_KEY) != "owner":
            raise PermissionError("Production approval is not Owner-authorized")

        resumed = self.resume_bridge.resume(
            original_request=original_request,
            accepted=accepted,
            authentication_assurance=authentication_assurance,
        )
        if not resumed.authority_context_id:
            raise PermissionError("JKD-001 did not issue an authority context")

        self.continuation_guard.claim(
            ApprovalContinuationClaim(
                approval_id=accepted.approval_id,
                organization_id=accepted.organization_id,
                request_id=accepted.request_id,
                correlation_id=original_request.correlation_id,
                capability=original_request.capability_name,
                authority_context_id=resumed.authority_context_id,
                claimed_at=current,
            )
        )
        return resumed, ProductionPromotionAuthorization(
            approval_id=accepted.approval_id,
            promotion_id=promotion_id,
            plan_sha256=digest,
            authority_context_id=resumed.authority_context_id,
            decided_by=accepted.decided_by,
            expires_at=accepted.expires_at,
        )
