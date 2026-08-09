"""Provider-neutral approval request contracts and validation for Project Jason.

Approval channels may deliver requests and return authenticated response metadata,
but they never become the authority. The caller must provide an authority checker
owned by Jason and must persist accepted approvals through the governed authority
repository before execution can continue.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol


class ApprovalRequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ApprovalDecision(StrEnum):
    APPROVE = "approve"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class ApprovalEvidenceReference:
    artifact_id: str
    organization_id: str
    content_sha256: str

    def validate(self) -> None:
        if not self.artifact_id.strip() or not self.organization_id.strip():
            raise ValueError("approval evidence reference identifiers must be non-empty")
        if len(self.content_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.content_sha256.lower()):
            raise ValueError("approval evidence reference requires a SHA-256 digest")


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    approval_id: str
    request_id: str
    correlation_id: str
    organization_id: str
    client_id: str | None
    requested_by: str
    capability: str
    requested_mode: str
    requested_at: datetime
    expires_at: datetime
    authorized_approver_ids: tuple[str, ...]
    evidence_references: tuple[ApprovalEvidenceReference, ...] = ()
    status: ApprovalRequestStatus = ApprovalRequestStatus.PENDING

    def validate(self) -> None:
        required = {
            "approval_id": self.approval_id,
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "organization_id": self.organization_id,
            "requested_by": self.requested_by,
            "capability": self.capability,
            "requested_mode": self.requested_mode,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(f"missing approval request fields: {', '.join(sorted(missing))}")
        if self.requested_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("approval timestamps must be timezone-aware")
        if self.expires_at <= self.requested_at:
            raise ValueError("approval expiration must be after request time")
        if not self.authorized_approver_ids or any(not value.strip() for value in self.authorized_approver_ids):
            raise ValueError("at least one authorized approver identity is required")
        if len(set(self.authorized_approver_ids)) != len(self.authorized_approver_ids):
            raise ValueError("authorized approver identities must be unique")
        for reference in self.evidence_references:
            reference.validate()
            if reference.organization_id != self.organization_id:
                raise ValueError("approval evidence organization must match approval organization")


@dataclass(frozen=True, slots=True)
class ApprovalResponse:
    approval_id: str
    organization_id: str
    approver_identity_id: str
    decision: ApprovalDecision
    decided_at: datetime
    channel: str
    channel_response_id: str

    def validate(self) -> None:
        for value in (
            self.approval_id,
            self.organization_id,
            self.approver_identity_id,
            self.channel,
            self.channel_response_id,
        ):
            if not value.strip():
                raise ValueError("approval response identifiers must be non-empty")
        if self.decided_at.tzinfo is None:
            raise ValueError("approval response time must be timezone-aware")


@dataclass(frozen=True, slots=True)
class AcceptedApproval:
    approval_id: str
    request_id: str
    capability: str
    organization_id: str
    client_id: str | None
    requested_by: str
    status: str
    decided_by: str
    decided_at: datetime
    expires_at: datetime
    channel: str
    channel_response_id: str
    evidence_references: tuple[ApprovalEvidenceReference, ...]


class ApprovalAuthorityChecker(Protocol):
    def can_approve(
        self,
        *,
        approver_identity_id: str,
        organization_id: str,
        client_id: str | None,
        capability: str,
        requested_mode: str,
    ) -> bool: ...


class ApprovalRequestRepository(Protocol):
    def get(self, approval_id: str) -> ApprovalRequest | None: ...
    def put(self, request: ApprovalRequest) -> None: ...


@dataclass
class InMemoryApprovalRequestRepository:
    records: dict[str, ApprovalRequest] = field(default_factory=dict)

    def get(self, approval_id: str) -> ApprovalRequest | None:
        return self.records.get(approval_id)

    def put(self, request: ApprovalRequest) -> None:
        self.records[request.approval_id] = request


@dataclass
class ApprovalRequestService:
    repository: ApprovalRequestRepository
    authority: ApprovalAuthorityChecker

    def create(self, request: ApprovalRequest, *, now: datetime | None = None) -> ApprovalRequest:
        request.validate()
        current = self._now(now)
        if request.status is not ApprovalRequestStatus.PENDING:
            raise ValueError("new approval requests must start pending")
        if current >= request.expires_at:
            raise ValueError("approval request is already expired")
        if self.repository.get(request.approval_id) is not None:
            raise ValueError("approval_id already exists")
        self.repository.put(request)
        return request

    def accept_response(self, response: ApprovalResponse, *, now: datetime | None = None) -> AcceptedApproval:
        response.validate()
        current = self._now(now)
        request = self.repository.get(response.approval_id)
        if request is None:
            raise ValueError("approval request not found")
        if request.status is not ApprovalRequestStatus.PENDING:
            raise ValueError("approval request is no longer pending")
        if response.organization_id != request.organization_id:
            raise PermissionError("approval response organization mismatch")
        if current >= request.expires_at or response.decided_at >= request.expires_at:
            self.repository.put(replace(request, status=ApprovalRequestStatus.EXPIRED))
            raise PermissionError("approval request expired")
        if response.approver_identity_id not in request.authorized_approver_ids:
            raise PermissionError("responder is not an authorized approver for this request")
        if not self.authority.can_approve(
            approver_identity_id=response.approver_identity_id,
            organization_id=request.organization_id,
            client_id=request.client_id,
            capability=request.capability,
            requested_mode=request.requested_mode,
        ):
            raise PermissionError("Jason authority denied approver authorization")

        final_status = (
            ApprovalRequestStatus.APPROVED
            if response.decision is ApprovalDecision.APPROVE
            else ApprovalRequestStatus.DENIED
        )
        self.repository.put(replace(request, status=final_status))
        return AcceptedApproval(
            approval_id=request.approval_id,
            request_id=request.request_id,
            capability=request.capability,
            organization_id=request.organization_id,
            client_id=request.client_id,
            requested_by=request.requested_by,
            status=final_status.value,
            decided_by=response.approver_identity_id,
            decided_at=response.decided_at.astimezone(timezone.utc),
            expires_at=request.expires_at.astimezone(timezone.utc),
            channel=response.channel,
            channel_response_id=response.channel_response_id,
            evidence_references=request.evidence_references,
        )

    @staticmethod
    def _now(value: datetime | None) -> datetime:
        current = value or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("approval service clock must be timezone-aware")
        return current.astimezone(timezone.utc)
