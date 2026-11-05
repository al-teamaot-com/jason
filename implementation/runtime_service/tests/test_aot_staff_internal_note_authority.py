import pytest

from kernel.identity_authority import (
    AuthorityGrant, IdentityAuthorityService, InMemoryIdentityRepository,
    InMemoryAuthorityGrantRepository, InMemoryApprovalRepository, PermissionMode,
)
from jason_runtime.aot_staff_internal_note_authority import (
    AOT_STAFF_INTERNAL_NOTE_GRANT_ID, AOT_STAFF_INTERNAL_NOTE_PROFILE,
    AOT_STAFF_INTERNAL_NOTE_PROFILE_ENV,
    configured_aot_staff_internal_note_write,
    ensure_aot_staff_internal_note_authority,
)
from orchestrator.provider_read_authority import AOT_STAFF_INTERNAL_NOTE_POLICY


def authority():
    return IdentityAuthorityService(
        identities=InMemoryIdentityRepository(),
        grants=InMemoryAuthorityGrantRepository(),
        approvals=InMemoryApprovalRepository(),
    )


def test_staff_note_profile_is_explicitly_opt_in(monkeypatch):
    monkeypatch.delenv(AOT_STAFF_INTERNAL_NOTE_PROFILE_ENV, raising=False)
    assert not configured_aot_staff_internal_note_write()
    monkeypatch.setenv(AOT_STAFF_INTERNAL_NOTE_PROFILE_ENV, "true")
    assert not configured_aot_staff_internal_note_write()
    monkeypatch.setenv(AOT_STAFF_INTERNAL_NOTE_PROFILE_ENV, AOT_STAFF_INTERNAL_NOTE_PROFILE)
    assert configured_aot_staff_internal_note_write()


def test_staff_note_grant_is_idempotent_approval_required_and_exact():
    service = authority()
    assert not ensure_aot_staff_internal_note_authority(service, enabled=False)
    assert service.grants.get(AOT_STAFF_INTERNAL_NOTE_GRANT_ID) is None
    assert ensure_aot_staff_internal_note_authority(service, enabled=True)
    assert not ensure_aot_staff_internal_note_authority(service, enabled=True)
    grant = service.grants.get(AOT_STAFF_INTERNAL_NOTE_GRANT_ID)
    assert grant.subject_id == "organization:aot"
    assert grant.capability == AOT_STAFF_INTERNAL_NOTE_POLICY
    assert grant.organization_id == "aot"
    assert grant.client_id is None
    assert grant.permission is PermissionMode.EXECUTE
    assert grant.approval_required is True
    assert grant.status == "active"


def test_grant_conflict_fails_closed():
    service = authority()
    conflict = AuthorityGrant(
        AOT_STAFF_INTERNAL_NOTE_GRANT_ID, "organization:aot",
        AOT_STAFF_INTERNAL_NOTE_POLICY, "aot", None,
        PermissionMode.EXECUTE, approval_required=False,
    )
    service.grants.put(conflict)
    with pytest.raises(RuntimeError, match="conflicts"):
        ensure_aot_staff_internal_note_authority(service, enabled=True)
    assert service.grants.get(AOT_STAFF_INTERNAL_NOTE_GRANT_ID) == conflict


# Governed capability matcher acceptance / negative cases.

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from kernel.execution_providers import ProviderApproval, ProviderLifecycle, ProviderType
from kernel.identity_authority import (
    ApprovalRecord, AuthorityGrant, AuthorityOutcome, AuthorityRequest,
    IdentityAuthorityService, IdentityRecord, InMemoryIdentityRepository,
    InMemoryAuthorityGrantRepository, InMemoryApprovalRepository, PermissionMode,
)
from orchestrator.provider_read_authority import (
    AOT_STAFF_INTERNAL_NOTE_POLICY, GovernedProviderReadAuthorityMatcher,
)

NOTE = "service.ticket.note.create"


class Capabilities:
    def __init__(self):
        self.active = True
        self.metadata = {
            "write_capability": "true",
            "mcp_action_enabled": "true",
            "conversation_authenticated_imperative_is_approval": "true",
        }

    def get_current(self, *, capability_name):
        from kernel.capabilities.repository import CapabilityNotFoundError
        if capability_name != NOTE:
            raise CapabilityNotFoundError(capability_name)
        return SimpleNamespace(
            lifecycle_status=SimpleNamespace(value="active" if self.active else "building"),
            metadata=self.metadata,
            approval=SimpleNamespace(required=True),
        )


class Providers:
    def __init__(self):
        self.active = True
        self.provider_id = "autotask_internal_note"
        self.approval_status = ProviderApproval.PILOT
        self.provider_type = ProviderType.EXTERNAL_CONNECTOR

    def list_all(self):
        return (SimpleNamespace(
            provider_id=self.provider_id, capabilities=frozenset({NOTE}),
            provider_type=self.provider_type,
            lifecycle_status=ProviderLifecycle.AVAILABLE if self.active else ProviderLifecycle.PLANNED,
            approval_status=self.approval_status,
        ),)


def make_service(*, enabled=True, approval_required=True):
    identities = InMemoryIdentityRepository()
    for principal, kind, org, status in (
        ("tech", "human", "aot", "active"),
        ("frontdesk", "person", "aot", "active"),
        ("automation", "service", "aot", "active"),
        ("disabled", "person", "aot", "disabled"),
        ("external", "human", "other", "active"),
    ):
        identities.put(IdentityRecord(principal, kind, org, status))
    caps = Capabilities()
    providers = Providers()
    grants = InMemoryAuthorityGrantRepository()
    grants.put(AuthorityGrant(
        "staff-note-grant", "organization:aot", AOT_STAFF_INTERNAL_NOTE_POLICY,
        "aot", None, PermissionMode.EXECUTE, approval_required=approval_required,
    ))
    approvals = InMemoryApprovalRepository()
    service = IdentityAuthorityService(
        identities=identities, grants=grants, approvals=approvals,
        capability_matcher=GovernedProviderReadAuthorityMatcher(
            caps, providers, identities,
            routine_write_enabled=False,
            internal_note_write_enabled=enabled,
        ),
    )
    return service, caps, providers, approvals


def decide(service, *, principal="tech", capability=NOTE, organization="aot",
           client=None, mode=PermissionMode.EXECUTE, approval_id=None):
    return service.evaluate(AuthorityRequest(
        "req-note", "corr-note", principal, organization, client,
        capability, mode, "entra-oauth-bearer", approval_id=approval_id,
    ))


@pytest.mark.parametrize("principal", ["tech", "frontdesk"])
def test_active_aot_humans_get_approval_required_then_exact_allow(principal):
    service, _, _, approvals = make_service()
    initial = decide(service, principal=principal)
    assert initial.outcome is AuthorityOutcome.APPROVAL_REQUIRED
    assert initial.matched_grants == ("staff-note-grant",)
    approvals.put(ApprovalRecord(
        "approval-note", "req-note", NOTE, "aot", None, principal,
        "approved", principal, datetime.now(timezone.utc),
        datetime.now(timezone.utc) + timedelta(minutes=5),
    ))
    approved = decide(service, principal=principal, approval_id="approval-note")
    assert approved.outcome is AuthorityOutcome.ALLOWED
    assert approved.execution_context.approval_required is True


def test_disabled_profile_denies_even_with_persisted_grant():
    service, _, _, _ = make_service(enabled=False)
    assert decide(service).outcome is AuthorityOutcome.DENIED


@pytest.mark.parametrize("principal", ["automation", "disabled", "external", "missing"])
def test_nonhuman_disabled_external_and_missing_principals_denied(principal):
    service, _, _, _ = make_service()
    assert decide(service, principal=principal).outcome in (
        AuthorityOutcome.DENIED, AuthorityOutcome.INDETERMINATE,
    )


@pytest.mark.parametrize("capability", [
    "service.ticket.create", "service.ticket.update", "service.ticket.note.update",
    "service.ticket.client.notification.create", "service.purchase.order.create",
    "automation.component.execute",
])
def test_staff_note_grant_cannot_mutate_anything_else(capability):
    service, _, _, _ = make_service()
    assert decide(service, capability=capability).outcome is AuthorityOutcome.DENIED


@pytest.mark.parametrize("kwargs", [
    {"organization": "other"},
    {"client": "other-client"},
    {"mode": PermissionMode.OBSERVE},
    {"mode": PermissionMode.ADMINISTER},
])
def test_wrong_scope_or_permission_denied(kwargs):
    service, _, _, _ = make_service()
    assert decide(service, **kwargs).outcome is AuthorityOutcome.DENIED


def test_rejects_grant_configured_without_approval():
    service, _, _, _ = make_service(approval_required=False)
    assert decide(service).outcome is AuthorityOutcome.DENIED


@pytest.mark.parametrize("field", [
    "write_capability", "mcp_action_enabled",
    "conversation_authenticated_imperative_is_approval",
])
def test_active_capability_and_imperative_requirement_not_optional(field):
    service, caps, _, _ = make_service()
    caps.metadata = {**caps.metadata, field: "false"}
    assert decide(service).outcome is AuthorityOutcome.DENIED


def test_provider_lifecycle_and_identity_fails_closed():
    service, caps, providers, _ = make_service()
    caps.active = False
    assert decide(service).outcome is AuthorityOutcome.DENIED
    caps.active = True
    providers.active = False
    assert decide(service).outcome is AuthorityOutcome.DENIED
    providers.active = True
    providers.provider_id = "unrelated_provider"
    assert decide(service).outcome is AuthorityOutcome.DENIED
    providers.provider_id = "autotask_internal_note"
    providers.approval_status = ProviderApproval.BLOCKED
    assert decide(service).outcome is AuthorityOutcome.DENIED


def test_real_denial_code_then_two_distinct_technicians_require_own_approval():
    """Regression for the observed production NO_MATCHING_AUTHORITY_GRANT.

    These named personas are deterministic stand-ins for two separately signed-in
    staff members. This is source validation, never evidence of live sign-ins.
    """
    service, caps, providers, approvals = make_service(enabled=False)
    for principal in ("tech", "frontdesk"):
        denied = decide(service, principal=principal)
        assert denied.outcome is AuthorityOutcome.DENIED
        assert denied.reason_codes == ("NO_MATCHING_AUTHORITY_GRANT",)

    service.capability_matcher = GovernedProviderReadAuthorityMatcher(
        caps, providers, service.identities,
        routine_write_enabled=False,
        internal_note_write_enabled=True,
    )
    expires = datetime.now(timezone.utc) + timedelta(minutes=5)
    for principal, approval_id in (("tech", "approval-tech"),
                                   ("frontdesk", "approval-frontdesk")):
        assert decide(service, principal=principal).outcome is AuthorityOutcome.APPROVAL_REQUIRED
        approvals.put(ApprovalRecord(
            approval_id, "req-note", NOTE, "aot", None, principal,
            "approved", principal, datetime.now(timezone.utc), expires,
        ))
        own = decide(service, principal=principal, approval_id=approval_id)
        assert own.outcome is AuthorityOutcome.ALLOWED
        assert own.execution_context.principal_id == principal
        assert own.execution_context.approval_required is True

    # A real human's approval must not authorize a different signed-in human.
    for principal, other in (("tech", "approval-frontdesk"),
                             ("frontdesk", "approval-tech")):
        cross = decide(service, principal=principal, approval_id=other)
        assert cross.outcome is AuthorityOutcome.DENIED
        assert cross.reason_codes == ("APPROVAL_INVALID",)

    # The opt-in flag remains a second independent kill switch even if the
    # durable approval and organization-level grant still exist.
    service.capability_matcher = GovernedProviderReadAuthorityMatcher(
        caps, providers, service.identities,
        routine_write_enabled=False,
        internal_note_write_enabled=False,
    )
    for principal, approval_id in (("tech", "approval-tech"),
                                   ("frontdesk", "approval-frontdesk")):
        denied = decide(service, principal=principal, approval_id=approval_id)
        assert denied.outcome is AuthorityOutcome.DENIED
        assert denied.reason_codes == ("NO_MATCHING_AUTHORITY_GRANT",)
