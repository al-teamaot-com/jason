"""Cross-boundary tests for the opt-in AOT Autotask ticket routine-RW grant."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from kernel.execution_providers import (
    ProviderApproval, ProviderLifecycle, ProviderType,
)
from kernel.identity_authority import (
    ApprovalRecord, AuthorityGrant, AuthorityOutcome, AuthorityRequest,
    IdentityAuthorityService, IdentityRecord, InMemoryIdentityRepository,
    InMemoryAuthorityGrantRepository, InMemoryApprovalRepository, PermissionMode,
)
from orchestrator.provider_read_authority import (
    AOT_TECHNICIAN_ROUTINE_AUTOTASK_WRITE_POLICY,
    GovernedProviderReadAuthorityMatcher,
    AOT_ROUTINE_AUTOTASK_WRITE_PROVIDERS,
)


CAPABILITIES = {
    "service.ticket.create",
    "service.ticket.update",
    "service.ticket.note.create",
}


class CapabilityRegistry:
    def __init__(self):
        self.enabled = True
        self.metadata = {
            "write_capability": "true",
            "mcp_action_enabled": "true",
            "conversation_authenticated_imperative_is_approval": "true",
        }

    def get_current(self, *, capability_name):
        from kernel.capabilities.repository import CapabilityNotFoundError
        if capability_name not in CAPABILITIES:
            raise CapabilityNotFoundError(capability_name)
        return SimpleNamespace(
            lifecycle_status=SimpleNamespace(value="active" if self.enabled else "building"),
            metadata=self.metadata,
            approval=SimpleNamespace(required=True),
        )


class Providers:
    def __init__(self):
        self.active = True
        self.provider_id = "autotask_ticket_update"
        self.kind = ProviderType.EXTERNAL_CONNECTOR
        self.approval = ProviderApproval.APPROVED

    def list_all(self):
        return tuple(
            SimpleNamespace(
                provider_id=(self.provider_id if capability == "service.ticket.update"
                             else AOT_ROUTINE_AUTOTASK_WRITE_PROVIDERS[capability]),
                capabilities=frozenset({capability}),
                provider_type=self.kind,
                lifecycle_status=(ProviderLifecycle.AVAILABLE if self.active
                                  else ProviderLifecycle.PLANNED),
                approval_status=self.approval,
            )
            for capability in sorted(CAPABILITIES)
        )


def make_runtime(*, enabled=True, approval_required=True):
    identities = InMemoryIdentityRepository()
    for principal, kind, org, status in (
        ("tech", "human", "aot", "active"),
        ("person", "person", "aot", "active"),
        ("autonomy", "service", "aot", "active"),
        ("disabled", "human", "aot", "disabled"),
        ("foreign", "human", "other", "active"),
    ):
        identities.put(IdentityRecord(principal, kind, org, status))
    capabilities, providers = CapabilityRegistry(), Providers()
    grants = InMemoryAuthorityGrantRepository()
    grants.put(AuthorityGrant(
        "routine-grant", "organization:aot",
        AOT_TECHNICIAN_ROUTINE_AUTOTASK_WRITE_POLICY,
        "aot", None, PermissionMode.EXECUTE, approval_required=approval_required,
    ))
    approvals = InMemoryApprovalRepository()
    service = IdentityAuthorityService(
        identities=identities, grants=grants, approvals=approvals,
        capability_matcher=GovernedProviderReadAuthorityMatcher(
            capabilities, providers, identities, routine_write_enabled=enabled,
        ),
    )
    return service, capabilities, providers, approvals


def decide(service, *, capability="service.ticket.update", principal="tech",
           organization="aot", client=None, approval_id=None, mode=PermissionMode.EXECUTE):
    return service.evaluate(AuthorityRequest(
        "request-123", "correlation-123", principal, organization, client,
        capability, mode, "entra-oauth-bearer", approval_id=approval_id,
    ))


@pytest.mark.parametrize("capability", sorted(CAPABILITIES))
def test_routine_ticket_capability_requires_exact_scoped_approval(capability):
    service, _, _, approvals = make_runtime()
    first = decide(service, capability=capability)
    assert first.outcome is AuthorityOutcome.APPROVAL_REQUIRED
    assert first.matched_grants == ("routine-grant",)
    approvals.put(ApprovalRecord(
        "approved-123", "request-123", capability, "aot", None, "tech",
        "approved", "tech", datetime.now(timezone.utc),
        datetime.now(timezone.utc) + timedelta(minutes=5),
    ))
    second = decide(service, capability=capability, approval_id="approved-123")
    assert second.outcome is AuthorityOutcome.ALLOWED
    assert second.execution_context.approval_required is True
    assert second.execution_context.maximum_mode is PermissionMode.EXECUTE


def test_profile_disabled_even_with_persisted_execute_grant():
    service, _, _, _ = make_runtime(enabled=False)
    assert decide(service).outcome is AuthorityOutcome.DENIED


@pytest.mark.parametrize("principal", ["autonomy", "disabled", "foreign", "missing"])
def test_not_nonhuman_disabled_foreign_or_unknown(principal):
    service, _, _, _ = make_runtime()
    assert decide(service, principal=principal).outcome in (
        AuthorityOutcome.DENIED, AuthorityOutcome.INDETERMINATE
    )

@pytest.mark.parametrize("capability", [
    "service.ticket.note.update", "service.ticket.attachment.create",
    "service.purchase.order.update", "automation.component.execute",
])
def test_unlisted_privileged_actions_not_inherited(capability):
    service, _, _, _ = make_runtime()
    assert decide(service, capability=capability).outcome is AuthorityOutcome.DENIED


def test_scope_and_mode_fail_closed():
    service, _, _, _ = make_runtime()
    assert decide(service, organization="other").outcome is AuthorityOutcome.DENIED
    assert decide(service, client="different-client").outcome is AuthorityOutcome.DENIED
    assert decide(service, mode=PermissionMode.OBSERVE).outcome is AuthorityOutcome.DENIED
    assert decide(service, mode=PermissionMode.ADMINISTER).outcome is AuthorityOutcome.DENIED


@pytest.mark.parametrize("field,value", [
    ("write_capability", "false"),
    ("mcp_action_enabled", "false"),
    ("conversation_authenticated_imperative_is_approval", "false"),
])
def test_capability_opt_in_is_mandatory(field, value):
    service, caps, _, _ = make_runtime()
    caps.metadata = {**caps.metadata, field: value}
    assert decide(service).outcome is AuthorityOutcome.DENIED


def test_inactive_capability_or_unavailable_provider_is_denied():
    service, caps, provider, _ = make_runtime()
    caps.enabled = False
    assert decide(service).outcome is AuthorityOutcome.DENIED
    caps.enabled = True
    provider.active = False
    assert decide(service).outcome is AuthorityOutcome.DENIED
    provider.active = True
    provider.approval = ProviderApproval.BLOCKED
    assert decide(service).outcome is AuthorityOutcome.DENIED
    provider.approval = ProviderApproval.APPROVED
    provider.provider_id = "fake_external_provider"
    assert decide(service).outcome is AuthorityOutcome.DENIED


def test_no_approval_bypass_from_wrongly_configured_grant():
    service, _, _, _ = make_runtime(approval_required=False)
    assert decide(service).outcome is AuthorityOutcome.DENIED


def test_expired_or_mismatched_approval_denied():
    service, _, _, approvals = make_runtime()
    approvals.put(ApprovalRecord(
        "other-client", "request-123", "service.ticket.update", "aot", "wrong",
        "tech", "approved", "tech", datetime.now(timezone.utc), None,
    ))
    assert decide(service, approval_id="other-client").outcome is AuthorityOutcome.DENIED
