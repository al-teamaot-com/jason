from __future__ import annotations

from datetime import datetime, timedelta, timezone

from kernel.identity_authority import (
    ApprovalRecord,
    AuthorityGrant,
    AuthorityOutcome,
    AuthorityRequest,
    ContextValidationRequest,
    ExecutionContextValidator,
    IdentityAuthorityService,
    IdentityRecord,
    InMemoryApprovalRepository,
    InMemoryAuthorityGrantRepository,
    InMemoryIdentityRepository,
    PermissionMode,
    SQLiteApprovalRepository,
    SQLiteAuthorityGrantRepository,
    SQLiteIdentityAuthorityStore,
    SQLiteIdentityRepository,
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
    assert result.execution_context.expires_at == NOW + timedelta(minutes=5)


def test_cross_client_scope_fails_closed():
    result = service(grant=grant(client_id="client-2")).evaluate(request(client_id="client-1"))
    assert result.outcome is AuthorityOutcome.DENIED
    assert result.reason_codes == ("NO_MATCHING_AUTHORITY_GRANT",)


def test_higher_requested_mode_is_limited_to_grant_ceiling():
    result = service(grant=grant(PermissionMode.RECOMMEND)).evaluate(request(PermissionMode.EXECUTE))
    assert result.outcome is AuthorityOutcome.ALLOWED_LIMITED
    assert result.maximum_mode is PermissionMode.RECOMMEND


def test_approval_required_without_record_stops_execution():
    result = service(grant=grant(PermissionMode.EXECUTE, approval_required=True)).evaluate(request(PermissionMode.EXECUTE))
    assert result.outcome is AuthorityOutcome.APPROVAL_REQUIRED
    assert result.execution_context is None


def test_valid_formal_approval_allows_execution():
    approval = ApprovalRecord(
        approval_id="apr-1", request_id="req-1", capability="autotask.ticket.get",
        organization_id="aot", client_id="client-1", requested_by="person-al",
        status="approved", decided_by="person-manager",
        decided_at=NOW - timedelta(minutes=1), expires_at=NOW + timedelta(minutes=10),
    )
    result = service(grant=grant(PermissionMode.EXECUTE, approval_required=True), approval=approval).evaluate(
        request(PermissionMode.EXECUTE, approval_id="apr-1")
    )
    assert result.outcome is AuthorityOutcome.ALLOWED
    assert result.execution_context is not None
    assert result.execution_context.approval_required is True


def test_missing_identity_is_indeterminate_and_fails_closed():
    result = IdentityAuthorityService(
        identities=InMemoryIdentityRepository(),
        grants=InMemoryAuthorityGrantRepository(),
        approvals=InMemoryApprovalRepository(),
        clock=lambda: NOW,
    ).evaluate(request())
    assert result.outcome is AuthorityOutcome.INDETERMINATE


def test_durable_store_persists_context_and_audit_and_supports_revocation(tmp_path):
    store = SQLiteIdentityAuthorityStore(tmp_path / "authority.db")
    identities = SQLiteIdentityRepository(store)
    grants = SQLiteAuthorityGrantRepository(store)
    approvals = SQLiteApprovalRepository(store)
    identities.put(IdentityRecord("person-al", "person", "aot"))
    grants.put(grant(PermissionMode.EXECUTE))

    authority = IdentityAuthorityService(
        identities=identities,
        grants=grants,
        approvals=approvals,
        contexts=store,
        audit=store,
        clock=lambda: NOW,
    )
    decision = authority.evaluate(request(PermissionMode.EXECUTE))
    context = decision.execution_context
    assert context is not None
    assert store.get_context(context.context_id) == context

    validator = ExecutionContextValidator(store, clock=lambda: NOW + timedelta(minutes=1))
    validation = validator.validate(ContextValidationRequest(
        context_id=context.context_id,
        correlation_id="corr-1",
        principal_id="person-al",
        organization_id="aot",
        client_id="client-1",
        capability="autotask.ticket.get",
        requested_mode=PermissionMode.EXECUTE,
    ))
    assert validation.valid is True

    assert store.revoke_context(
        context.context_id,
        revoked_at=NOW + timedelta(minutes=2),
        reason="operator_revoked",
    ) is True
    revoked = validator.validate(ContextValidationRequest(
        context_id=context.context_id,
        correlation_id="corr-1",
        principal_id="person-al",
        organization_id="aot",
        client_id="client-1",
        capability="autotask.ticket.get",
        requested_mode=PermissionMode.EXECUTE,
    ))
    assert revoked.valid is False
    assert revoked.reason_code == "EXECUTION_CONTEXT_REVOKED"


def test_durable_context_rejects_scope_reuse(tmp_path):
    store = SQLiteIdentityAuthorityStore(tmp_path / "authority.db")
    identities = SQLiteIdentityRepository(store)
    grants = SQLiteAuthorityGrantRepository(store)
    identities.put(IdentityRecord("person-al", "person", "aot"))
    grants.put(grant())
    authority = IdentityAuthorityService(
        identities=identities,
        grants=grants,
        approvals=SQLiteApprovalRepository(store),
        contexts=store,
        audit=store,
        clock=lambda: NOW,
    )
    context = authority.evaluate(request()).execution_context
    assert context is not None
    validator = ExecutionContextValidator(store, clock=lambda: NOW)
    result = validator.validate(ContextValidationRequest(
        context_id=context.context_id,
        correlation_id="corr-1",
        principal_id="person-al",
        organization_id="aot",
        client_id="different-client",
        capability="autotask.ticket.get",
        requested_mode=PermissionMode.OBSERVE,
    ))
    assert result.valid is False
    assert result.reason_code == "EXECUTION_CONTEXT_SCOPE_MISMATCH"


def test_organization_policy_subject_can_supply_matching_authority() -> None:
    identities = InMemoryIdentityRepository()
    identities.put(IdentityRecord("person-al", "person", "aot"))

    grants = InMemoryAuthorityGrantRepository()
    grants.put(
        AuthorityGrant(
            grant_id="grant-aot-policy",
            subject_id="organization:aot",
            capability="endpoint.device.search",
            organization_id="aot",
            client_id="client-1",
            permission=PermissionMode.OBSERVE,
        )
    )

    service = IdentityAuthorityService(
        identities=identities,
        grants=grants,
        approvals=InMemoryApprovalRepository(),
    )

    result = service.evaluate(
        AuthorityRequest(
            request_id="req-org-policy-1",
            correlation_id="corr-org-policy-1",
            principal_id="person-al",
            organization_id="aot",
            client_id="client-1",
            capability="endpoint.device.search",
            requested_mode=PermissionMode.OBSERVE,
            authentication_assurance="high",
        )
    )

    assert result.outcome is AuthorityOutcome.ALLOWED
    assert result.matched_grants == ("grant-aot-policy",)


def test_other_organization_policy_subject_does_not_grant_authority() -> None:
    identities = InMemoryIdentityRepository()
    identities.put(IdentityRecord("person-al", "person", "aot"))

    grants = InMemoryAuthorityGrantRepository()
    grants.put(
        AuthorityGrant(
            grant_id="grant-other-policy",
            subject_id="organization:other",
            capability="endpoint.device.search",
            organization_id="aot",
            client_id="client-1",
            permission=PermissionMode.OBSERVE,
        )
    )

    service = IdentityAuthorityService(
        identities=identities,
        grants=grants,
        approvals=InMemoryApprovalRepository(),
    )

    result = service.evaluate(
        AuthorityRequest(
            request_id="req-other-org-policy-1",
            correlation_id="corr-other-org-policy-1",
            principal_id="person-al",
            organization_id="aot",
            client_id="client-1",
            capability="endpoint.device.search",
            requested_mode=PermissionMode.OBSERVE,
            authentication_assurance="high",
        )
    )

    assert result.outcome is AuthorityOutcome.DENIED
    assert result.reason_codes == ("NO_MATCHING_AUTHORITY_GRANT",)
