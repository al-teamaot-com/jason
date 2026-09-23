from datetime import datetime, timezone

from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
)
from kernel.identity_authority import AuthorityGrant, AuthorityRequest, PermissionMode
from orchestrator.provider_read_authority import GovernedProviderReadAuthorityMatcher
from orchestrator.resource_capability_catalog import (
    DATTO_RMM_PROVIDER,
    ENDPOINT_ALERT_SEARCH,
    MANAGEMENT_SITE_SEARCH,
    register_endpoint_resource_foundation,
)


def matcher():
    capabilities = CapabilityRegistryService(
        registry=InMemoryCapabilityRegistry()
    )
    providers = ExecutionProviderRegistryService(
        registry=InMemoryExecutionProviderRegistry()
    )

    register_endpoint_resource_foundation(
        capabilities=capabilities,
        providers=providers,
        now=datetime.now(timezone.utc),
    )

    return GovernedProviderReadAuthorityMatcher(
        capabilities=capabilities,
        providers=providers,
    )


def grant():
    return AuthorityGrant(
        grant_id="grant-aot-datto-read",
        subject_id="organization:aot",
        capability="provider-read:datto_rmm",
        organization_id="aot",
        client_id="client-aot-internal",
        permission=PermissionMode.OBSERVE,
    )


def request(capability, mode=PermissionMode.OBSERVE):
    return AuthorityRequest(
        request_id="req-provider-read-1",
        correlation_id="corr-provider-read-1",
        principal_id="person-al",
        organization_id="aot",
        client_id="client-aot-internal",
        capability=capability,
        requested_mode=mode,
        authentication_assurance="high",
    )


def test_datto_read_policy_matches_registered_read_capabilities():
    policy = matcher()

    assert policy.matches(
        grant=grant(),
        request=request(ENDPOINT_ALERT_SEARCH),
    )

    assert policy.matches(
        grant=grant(),
        request=request(MANAGEMENT_SITE_SEARCH),
    )


def test_datto_read_policy_never_matches_execute_request():
    policy = matcher()

    assert not policy.matches(
        grant=grant(),
        request=request(
            ENDPOINT_ALERT_SEARCH,
            PermissionMode.EXECUTE,
        ),
    )


def test_datto_read_policy_does_not_match_unregistered_capability():
    policy = matcher()

    assert not policy.matches(
        grant=grant(),
        request=request("communication.email.send"),
    )


def test_policy_expression_is_provider_specific():
    policy = matcher()

    wrong_provider_grant = AuthorityGrant(
        grant_id="grant-wrong-provider",
        subject_id="organization:aot",
        capability="provider-read:other_provider",
        organization_id="aot",
        client_id="client-aot-internal",
        permission=PermissionMode.OBSERVE,
    )

    assert not policy.matches(
        grant=wrong_provider_grant,
        request=request(ENDPOINT_ALERT_SEARCH),
    )
