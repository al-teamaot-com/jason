from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol
from uuid import uuid4

from .contracts import (
    ApprovalRecord,
    AuthorityDecision,
    AuthorityGrant,
    AuthorityOutcome,
    AuthorityRequest,
    ExecutionContext,
    IdentityRecord,
    PermissionMode,
    permission_rank,
)


class IdentityRepository(Protocol):
    def get(self, identity_id: str) -> IdentityRecord | None: ...


class AuthorityGrantRepository(Protocol):
    def list_for_subject(self, subject_id: str) -> tuple[AuthorityGrant, ...]: ...


class ApprovalRepository(Protocol):
    def get(self, approval_id: str) -> ApprovalRecord | None: ...


class ContextRepository(Protocol):
    def put_context(self, context: ExecutionContext) -> None: ...


class AuthorityAuditSink(Protocol):
    def append_authority_audit(
        self,
        *,
        event_type: str,
        correlation_id: str,
        principal_id: str,
        organization_id: str,
        capability: str,
        outcome: str,
        reason_codes: tuple[str, ...],
    ) -> None: ...


@dataclass
class IdentityAuthorityService:
    identities: IdentityRepository
    grants: AuthorityGrantRepository
    approvals: ApprovalRepository
    contexts: ContextRepository | None = None
    audit: AuthorityAuditSink | None = None
    context_lifetime: timedelta = timedelta(minutes=5)
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)

    def evaluate(self, request: AuthorityRequest) -> AuthorityDecision:
        now = self._now()
        identity = self.identities.get(request.principal_id)
        if identity is None:
            return self._finalize(request, AuthorityDecision(
                AuthorityOutcome.INDETERMINATE,
                ("IDENTITY_NOT_FOUND",),
            ))
        if identity.status != "active":
            return self._finalize(request, AuthorityDecision(
                AuthorityOutcome.DENIED,
                ("IDENTITY_INACTIVE",),
            ))
        if identity.organization_id != request.organization_id:
            return self._finalize(request, AuthorityDecision(
                AuthorityOutcome.DENIED,
                ("ORGANIZATION_SCOPE_MISMATCH",),
            ))

        candidates = tuple(
            grant
            for grant in self.grants.list_for_subject(request.principal_id)
            if self._grant_matches(grant, request, now)
        )
        if not candidates:
            return self._finalize(request, AuthorityDecision(
                AuthorityOutcome.DENIED,
                ("NO_MATCHING_AUTHORITY_GRANT",),
            ))

        best = max(candidates, key=lambda grant: permission_rank(grant.permission))
        matched = tuple(sorted(grant.grant_id for grant in candidates))
        requested_rank = permission_rank(request.requested_mode)
        maximum_rank = permission_rank(best.permission)

        if maximum_rank < requested_rank:
            if maximum_rank >= permission_rank(PermissionMode.RECOMMEND):
                return self._context_decision(
                    request=request,
                    now=now,
                    outcome=AuthorityOutcome.ALLOWED_LIMITED,
                    reason_codes=("AUTHORITY_MODE_EXCEEDED",),
                    maximum_mode=best.permission,
                    matched_grants=matched,
                    approval_required=False,
                )
            return self._finalize(request, AuthorityDecision(
                AuthorityOutcome.DENIED,
                ("AUTHORITY_MODE_EXCEEDED",),
                maximum_mode=best.permission,
                matched_grants=matched,
            ))

        approval_required = any(grant.approval_required for grant in candidates)
        if approval_required:
            if request.approval_id is None:
                return self._finalize(request, AuthorityDecision(
                    AuthorityOutcome.APPROVAL_REQUIRED,
                    ("APPROVAL_REQUIRED",),
                    maximum_mode=best.permission,
                    matched_grants=matched,
                ))
            approval = self.approvals.get(request.approval_id)
            if not self._approval_valid(approval, request, now):
                return self._finalize(request, AuthorityDecision(
                    AuthorityOutcome.DENIED,
                    ("APPROVAL_INVALID",),
                    maximum_mode=best.permission,
                    matched_grants=matched,
                ))

        return self._context_decision(
            request=request,
            now=now,
            outcome=AuthorityOutcome.ALLOWED,
            reason_codes=("AUTHORITY_ALLOWED",),
            maximum_mode=best.permission,
            matched_grants=matched,
            approval_required=approval_required,
        )

    @staticmethod
    def _grant_matches(grant: AuthorityGrant, request: AuthorityRequest, now: datetime) -> bool:
        if grant.status != "active" or grant.capability != request.capability:
            return False
        if grant.organization_id != request.organization_id or grant.client_id != request.client_id:
            return False
        if grant.effective_from is not None and now < grant.effective_from:
            return False
        if grant.effective_until is not None and now >= grant.effective_until:
            return False
        return True

    @staticmethod
    def _approval_valid(approval: ApprovalRecord | None, request: AuthorityRequest, now: datetime) -> bool:
        if approval is None or approval.status != "approved":
            return False
        if approval.request_id != request.request_id or approval.capability != request.capability:
            return False
        if approval.organization_id != request.organization_id or approval.client_id != request.client_id:
            return False
        if approval.requested_by != request.principal_id:
            return False
        if approval.expires_at is not None and now >= approval.expires_at:
            return False
        return True

    def _context_decision(
        self,
        *,
        request: AuthorityRequest,
        now: datetime,
        outcome: AuthorityOutcome,
        reason_codes: tuple[str, ...],
        maximum_mode: PermissionMode,
        matched_grants: tuple[str, ...],
        approval_required: bool,
    ) -> AuthorityDecision:
        context = ExecutionContext(
            context_id=f"ctx_{uuid4().hex}",
            correlation_id=request.correlation_id,
            principal_id=request.principal_id,
            organization_id=request.organization_id,
            client_id=request.client_id,
            capability=request.capability,
            requested_mode=request.requested_mode,
            maximum_mode=maximum_mode,
            outcome=outcome,
            approval_required=approval_required,
            matched_grants=matched_grants,
            authentication_assurance=request.authentication_assurance,
            issued_at=now,
            expires_at=now + self.context_lifetime,
        )
        if self.contexts is not None:
            self.contexts.put_context(context)
        return self._finalize(request, AuthorityDecision(
            outcome=outcome,
            reason_codes=reason_codes,
            maximum_mode=maximum_mode,
            matched_grants=matched_grants,
            execution_context=context,
        ))

    def _finalize(self, request: AuthorityRequest, decision: AuthorityDecision) -> AuthorityDecision:
        if self.audit is not None:
            self.audit.append_authority_audit(
                event_type="authority.decision",
                correlation_id=request.correlation_id,
                principal_id=request.principal_id,
                organization_id=request.organization_id,
                capability=request.capability,
                outcome=decision.outcome.value,
                reason_codes=decision.reason_codes,
            )
        return decision

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            raise ValueError("identity authority clock must be timezone-aware")
        return value.astimezone(timezone.utc)
