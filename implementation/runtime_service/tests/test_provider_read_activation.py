from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kernel.capabilities import (
    CapabilityLifecycle,
    CapabilityRegistryService,
    InMemoryCapabilityRegistry,
)
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
    ProviderApproval,
    ProviderHealth,
    ProviderLifecycle,
)
from orchestrator.provider_read_capability_catalog import (
    AUTOTASK_CAPABILITIES,
    AUTOTASK_PROVIDER,
    DOCUMENTATION_DOCUMENT_READ,
    DOCUMENTATION_DOCUMENT_SEARCH,
    DOCUMENTATION_ORGANIZATION_SEARCH,
    IT_GLUE_CAPABILITIES,
    IT_GLUE_PROVIDER,
    MICROSOFT_GRAPH_MAIL_CAPABILITIES,
    SERVICE_COMPANY_READ,
    SERVICE_CONTRACT_READ,
    SERVICE_CONTRACT_SEARCH,
    SERVICE_TICKET_ATTACHMENT_SEARCH,
    SERVICE_TICKET_ATTACHMENT_READ,
    SERVICE_TICKET_ATTACHMENT_CONTENT_READ,
    SERVICE_TICKET_SEARCH,
    register_provider_read_foundation,
)
from jason_runtime.provider_read_activation import (
    PROVIDER_READ_ACTIVATION_ENV,
    PROVIDER_READ_AUTOTASK_PROCUREMENT_CAPABILITIES,
    PROVIDER_READ_ENTRA_PROCUREMENT_CATALOG_CAPABILITIES,
    PROVIDER_READ_ENTRA_PROCUREMENT_CATALOG_PROFILE,
    PROVIDER_READ_ENTRA_PROCUREMENT_MAIL_CATALOG_CAPABILITIES,
    PROVIDER_READ_ENTRA_PROCUREMENT_MAIL_CATALOG_PROFILE,
    PROVIDER_READ_ENTRA_PROCUREMENT_MAIL_CONTRACT_CATALOG_CAPABILITIES,
    PROVIDER_READ_ENTRA_PROCUREMENT_MAIL_CONTRACT_CATALOG_PROFILE,
    PROVIDER_READ_ENTRA_PROCUREMENT_MAIL_CONTRACT_ATTACHMENT_CATALOG_PROFILE,
    PROVIDER_READ_DOCUMENT_CAPABILITIES,
    PROVIDER_READ_DOCUMENT_PROFILE,
    PROVIDER_READ_GOVERNED_CATALOG_CAPABILITIES,
    PROVIDER_READ_GOVERNED_CATALOG_PROFILE,
    PROVIDER_READ_PRODUCTION_CAPABILITIES,
    PROVIDER_READ_PRODUCTION_PROFILE,
    ProviderReadActivationError,
    apply_provider_read_activation_from_env,
    apply_provider_read_activation_profile,
)


EXPECTED_INITIAL_CAPABILITIES = frozenset(
    {
        DOCUMENTATION_ORGANIZATION_SEARCH,
        SERVICE_COMPANY_READ,
        SERVICE_TICKET_SEARCH,
    }
)

EXPECTED_DOCUMENT_CAPABILITIES = frozenset(
    {
        *EXPECTED_INITIAL_CAPABILITIES,
        DOCUMENTATION_DOCUMENT_SEARCH,
        DOCUMENTATION_DOCUMENT_READ,
    }
)


def _registries():
    capabilities = CapabilityRegistryService(
        registry=InMemoryCapabilityRegistry()
    )
    providers = ExecutionProviderRegistryService(
        registry=InMemoryExecutionProviderRegistry()
    )
    register_provider_read_foundation(
        capabilities=capabilities,
        providers=providers,
        now=datetime(2026, 9, 10, tzinfo=timezone.utc),
    )
    return capabilities, providers


def _all_provider_read_capabilities() -> frozenset[str]:
    return IT_GLUE_CAPABILITIES | AUTOTASK_CAPABILITIES


def _legacy_provider_read_capabilities() -> frozenset[str]:
    return _all_provider_read_capabilities() - PROVIDER_READ_AUTOTASK_PROCUREMENT_CAPABILITIES


def test_unset_profile_remains_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(PROVIDER_READ_ACTIVATION_ENV, raising=False)
    capabilities, providers = _registries()

    state = apply_provider_read_activation_from_env(
        capabilities=capabilities,
        providers=providers,
    )

    assert state.enabled is False
    assert state.provider_ids == ()
    assert state.capability_names == ()

    for provider_id in (IT_GLUE_PROVIDER, AUTOTASK_PROVIDER):
        provider = providers.get(provider_id)
        assert provider.lifecycle_status is ProviderLifecycle.PLANNED
        assert provider.health_status is ProviderHealth.UNKNOWN
        assert provider.approval_status is ProviderApproval.PILOT

    for capability_name in _all_provider_read_capabilities():
        capability = capabilities.get(
            capability_name=capability_name,
            version="1.0",
        )
        assert capability.lifecycle_status is CapabilityLifecycle.PILOT


def test_unknown_profile_fails_before_any_registry_mutation() -> None:
    capabilities, providers = _registries()

    with pytest.raises(
        ProviderReadActivationError,
        match="unsupported provider-read activation profile",
    ):
        apply_provider_read_activation_profile(
            capabilities=capabilities,
            providers=providers,
            profile="future-unreviewed-profile",
        )

    for provider_id in (IT_GLUE_PROVIDER, AUTOTASK_PROVIDER):
        provider = providers.get(provider_id)
        assert provider.lifecycle_status is ProviderLifecycle.PLANNED
        assert provider.health_status is ProviderHealth.UNKNOWN
        assert provider.approval_status is ProviderApproval.PILOT


def test_initial_profile_activates_exactly_three_proven_reads() -> None:
    capabilities, providers = _registries()

    state = apply_provider_read_activation_profile(
        capabilities=capabilities,
        providers=providers,
        profile=PROVIDER_READ_PRODUCTION_PROFILE,
    )

    assert PROVIDER_READ_PRODUCTION_CAPABILITIES == EXPECTED_INITIAL_CAPABILITIES
    assert state.enabled is True
    assert state.profile == PROVIDER_READ_PRODUCTION_PROFILE
    assert set(state.provider_ids) == {IT_GLUE_PROVIDER, AUTOTASK_PROVIDER}
    assert set(state.capability_names) == EXPECTED_INITIAL_CAPABILITIES
    assert len(state.capability_names) == 3

    for provider_id, expected_catalog in (
        (IT_GLUE_PROVIDER, IT_GLUE_CAPABILITIES),
        (AUTOTASK_PROVIDER, AUTOTASK_CAPABILITIES),
    ):
        provider = providers.get(provider_id)
        assert provider.lifecycle_status is ProviderLifecycle.AVAILABLE
        assert provider.health_status is ProviderHealth.HEALTHY
        assert provider.approval_status is ProviderApproval.APPROVED
        assert provider.execution_modes == frozenset({"deterministic"})
        assert provider.capabilities == expected_catalog
        assert provider.pricing_profile_id == "zero-cost-foundation"

    for capability_name in _all_provider_read_capabilities():
        capability = capabilities.get(
            capability_name=capability_name,
            version="1.0",
        )
        expected_lifecycle = (
            CapabilityLifecycle.ACTIVE
            if capability_name in EXPECTED_INITIAL_CAPABILITIES
            else CapabilityLifecycle.PILOT
        )
        assert capability.lifecycle_status is expected_lifecycle
        assert capability.metadata["provider_neutral"] == "true"
        assert capability.metadata["read_only"] == "true"
        assert capability.permitted_execution_modes == frozenset({"deterministic"})
        assert capability.approval.required is False


def test_document_profile_activates_exactly_five_proven_reads() -> None:
    capabilities, providers = _registries()

    state = apply_provider_read_activation_profile(
        capabilities=capabilities,
        providers=providers,
        profile=PROVIDER_READ_DOCUMENT_PROFILE,
    )

    assert PROVIDER_READ_DOCUMENT_CAPABILITIES == EXPECTED_DOCUMENT_CAPABILITIES
    assert state.enabled is True
    assert state.profile == PROVIDER_READ_DOCUMENT_PROFILE
    assert set(state.provider_ids) == {IT_GLUE_PROVIDER, AUTOTASK_PROVIDER}
    assert set(state.capability_names) == EXPECTED_DOCUMENT_CAPABILITIES
    assert len(state.capability_names) == 5

    for provider_id in (IT_GLUE_PROVIDER, AUTOTASK_PROVIDER):
        provider = providers.get(provider_id)
        assert provider.lifecycle_status is ProviderLifecycle.AVAILABLE
        assert provider.health_status is ProviderHealth.HEALTHY
        assert provider.approval_status is ProviderApproval.APPROVED

    for capability_name in _all_provider_read_capabilities():
        capability = capabilities.get(
            capability_name=capability_name,
            version="1.0",
        )
        expected_lifecycle = (
            CapabilityLifecycle.ACTIVE
            if capability_name in EXPECTED_DOCUMENT_CAPABILITIES
            else CapabilityLifecycle.PILOT
        )
        assert capability.lifecycle_status is expected_lifecycle


def test_governed_catalog_profile_derives_all_reads_from_trusted_provider_catalogs() -> None:
    capabilities, providers = _registries()

    state = apply_provider_read_activation_profile(
        capabilities=capabilities,
        providers=providers,
        profile=PROVIDER_READ_GOVERNED_CATALOG_PROFILE,
    )

    expected = _legacy_provider_read_capabilities()
    assert PROVIDER_READ_GOVERNED_CATALOG_CAPABILITIES == expected
    assert state.enabled is True
    assert state.profile == PROVIDER_READ_GOVERNED_CATALOG_PROFILE
    assert set(state.provider_ids) == {IT_GLUE_PROVIDER, AUTOTASK_PROVIDER}
    assert set(state.capability_names) == expected

    for provider_id in (IT_GLUE_PROVIDER, AUTOTASK_PROVIDER):
        provider = providers.get(provider_id)
        assert provider.lifecycle_status is ProviderLifecycle.AVAILABLE
        assert provider.health_status is ProviderHealth.HEALTHY
        assert provider.approval_status is ProviderApproval.APPROVED
        assert provider.execution_modes == frozenset({"deterministic"})
        assert provider.pricing_profile_id == "zero-cost-foundation"

    for capability_name in expected:
        capability = capabilities.get(
            capability_name=capability_name,
            version="1.0",
        )
        assert capability.lifecycle_status is CapabilityLifecycle.ACTIVE
        assert capability.metadata["provider_neutral"] == "true"
        assert capability.metadata["read_only"] == "true"
        assert capability.permitted_execution_modes == frozenset({"deterministic"})
        assert capability.approval.required is False


def test_governed_catalog_profile_is_restart_persistable_environment_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        PROVIDER_READ_ACTIVATION_ENV,
        PROVIDER_READ_GOVERNED_CATALOG_PROFILE,
    )
    capabilities, providers = _registries()

    state = apply_provider_read_activation_from_env(
        capabilities=capabilities,
        providers=providers,
    )

    assert state.enabled is True
    assert state.profile == PROVIDER_READ_GOVERNED_CATALOG_PROFILE
    assert set(state.capability_names) == _legacy_provider_read_capabilities()


def test_document_profile_is_restart_persistable_environment_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        PROVIDER_READ_ACTIVATION_ENV,
        PROVIDER_READ_DOCUMENT_PROFILE,
    )
    capabilities, providers = _registries()

    state = apply_provider_read_activation_from_env(
        capabilities=capabilities,
        providers=providers,
    )

    assert state.enabled is True
    assert state.profile == PROVIDER_READ_DOCUMENT_PROFILE
    assert set(state.capability_names) == EXPECTED_DOCUMENT_CAPABILITIES


def test_no_fourth_provider_read_is_activated() -> None:
    capabilities, providers = _registries()

    apply_provider_read_activation_profile(
        capabilities=capabilities,
        providers=providers,
        profile=PROVIDER_READ_PRODUCTION_PROFILE,
    )

    active = {
        capability_name
        for capability_name in _all_provider_read_capabilities()
        if capabilities.get(
            capability_name=capability_name,
            version="1.0",
        ).lifecycle_status
        is CapabilityLifecycle.ACTIVE
    }

    assert active == EXPECTED_INITIAL_CAPABILITIES
    assert len(active) == 3


def test_catalog_drift_fails_closed_before_provider_availability() -> None:
    capabilities, providers = _registries()

    capabilities.set_lifecycle(
        capability_name=sorted(IT_GLUE_CAPABILITIES)[0],
        version="1.0",
        lifecycle_status=CapabilityLifecycle.ACTIVE,
    )

    with pytest.raises(
        ProviderReadActivationError,
        match="pilot pre-activation state",
    ):
        apply_provider_read_activation_profile(
            capabilities=capabilities,
            providers=providers,
            profile=PROVIDER_READ_PRODUCTION_PROFILE,
        )

    for provider_id in (IT_GLUE_PROVIDER, AUTOTASK_PROVIDER):
        provider = providers.get(provider_id)
        assert provider.lifecycle_status is ProviderLifecycle.PLANNED
        assert provider.health_status is ProviderHealth.UNKNOWN
        assert provider.approval_status is ProviderApproval.PILOT




def test_procurement_v5_explicitly_activates_new_autotask_reads_without_broadening_v4() -> None:
    capabilities, providers = _registries()

    state = apply_provider_read_activation_profile(
        capabilities=capabilities,
        providers=providers,
        profile=PROVIDER_READ_ENTRA_PROCUREMENT_CATALOG_PROFILE,
    )

    assert state.enabled is True
    assert state.profile == PROVIDER_READ_ENTRA_PROCUREMENT_CATALOG_PROFILE
    assert PROVIDER_READ_AUTOTASK_PROCUREMENT_CAPABILITIES
    assert PROVIDER_READ_AUTOTASK_PROCUREMENT_CAPABILITIES.isdisjoint(
        PROVIDER_READ_GOVERNED_CATALOG_CAPABILITIES
    )
    assert PROVIDER_READ_AUTOTASK_PROCUREMENT_CAPABILITIES.issubset(
        PROVIDER_READ_ENTRA_PROCUREMENT_CATALOG_CAPABILITIES
    )
    assert PROVIDER_READ_AUTOTASK_PROCUREMENT_CAPABILITIES.issubset(
        set(state.capability_names)
    )


def test_mail_reads_remain_dormant_in_v5_and_activate_only_in_v6() -> None:
    capabilities, providers = _registries()

    v5 = apply_provider_read_activation_profile(
        capabilities=capabilities,
        providers=providers,
        profile=PROVIDER_READ_ENTRA_PROCUREMENT_CATALOG_PROFILE,
    )
    assert MICROSOFT_GRAPH_MAIL_CAPABILITIES.isdisjoint(
        set(v5.capability_names)
    )
    for name in MICROSOFT_GRAPH_MAIL_CAPABILITIES:
        assert capabilities.get(
            capability_name=name,
            version="1.0",
        ).lifecycle_status is CapabilityLifecycle.PILOT

    capabilities, providers = _registries()
    v6 = apply_provider_read_activation_profile(
        capabilities=capabilities,
        providers=providers,
        profile=PROVIDER_READ_ENTRA_PROCUREMENT_MAIL_CATALOG_PROFILE,
    )
    assert v6.enabled is True
    assert MICROSOFT_GRAPH_MAIL_CAPABILITIES.issubset(
        set(v6.capability_names)
    )
    assert set(v6.capability_names) == set(
        PROVIDER_READ_ENTRA_PROCUREMENT_MAIL_CATALOG_CAPABILITIES
    )

def test_profile_name_is_restart_persistable_environment_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        PROVIDER_READ_ACTIVATION_ENV,
        PROVIDER_READ_PRODUCTION_PROFILE,
    )
    capabilities, providers = _registries()

    state = apply_provider_read_activation_from_env(
        capabilities=capabilities,
        providers=providers,
    )

    assert state.enabled is True
    assert state.profile == PROVIDER_READ_PRODUCTION_PROFILE
    assert set(state.capability_names) == EXPECTED_INITIAL_CAPABILITIES
    assert providers.get(IT_GLUE_PROVIDER).lifecycle_status is ProviderLifecycle.AVAILABLE
    assert providers.get(AUTOTASK_PROVIDER).lifecycle_status is ProviderLifecycle.AVAILABLE


def test_contract_reads_remain_dormant_in_v5_v6_and_activate_only_in_v7() -> None:
    contract_reads = {SERVICE_CONTRACT_SEARCH, SERVICE_CONTRACT_READ}
    for profile in (
        PROVIDER_READ_ENTRA_PROCUREMENT_CATALOG_PROFILE,
        PROVIDER_READ_ENTRA_PROCUREMENT_MAIL_CATALOG_PROFILE,
    ):
        capabilities, providers = _registries()
        state = apply_provider_read_activation_profile(
            capabilities=capabilities, providers=providers, profile=profile
        )
        assert contract_reads.isdisjoint(set(state.capability_names))
        for name in contract_reads:
            assert capabilities.get(
                capability_name=name, version="1.0"
            ).lifecycle_status is CapabilityLifecycle.PILOT

    capabilities, providers = _registries()
    v7 = apply_provider_read_activation_profile(
        capabilities=capabilities,
        providers=providers,
        profile=PROVIDER_READ_ENTRA_PROCUREMENT_MAIL_CONTRACT_CATALOG_PROFILE,
    )
    assert v7.enabled is True
    assert contract_reads.issubset(set(v7.capability_names))
    assert set(v7.capability_names) == set(
        PROVIDER_READ_ENTRA_PROCUREMENT_MAIL_CONTRACT_CATALOG_CAPABILITIES
    )


def test_attachment_reads_are_dormant_in_v7_and_activate_only_in_v8() -> None:
    attachment_reads={
        SERVICE_TICKET_ATTACHMENT_SEARCH,SERVICE_TICKET_ATTACHMENT_READ,
        SERVICE_TICKET_ATTACHMENT_CONTENT_READ,
    }
    capabilities,providers=_registries()
    v7=apply_provider_read_activation_profile(
        capabilities=capabilities,providers=providers,
        profile=PROVIDER_READ_ENTRA_PROCUREMENT_MAIL_CONTRACT_CATALOG_PROFILE,
    )
    assert attachment_reads.isdisjoint(set(v7.capability_names))

    capabilities,providers=_registries()
    v8=apply_provider_read_activation_profile(
        capabilities=capabilities,providers=providers,
        profile=PROVIDER_READ_ENTRA_PROCUREMENT_MAIL_CONTRACT_ATTACHMENT_CATALOG_PROFILE,
    )
    assert attachment_reads.issubset(set(v8.capability_names))
