from __future__ import annotations

from datetime import datetime, timedelta, timezone

from kernel.identity_authority import (
    ApprovalRecord,
    AuthorityGrant,
    AuthorityOutcome,
    AuthorityRequest,
    IdentityAuthorityService,
    IdentityRecord,
    InMemoryApprovalRepository,
    InMemoryAuthorityGrantRepository,
    InMemoryIdentityRepository,
    PermissionMode,
)

NOW = datetime(2026, 8, 8, 21, 30, tzinfo=timezone.utc)


def service(*, grant: AuthorityGrant, approval: ApprovalRecord | None = None):
    identities = InMemoryIdentityRepository()
    identities.put(IdentityRecord("person-al", "person", "aot"))
    grants = InMemoryAuthorityGrantRepository()
    grants.put(grant)
    approvals = InMemoryApprovalRepository()
    if approval is not None:
        approvals.put(approval)
    return IdentityAuthorityService(
        identities=identities,
        grants=grants,
        approvals=approvals,
        clock=lambda: NOW,
    )


def request(mode=PermissionMode.OBSERVE, approval_id=None, client_id="client-1"):
    return AuthorityRequest(
        request_id="req-1",
        correlation_id="corr-1",
        principal_id="person-al",
        organization_id="aot",
        client_id=client_id,
        capability="autotask.ticket.get",
        requested_mode=mode,
        authentication_assurance="high",
        approval_id=approval_id,
    )


def grant(permission=PermissionMode.OBSERVE, approval_required=False, client_id="client-1"):
    return AuthorityGrant(
        grant_id="grant-1",
        subject_id="person-al",
        capability="autotask.ticket.get",
        organization_id="aot",
        client_id=client_id,
        permission=permission,
        approval_required=approval_required,
        effective_from=NOW - timedelta(minutes=1),
        effective_until=NOW + timedelta(hours=1),
    )


def test_allowed_request_issues_short_lived_execution_context():
    result = service(grant=grant()).evaluate(request())

    assert result.outcome is AuthorityOutcome.ALLOWED
    assert result.execution_context is not None
    assert result.execution_context.principal_id == "person-al"
    assert result.execution_context.client_id == "client-1"
    assert result.execution_context.capability == "autotask.ticket.get"
    assert result.execution_context.expires_at == NOW + timedelta(minutes=5)


def test_cross_client_scope_fails_closed():
    result = service(grant=grant(client_id="client-2")).evaluate(request(client_id="client-1"))
    assert result.outcome is AuthorityOutcome.DENIED
    assert result.reason_codes == ("NO_MATCHING_AUTHORITY_GRANT",)


def test_higher_requested_mode_is_limited_to_grant_ceiling():
    result = service(grant=grant(PermissionMode.RECOMMEND)).evaluate(
        request(PermissionMode.EXECUTE)
    )
    assert result.outcome is AuthorityOutcome.ALLOWED_LIMITED
    assert result.maximum_mode is PermissionMode.RECOMMEND
    assert result.execution_context is not None


def test_approval_required_without_record_stops_execution():
    result = service(
        grant=grant(PermissionMode.EXECUTE, approval_required=True)
    ).evaluate(request(PermissionMode.EXECUTE))
    assert result.outcome is AuthorityOutcome.APPROVAL_REQUIRED
    assert result.execution_context is None


def test_valid_formal_approval_allows_execution():
    approval = ApprovalRecord(
        approval_id="apr-1",
        request_id="req-1",
        capability="autotask.ticket.get",
        organization_id="aot",
        client_id="client-1",
        requested_by="person-al",
        status="approved",
        decided_by="person-manager",
        decided_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=10),
    )
    result = service(
        grant=grant(PermissionMode.EXECUTE, approval_required=True),
        approval=approval,
    ).evaluate(request(PermissionMode.EXECUTE, approval_id="apr-1"))
    assert result.outcome is AuthorityOutcome.ALLOWED
    assert result.execution_context is not None
    assert result.execution_context.approval_required is True


def test_expired_or_wrong_approval_is_denied():
    approval = ApprovalRecord(
        approval_id="apr-1",
        request_id="different-request",
        capability="autotask.ticket.get",
        organization_id="aot",
        client_id="client-1",
        requested_by="person-al",
        status="approved",
        decided_by="person-manager",
        decided_at=NOW - timedelta(minutes=2),
        expires_at=NOW + timedelta(minutes=10),
    )
    result = service(
        grant=grant(PermissionMode.EXECUTE, approval_required=True),
        approval=approval,
    ).evaluate(request(PermissionMode.EXECUTE, approval_id="apr-1"))
    assert result.outcome is AuthorityOutcome.DENIED
    assert result.reason_codes == ("APPROVAL_INVALID",)


def test_missing_identity_is_indeterminate_and_fails_closed():
    identities = InMemoryIdentityRepository()
    grants = InMemoryAuthorityGrantRepository()
    approvals = InMemoryApprovalRepository()
    result = IdentityAuthorityService(
        identities=identities,
        grants=grants,
        approvals=approvals,
        clock=lambda: NOW,
    ).evaluate(request())
    assert result.outcome is AuthorityOutcome.INDETERMINATE
