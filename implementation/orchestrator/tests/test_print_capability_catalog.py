from __future__ import annotations

from datetime import datetime, timezone

from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
    ProviderApproval,
    ProviderHealth,
    ProviderLifecycle,
)
from orchestrator.print_capability_catalog import (
    KYOCERA_KFS_PROVIDER,
    PRINT_ALERT_SEARCH,
    PRINT_DEVICE_READ,
    PRINT_DEVICE_SEARCH,
    PRINT_METER_READ,
    PRINT_SUPPLIES_READ,
    kyocera_kfs_provider,
    print_capabilities,
    register_print_resource_foundation,
)


NOW = datetime(2026, 9, 21, 19, 0, tzinfo=timezone.utc)


def test_print_capability_catalog_is_read_only_and_client_scoped() -> None:
    definitions = print_capabilities(NOW)

    assert {item.capability_name for item in definitions} == {
        PRINT_DEVICE_SEARCH,
        PRINT_DEVICE_READ,
        PRINT_METER_READ,
        PRINT_SUPPLIES_READ,
        PRINT_ALERT_SEARCH,
    }
    assert all(item.metadata["read_only"] == "true" for item in definitions)
    assert all(item.client_isolation_required for item in definitions)
    assert all(item.approval.required is False for item in definitions)


def test_kfs_provider_is_blocked_until_explicitly_enabled() -> None:
    provider = kyocera_kfs_provider(NOW, enabled=False)

    assert provider.provider_id == KYOCERA_KFS_PROVIDER
    assert provider.lifecycle_status is ProviderLifecycle.PLANNED
    assert provider.health_status is ProviderHealth.UNAVAILABLE
    assert provider.approval_status is ProviderApproval.BLOCKED
    assert provider.metadata["live_enablement"] == "blocked_pending_contract"


def test_kfs_provider_becomes_available_only_with_enablement_gate() -> None:
    provider = kyocera_kfs_provider(NOW, enabled=True)

    assert provider.lifecycle_status is ProviderLifecycle.AVAILABLE
    assert provider.health_status is ProviderHealth.HEALTHY
    assert provider.approval_status is ProviderApproval.APPROVED
    assert provider.metadata["live_enablement"] == "enabled"


def test_register_print_foundation_registers_all_capabilities_and_provider() -> None:
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(
        registry=InMemoryExecutionProviderRegistry()
    )

    register_print_resource_foundation(
        capabilities=capabilities,
        providers=providers,
        now=NOW,
        enabled=False,
    )

    for name in (
        PRINT_DEVICE_SEARCH,
        PRINT_DEVICE_READ,
        PRINT_METER_READ,
        PRINT_SUPPLIES_READ,
        PRINT_ALERT_SEARCH,
    ):
        assert capabilities.get(name).capability_name == name

    assert providers.get(KYOCERA_KFS_PROVIDER).provider_id == KYOCERA_KFS_PROVIDER
