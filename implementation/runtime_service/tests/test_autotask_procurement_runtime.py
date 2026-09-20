from datetime import datetime, timezone

from kernel.capabilities import CapabilityLifecycle, CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_providers import ExecutionProviderRegistryService, InMemoryExecutionProviderRegistry
from jason_runtime.autotask_procurement import (
    AUTOTASK_PROCUREMENT_PROFILE_ENV,
    AUTOTASK_PROCUREMENT_PROVIDER,
    PROCUREMENT_CAPABILITIES,
    register_autotask_procurement_runtime_foundation,
)


def test_procurement_profile_activates_exact_governed_surface(monkeypatch) -> None:
    monkeypatch.setenv("JASON_AUTOTASK_MUTATION_ENABLED", "true")
    monkeypatch.setenv(AUTOTASK_PROCUREMENT_PROFILE_ENV, "owner-procurement-v1")
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())

    state = register_autotask_procurement_runtime_foundation(
        capabilities=capabilities,
        providers=providers,
        now=datetime.now(timezone.utc),
    )
    assert state.enabled is True
    assert set(state.capability_names) == set(PROCUREMENT_CAPABILITIES)
    provider = providers.get(AUTOTASK_PROCUREMENT_PROVIDER)
    assert set(provider.capabilities) == set(PROCUREMENT_CAPABILITIES)
    for name in PROCUREMENT_CAPABILITIES:
        definition = capabilities.get(capability_name=name, version="1.0")
        assert definition.lifecycle_status is CapabilityLifecycle.ACTIVE
        assert definition.metadata["mcp_action_enabled"] == "true"
        assert definition.approval.required is True


def test_procurement_profile_is_dormant_when_unset(monkeypatch) -> None:
    monkeypatch.delenv(AUTOTASK_PROCUREMENT_PROFILE_ENV, raising=False)
    monkeypatch.setenv("JASON_AUTOTASK_MUTATION_ENABLED", "true")
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())

    state = register_autotask_procurement_runtime_foundation(
        capabilities=capabilities,
        providers=providers,
        now=datetime.now(timezone.utc),
    )
    assert state.enabled is False
    for name in PROCUREMENT_CAPABILITIES:
        definition = capabilities.get(capability_name=name, version="1.0")
        assert definition.lifecycle_status is CapabilityLifecycle.BUILDING
