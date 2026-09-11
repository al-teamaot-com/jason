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
    SERVICE_COMPANY_READ,
    SERVICE_TICKET_SEARCH,
    register_provider_read_foundation,
)
from jason_runtime.provider_read_activation import (
    PROVIDER_READ_ACTIVATION_ENV,
    PROVIDER_READ_DOCUMENT_CAPABILITIES,
    PROVIDER_READ_DOCUMENT_PROFILE,
    PROVIDER_READ_DYNAMIC_PROFILE,
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


def test_dynamic_profile_activates_complete_safe_provider_catalog() -> None:
    capabilities, providers = _registries()
    expected = _all_provider_read_capabilities()

    state = apply_provider_read_activation_profile(
        capabilities=capabilities,
        providers=providers,
        profile=PROVIDER_READ_DYNAMIC_PROFILE,
    )

    assert state.enabled is True
    assert state.profile == PROVIDER_READ_DYNAMIC_PROFILE
    assert set(state.provider_ids) == {IT_GLUE_PROVIDER, AUTOTASK_PROVIDER}
    assert set(state.capability_names) == expected
    assert len(state.capability_names) == len(expected)

    for provider_id, expected_catalog in (
        (IT_GLUE_PROVIDER, IT_GLUE_CAPABILITIES),
        (AUTOTASK_PROVIDER, AUTOTASK_CAPABILITIES),
    ):
        provider = providers.get(provider_id)
        assert provider.lifecycle_status is ProviderLifecycle.AVAILABLE
        assert provider.health_status is ProviderHealth.HEALTHY
        assert provider.approval_status is ProviderApproval.APPROVED
        assert provider.capabilities == expected_catalog

    for capability_name in expected:
        capability = capabilities.get(
            capability_name=capability_name,
            version="1.0",
        )
        assert capability.lifecycle_status is CapabilityLifecycle.ACTIVE
        assert capability.metadata["provider_neutral"] == "true"
        assert capability.metadata["read_only"] == "true"
        assert capability.risk_level.value == "low"
        assert capability.permitted_execution_modes == frozenset({"deterministic"})
        assert capability.approval.required is False


def test_dynamic_profile_is_restart_persistable_environment_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        PROVIDER_READ_ACTIVATION_ENV,
        PROVIDER_READ_DYNAMIC_PROFILE,
    )
    capabilities, providers = _registries()

    state = apply_provider_read_activation_from_env(
        capabilities=capabilities,
        providers=providers,
    )

    assert state.enabled is True
    assert state.profile == PROVIDER_READ_DYNAMIC_PROFILE
    assert set(state.capability_names) == _all_provider_read_capabilities()


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


def test_legacy_initial_profile_still_activates_no_fourth_read() -> None:
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
            profile=PROVIDER_READ_DYNAMIC_PROFILE,
        )

    for provider_id in (IT_GLUE_PROVIDER, AUTOTASK_PROVIDER):
        provider = providers.get(provider_id)
        assert provider.lifecycle_status is ProviderLifecycle.PLANNED
        assert provider.health_status is ProviderHealth.UNKNOWN
        assert provider.approval_status is ProviderApproval.PILOT


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
