"""Governed bridge from provider-neutral approvals into JKD-001 and orchestration.

Accepted channel responses are persisted as formal JKD-001 approval records and
re-evaluated for the original requester before orchestration can resume.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable, Protocol

from connectors.src.jason_connectors.approval_requests import AcceptedApproval
from kernel.identity_authority import (
    ApprovalRecord,
    AuthorityGrant,
    AuthorityOutcome,
    AuthorityRequest,
    IdentityAuthorityService,
    IdentityRecord,
    PermissionMode,
)
from kernel.identity_authority.contracts import permission_rank

from .contracts import OrchestrationRequest


class IdentityLookup(Protocol):
    def get(self, identity_id: str) -> IdentityRecord | None: ...


class GrantLookup(Protocol):
    def list_for_subject(self, subject_id: str) -> tuple[AuthorityGrant, ...]: ...


class ApprovalWriter(Protocol):
    def put(self, record: ApprovalRecord) -> None: ...


@dataclass(frozen=True, slots=True)
class JKD001ApprovalAuthorityChecker:
    """Validate whether an authenticated identity may approve an exact request scope."""

    identities: IdentityLookup
    grants: GrantLookup
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)

    def can_approve(
        self,
        *,
        approver_identity_id: str,
        organization_id: str,
        client_id: str | None,
        capability: str,
        requested_mode: str,
    ) -> bool:
        now = self._now()
        identity = self.identities.get(approver_identity_id)
        if identity is None or identity.status != "active" or identity.organization_id != organization_id:
            return False
        try:
            requested = PermissionMode(requested_mode)
        except ValueError:
            return False
        for grant in self.grants.list_for_subject(approver_identity_id):
            if grant.status != "active":
                continue
            if grant.organization_id != organization_id or grant.client_id != client_id:
                continue
            if grant.capability != capability:
                continue
            if grant.effective_from is not None and now < grant.effective_from:
                continue
            if grant.effective_until is not None and now >= grant.effective_until:
                continue
            if permission_rank(grant.permission) < permission_rank(PermissionMode.REQUEST_APPROVAL):
                continue
            if permission_rank(grant.permission) < permission_rank(requested):
                continue
            return True
        return False

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            raise ValueError("approval authority clock must be timezone-aware")
        return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class ApprovalResumeBridge:
    """Persist a formal approval and ask JKD-001 for fresh execution authority."""

    approvals: ApprovalWriter
    authority: IdentityAuthorityService

    def resume(
        self,
        *,
        original_request: OrchestrationRequest,
        accepted: AcceptedApproval,
        authentication_assurance: str,
    ) -> OrchestrationRequest:
        if accepted.status != "approved":
            raise PermissionError("only approved responses may resume execution")
        if accepted.request_id != original_request.execution_id:
            raise PermissionError("approval request does not match orchestration execution")
        if accepted.organization_id != original_request.organization_id:
            raise PermissionError("approval organization does not match orchestration request")
        if accepted.client_id != original_request.client_id:
            raise PermissionError("approval client does not match orchestration request")
        if accepted.requested_by != original_request.principal_id:
            raise PermissionError("approval requester does not match orchestration principal")
        if accepted.capability != original_request.capability_name:
            raise PermissionError("approval capability does not match orchestration capability")
        if not authentication_assurance.strip():
            raise ValueError("authentication_assurance must be non-empty")

        self.approvals.put(ApprovalRecord(
            approval_id=accepted.approval_id,
            request_id=accepted.request_id,
            capability=accepted.capability,
            organization_id=accepted.organization_id,
            client_id=accepted.client_id,
            requested_by=accepted.requested_by,
            status="approved",
            decided_by=accepted.decided_by,
            decided_at=accepted.decided_at,
            expires_at=accepted.expires_at,
        ))
        try:
            mode = PermissionMode(original_request.requested_mode)
        except ValueError as exc:
            raise PermissionError("orchestration requested mode is not a JKD-001 mode") from exc
        decision = self.authority.evaluate(AuthorityRequest(
            request_id=original_request.execution_id,
            correlation_id=original_request.correlation_id,
            principal_id=original_request.principal_id,
            organization_id=original_request.organization_id,
            client_id=original_request.client_id,
            capability=original_request.capability_name,
            requested_mode=mode,
            authentication_assurance=authentication_assurance,
            approval_id=accepted.approval_id,
        ))
        if decision.outcome is not AuthorityOutcome.ALLOWED or decision.execution_context is None:
            raise PermissionError("JKD-001 did not issue execution authority after approval")
        return replace(
            original_request,
            authority_allowed=True,
            approval_present=True,
            authority_context_id=decision.execution_context.context_id,
        )
