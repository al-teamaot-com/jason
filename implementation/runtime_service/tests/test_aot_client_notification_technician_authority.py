"""Source-only security regression for opt-in approved client notifications.

No actual Autotask mutation, Teams message, host credential, or live grant.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from kernel.capabilities.repository import CapabilityNotFoundError
from kernel.execution_providers import (
    ProviderApproval,
    ProviderLifecycle,
    ProviderType,
)
from kernel.identity_authority import (
    ApprovalRecord,
    AuthorityGrant,
    AuthorityOutcome,
    AuthorityRequest,
    IdentityAuthorityService,
    IdentityRecord,
    InMemoryAuthorityGrantRepository,
    InMemoryApprovalRepository,
    InMemoryIdentityRepository,
    PermissionMode,
)
from orchestrator.provider_read_authority import (
    AOT_APPROVED_CLIENT_NOTIFICATION_CAPABILITY as CAPABILITY,
    AOT_APPROVED_CLIENT_NOTIFICATION_POLICY as POLICY,
    AOT_APPROVED_CLIENT_NOTIFICATION_PROVIDER as PROVIDER,
    GovernedProviderReadAuthorityMatcher,
)
from jason_runtime.aot_client_notification_authority import (
    AOT_CLIENT_NOTIFICATION_PROVIDER_PROFILE,
    AOT_CLIENT_NOTIFICATION_PROVIDER_PROFILE_ENV,
    AOT_CLIENT_NOTIFICATION_TECH_GRANT_ID,
    AOT_CLIENT_NOTIFICATION_TECH_PROFILE,
    AOT_CLIENT_NOTIFICATION_TECH_PROFILE_ENV,
    configured_aot_client_notification_technician_write,
    ensure_aot_client_notification_technician_authority,
)

class Capabilities:
    def __init__(self):
        self.active = True
        self.metadata = {
            "write_capability": "true",
            "mcp_action_enabled": "true",
            "conversation_authenticated_imperative_is_approval": "true",
            "profile": AOT_CLIENT_NOTIFICATION_PROVIDER_PROFILE,
            "workflow_template_binding": "source_controlled_exact_pair",
            "recipient_source": "authoritative_autotask_contact",
        }
        self.approval_required = True

    def get_current(self, *, capability_name):
        if capability_name != CAPABILITY:
            raise CapabilityNotFoundError(capability_name)
        return SimpleNamespace(
            lifecycle_status=SimpleNamespace(
                value="active" if self.active else "building",
            ),
            approval=SimpleNamespace(required=self.approval_required),
            metadata=self.metadata,
        )


class Providers:
    def __init__(self):
        self.provider_id = PROVIDER
        self.provider_type = ProviderType.EXTERNAL_CONNECTOR
        self.active = True
        self.approved = ProviderApproval.APPROVED

    def list_all(self):
        return (
            SimpleNamespace(
                provider_id=self.provider_id,
                capabilities=frozenset({CAPABILITY}),
                provider_type=self.provider_type,
                lifecycle_status=(
                    ProviderLifecycle.AVAILABLE
                    if self.active else ProviderLifecycle.PLANNED
                ),
                approval_status=self.approved,
            ),
        )


class Case:
    def __init__(self, *, enabled=True, grant_approval_required=True):
        self.identities = InMemoryIdentityRepository()
        for who, kind, org, status in (
            ("tech", "human", "aot", "active"),
            ("other-tech", "person", "aot", "active"),
            ("admin", "human", "aot", "active"),
            ("service", "service", "aot", "active"),
            ("disabled", "human", "aot", "disabled"),
            ("outsider", "human", "other", "active"),
        ):
            self.identities.put(IdentityRecord(who, kind, org, status))
        self.caps = Capabilities()
        self.providers = Providers()
        self.grants = InMemoryAuthorityGrantRepository()
        self.grants.put(AuthorityGrant(
            AOT_CLIENT_NOTIFICATION_TECH_GRANT_ID,
            "organization:aot",
            POLICY, "aot", None,
            PermissionMode.EXECUTE,
            approval_required=grant_approval_required,
        ))
        self.approvals = InMemoryApprovalRepository()
        self.service = IdentityAuthorityService(
            identities=self.identities,
            grants=self.grants,
            approvals=self.approvals,
            capability_matcher=GovernedProviderReadAuthorityMatcher(
                capabilities=self.caps,
                providers=self.providers,
                identities=self.identities,
                approved_client_notification_write_enabled=enabled,
                privileged_admin_principal_ids=frozenset({"admin"}),
            ),
        )

    def decide(self, *, who="tech", capability=CAPABILITY, org="aot", client=None,
               approval_id=None, request_id="xyz-notification-141431",
               mode=PermissionMode.EXECUTE, assurance="entra-oauth-bearer"):
        return self.service.evaluate(AuthorityRequest(
            request_id, "corr-xyz-notification", who, org, client, capability,
            mode, assurance, approval_id=approval_id,
        ))

    def approve(self, *, who="tech", approval_id="app-xyz-test",
                request_id="xyz-notification-141431", client=None,
                expires_at=None):
        now = datetime.now(timezone.utc)
        self.approvals.put(ApprovalRecord(
            approval_id, request_id, CAPABILITY, "aot", client,
            who, "approved", who, now,
            expires_at if expires_at is not None else now + timedelta(minutes=5),
        ))
        return approval_id


def test_standing_authority_needs_two_independent_activation_profiles(monkeypatch):
    for key in (
        AOT_CLIENT_NOTIFICATION_PROVIDER_PROFILE_ENV,
        AOT_CLIENT_NOTIFICATION_TECH_PROFILE_ENV,
    ):
        monkeypatch.delenv(key, raising=False)
    assert not configured_aot_client_notification_technician_write()
    values = (
        (AOT_CLIENT_NOTIFICATION_PROVIDER_PROFILE_ENV,
         AOT_CLIENT_NOTIFICATION_PROVIDER_PROFILE),
        (AOT_CLIENT_NOTIFICATION_TECH_PROFILE_ENV,
         AOT_CLIENT_NOTIFICATION_TECH_PROFILE),
    )
    for index in range(len(values)):
        for key, value in values:
            monkeypatch.setenv(key, value)
        monkeypatch.delenv(values[index][0])
        assert not configured_aot_client_notification_technician_write()
    for key, value in values:
        monkeypatch.setenv(key, value)
    assert configured_aot_client_notification_technician_write()
    monkeypatch.setenv(AOT_CLIENT_NOTIFICATION_PROVIDER_PROFILE_ENV,
                       "xyz-test-company-client-notification-v1")
    assert not configured_aot_client_notification_technician_write()


def test_standing_org_grant_only_on_opt_in_is_idempotent_and_requires_approval():
    case = Case()
    case.grants = InMemoryAuthorityGrantRepository()
    authority = SimpleNamespace(grants=case.grants)
    assert not ensure_aot_client_notification_technician_authority(
        authority, enabled=False,
    )
    assert case.grants.get(AOT_CLIENT_NOTIFICATION_TECH_GRANT_ID) is None
    assert ensure_aot_client_notification_technician_authority(
        authority, enabled=True,
    )
    assert not ensure_aot_client_notification_technician_authority(
        authority, enabled=True,
    )
    grant = case.grants.get(AOT_CLIENT_NOTIFICATION_TECH_GRANT_ID)
    assert grant.capability == POLICY
    assert grant.subject_id == "organization:aot"
    assert grant.permission is PermissionMode.EXECUTE
    assert grant.approval_required is True
    assert grant.client_id is None
    assert grant.status == "active"


def test_conflicting_existing_grant_fails_closed():
    case = Case(grant_approval_required=False)
    with pytest.raises(RuntimeError, match="conflicts"):
        ensure_aot_client_notification_technician_authority(
            SimpleNamespace(grants=case.grants), enabled=True,
        )


@pytest.mark.parametrize("who", ["tech", "other-tech"])
def test_authenticated_technician_needs_own_exact_action_approval(who):
    case = Case()
    first = case.decide(who=who)
    assert first.outcome is AuthorityOutcome.APPROVAL_REQUIRED
    assert first.matched_grants == (AOT_CLIENT_NOTIFICATION_TECH_GRANT_ID,)
    approval = case.approve(who=who, approval_id=f"approved-{who}")
    second = case.decide(who=who, approval_id=approval)
    assert second.outcome is AuthorityOutcome.ALLOWED
    assert second.execution_context.approval_required is True


def test_one_technicians_approval_does_not_authorize_a_second_technician():
    case = Case()
    approval = case.approve(who="tech")
    assert case.decide(who="tech", approval_id=approval).outcome is AuthorityOutcome.ALLOWED
    assert case.decide(who="other-tech", approval_id=approval).outcome is AuthorityOutcome.DENIED


@pytest.mark.parametrize("who", ["admin", "service", "disabled", "outsider", "unknown"])
def test_no_approval_path_for_admin_service_disabled_or_other_tenant(who):
    case = Case()
    assert case.decide(who=who).outcome in (
        AuthorityOutcome.DENIED, AuthorityOutcome.INDETERMINATE,
    )


def test_disabled_profile_fails_closed_even_if_exact_org_grant_persists():
    assert Case(enabled=False).decide().outcome is AuthorityOutcome.DENIED


@pytest.mark.parametrize("kwargs", [
    {"capability": "service.ticket.update"},
    {"capability": "service.ticket.note.create"},
    {"capability": "service.ticket.attachment.create"},
    {"org": "other"},
    {"client": "1158"},
    {"mode": PermissionMode.ADMINISTER},
    {"mode": PermissionMode.OBSERVE},
    {"assurance": "unverified"},
])
def test_other_capability_organization_client_or_mode_does_not_inherit(kwargs):
    assert Case().decide(**kwargs).outcome is not AuthorityOutcome.ALLOWED


@pytest.mark.parametrize("key,value", [
    ("write_capability", "false"),
    ("mcp_action_enabled", "false"),
    ("conversation_authenticated_imperative_is_approval", "false"),
    ("profile", "xyz-test-company-client-notification-v1"),
    ("profile", "gromelski-vulscan-client-notification-v1"),
    ("workflow_template_binding", "caller_supplied"),
    ("recipient_source", "model_supplied"),
])
def test_approved_template_recipient_and_imperative_metadata_required(key, value):
    case = Case()
    case.caps.metadata = {**case.caps.metadata, key: value}
    assert case.decide().outcome is AuthorityOutcome.DENIED


def test_provider_and_lifecycle_must_be_exact_and_active():
    case = Case()
    case.providers.provider_id = "fake-connector"
    assert case.decide().outcome is AuthorityOutcome.DENIED
    case.providers.provider_id = PROVIDER
    case.providers.active = False
    assert case.decide().outcome is AuthorityOutcome.DENIED
    case.providers.active = True
    case.providers.approved = ProviderApproval.BLOCKED
    assert case.decide().outcome is AuthorityOutcome.DENIED
    case.providers.approved = ProviderApproval.APPROVED
    case.providers.provider_type = ProviderType.WORKFLOW
    assert case.decide().outcome is AuthorityOutcome.DENIED
    case.providers.provider_type = ProviderType.EXTERNAL_CONNECTOR
    case.caps.approval_required = False
    assert case.decide().outcome is AuthorityOutcome.DENIED
    case.caps.approval_required = True
    case.caps.active = False
    assert case.decide().outcome is AuthorityOutcome.DENIED


def test_expired_mismatched_or_unapproved_grant_never_authorizes_send():
    case = Case(grant_approval_required=False)
    assert case.decide().outcome is AuthorityOutcome.DENIED
    case = Case()
    approval = case.approve(
        approval_id="expired",
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    assert case.decide(approval_id=approval).outcome is AuthorityOutcome.DENIED
    case = Case()
    approval = case.approve(request_id="other-request")
    assert case.decide(approval_id=approval).outcome is AuthorityOutcome.DENIED
