from datetime import datetime, timezone

import pytest
from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_providers import (
    ExecutionProviderRegistryService, InMemoryExecutionProviderRegistry,
    ProviderApproval,
)
from kernel.identity_authority import (
    AuthorityGrant, AuthorityOutcome, AuthorityRequest, IdentityAuthorityService,
    IdentityRecord, InMemoryIdentityRepository, InMemoryAuthorityGrantRepository,
    InMemoryApprovalRepository, PermissionMode,
)
from orchestrator.backup_capability_catalog import (
    BACKUP_ENDPOINT_ASSET_READ, BACKUP_BACKUPIQ_ALERT_SEARCH,
    register_backup_resource_foundation,
)
from orchestrator.provider_read_authority import (
    AOT_TECHNICIAN_OPERATIONAL_READ_POLICY, GovernedProviderReadAuthorityMatcher,
)
from orchestrator.resource_capability_catalog import (
    DATTO_EDR_PROVIDER, ENDPOINT_SECURITY_DETECTION_SEARCH,
    ENDPOINT_SECURITY_QUARANTINE_SEARCH, ENDPOINT_DEVICE_READ,
    register_endpoint_resource_foundation,
)


def setup_policy():
    identities = InMemoryIdentityRepository()
    for principal, kind, organization, status in (
        ("person-entra-tech", "human", "aot", "active"),
        ("jason-autonomy-worker", "service", "aot", "active"),
        ("person-disabled", "human", "aot", "disabled"),
        ("person-foreign", "human", "other", "active"),
    ):
        identities.put(IdentityRecord(principal, kind, organization, status))
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
    now = datetime.now(timezone.utc)
    register_endpoint_resource_foundation(capabilities=capabilities, providers=providers, now=now)
    register_backup_resource_foundation(capabilities=capabilities, providers=providers, now=now, enabled=True)
    matcher = GovernedProviderReadAuthorityMatcher(capabilities, providers, identities)
    grants = InMemoryAuthorityGrantRepository()
    grants.put(AuthorityGrant(
        "grant-tech-observe", "organization:aot", AOT_TECHNICIAN_OPERATIONAL_READ_POLICY,
        "aot", None, PermissionMode.OBSERVE, approval_required=False,
    ))
    authority = IdentityAuthorityService(
        identities=identities, grants=grants, approvals=InMemoryApprovalRepository(),
        capability_matcher=matcher,
    )
    return authority, providers


def decide(authority, capability, principal="person-entra-tech", mode=PermissionMode.OBSERVE,
           organization="aot", client_id=None):
    return authority.evaluate(AuthorityRequest(
        "request-test", "correlation-test", principal, organization, client_id,
        capability, mode, "microsoft_entra",
    ))


@pytest.mark.parametrize("capability", (
    ENDPOINT_SECURITY_DETECTION_SEARCH,
    ENDPOINT_SECURITY_QUARANTINE_SEARCH,
    ENDPOINT_DEVICE_READ,
    BACKUP_ENDPOINT_ASSET_READ,
    BACKUP_BACKUPIQ_ALERT_SEARCH,
))
def test_human_technician_may_read_registered_edr_rmm_backup_without_approval(capability):
    authority, _ = setup_policy()
    decision = decide(authority, capability)
    assert decision.outcome is AuthorityOutcome.ALLOWED
    assert decision.execution_context is not None
    assert decision.execution_context.approval_required is False
    assert decision.execution_context.maximum_mode is PermissionMode.OBSERVE


@pytest.mark.parametrize("principal", (
    "jason-autonomy-worker", "person-disabled", "person-foreign", "unknown",
))
def test_standing_read_policy_never_grants_nonhuman_inactive_foreign(principal):
    authority, _ = setup_policy()
    assert decide(authority, ENDPOINT_SECURITY_DETECTION_SEARCH, principal).outcome in (
        AuthorityOutcome.DENIED, AuthorityOutcome.INDETERMINATE,
    )


def test_standing_read_policy_does_not_grant_mutation_cross_organization_or_cross_client():
    authority, _ = setup_policy()
    assert decide(authority, ENDPOINT_SECURITY_DETECTION_SEARCH,
                  mode=PermissionMode.EXECUTE).outcome is AuthorityOutcome.DENIED
    assert decide(authority, ENDPOINT_SECURITY_DETECTION_SEARCH,
                  organization="other").outcome is AuthorityOutcome.DENIED
    assert decide(authority, ENDPOINT_SECURITY_DETECTION_SEARCH,
                  client_id="client-not-scoped").outcome is AuthorityOutcome.DENIED


def test_standing_read_does_not_override_disabled_provider_or_unknown_capability():
    authority, providers = setup_policy()
    assert decide(authority, ENDPOINT_SECURITY_DETECTION_SEARCH).outcome is AuthorityOutcome.ALLOWED
    providers.set_approval(provider_id=DATTO_EDR_PROVIDER, approval_status=ProviderApproval.BLOCKED)
    assert decide(authority, ENDPOINT_SECURITY_DETECTION_SEARCH).outcome is AuthorityOutcome.DENIED
    assert decide(authority, "endpoint.unregistered.read").outcome is AuthorityOutcome.DENIED
