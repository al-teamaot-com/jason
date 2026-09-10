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
    IT_GLUE_CAPABILITIES,
    IT_GLUE_PROVIDER,
    register_provider_read_foundation,
)
from jason_runtime.provider_read_activation import (
    PROVIDER_READ_ACTIVATION_ENV,
    PROVIDER_READ_PRODUCTION_PROFILE,
    ProviderReadActivationError,
    apply_provider_read_activation_from_env,
    apply_provider_read_activation_profile,
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


def test_approved_profile_activates_only_exact_read_only_catalog() -> None:
    capabilities, providers = _registries()

    state = apply_provider_read_activation_profile(
        capabilities=capabilities,
        providers=providers,
        profile=PROVIDER_READ_PRODUCTION_PROFILE,
    )

    expected = _all_provider_read_capabilities()
    assert state.enabled is True
    assert state.profile == PROVIDER_READ_PRODUCTION_PROFILE
    assert set(state.provider_ids) == {IT_GLUE_PROVIDER, AUTOTASK_PROVIDER}
    assert set(state.capability_names) == expected

    for provider_id, expected_capabilities in (
        (IT_GLUE_PROVIDER, IT_GLUE_CAPABILITIES),
        (AUTOTASK_PROVIDER, AUTOTASK_CAPABILITIES),
    ):
        provider = providers.get(provider_id)
        assert provider.lifecycle_status is ProviderLifecycle.AVAILABLE
        assert provider.health_status is ProviderHealth.HEALTHY
        assert provider.approval_status is ProviderApproval.APPROVED
        assert provider.execution_modes == frozenset({"deterministic"})
        assert provider.capabilities == expected_capabilities
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
    assert providers.get(IT_GLUE_PROVIDER).lifecycle_status is ProviderLifecycle.AVAILABLE
    assert providers.get(AUTOTASK_PROVIDER).lifecycle_status is ProviderLifecycle.AVAILABLE
