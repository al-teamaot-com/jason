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
from orchestrator.quickbooks_capability_catalog import (
    QUICKBOOKS_CAPABILITIES,
    QUICKBOOKS_PROVIDER,
    register_quickbooks_read_foundation,
)
from jason_runtime.quickbooks_read_activation import (
    QUICKBOOKS_READ_ACTIVATION_ENV,
    QUICKBOOKS_READ_SANDBOX_PROFILE,
    QuickBooksReadActivationError,
    apply_quickbooks_read_activation_from_env,
    apply_quickbooks_read_activation_profile,
)


def _registries():
    capabilities = CapabilityRegistryService(
        registry=InMemoryCapabilityRegistry()
    )
    providers = ExecutionProviderRegistryService(
        registry=InMemoryExecutionProviderRegistry()
    )
    register_quickbooks_read_foundation(
        capabilities=capabilities,
        providers=providers,
        now=datetime(2026, 10, 5, tzinfo=timezone.utc),
    )
    return capabilities, providers


def test_unset_profile_keeps_quickbooks_dormant(monkeypatch):
    monkeypatch.delenv(QUICKBOOKS_READ_ACTIVATION_ENV, raising=False)
    capabilities, providers = _registries()

    state = apply_quickbooks_read_activation_from_env(
        capabilities=capabilities,
        providers=providers,
    )

    assert state.enabled is False
    provider = providers.get(QUICKBOOKS_PROVIDER)
    assert provider.lifecycle_status is ProviderLifecycle.PLANNED
    assert provider.health_status is ProviderHealth.UNKNOWN
    assert provider.approval_status is ProviderApproval.PILOT
    for name in QUICKBOOKS_CAPABILITIES:
        assert capabilities.get(
            capability_name=name,
            version="1.0",
        ).lifecycle_status is CapabilityLifecycle.PILOT


def test_unknown_profile_fails_without_registry_mutation():
    capabilities, providers = _registries()

    with pytest.raises(QuickBooksReadActivationError, match="unsupported"):
        apply_quickbooks_read_activation_profile(
            capabilities=capabilities,
            providers=providers,
            profile="quickbooks-production-read-v1",
        )

    assert providers.get(
        QUICKBOOKS_PROVIDER
    ).lifecycle_status is ProviderLifecycle.PLANNED


def test_exact_sandbox_profile_activates_only_quickbooks_read_catalog():
    capabilities, providers = _registries()

    state = apply_quickbooks_read_activation_profile(
        capabilities=capabilities,
        providers=providers,
        profile=QUICKBOOKS_READ_SANDBOX_PROFILE,
    )

    assert state.enabled is True
    assert set(state.capability_names) == QUICKBOOKS_CAPABILITIES
    provider = providers.get(QUICKBOOKS_PROVIDER)
    assert provider.lifecycle_status is ProviderLifecycle.AVAILABLE
    assert provider.health_status is ProviderHealth.HEALTHY
    assert provider.approval_status is ProviderApproval.APPROVED
    for name in QUICKBOOKS_CAPABILITIES:
        capability = capabilities.get(capability_name=name, version="1.0")
        assert capability.lifecycle_status is CapabilityLifecycle.ACTIVE
        assert capability.metadata["read_only"] == "true"
        assert capability.approval.required is False
