from datetime import datetime, timezone

from kernel.capabilities import CapabilityLifecycle, CapabilityRegistryService, InMemoryCapabilityRegistry
from orchestrator.provider_resource_capability_catalog import (
    PROVIDER_RESOURCE_READ,
    PROVIDER_RESOURCE_SEARCH,
    register_provider_resource_capabilities,
)


def test_generic_provider_resource_capabilities_are_pilot_and_entity_agnostic():
    registry = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    register_provider_resource_capabilities(
        capabilities=registry,
        now=datetime(2026, 9, 10, tzinfo=timezone.utc),
    )

    search = registry.get_current(
        capability_name=PROVIDER_RESOURCE_SEARCH,
        allow_pilot=True,
    )
    read = registry.get_current(
        capability_name=PROVIDER_RESOURCE_READ,
        allow_pilot=True,
    )

    assert search.lifecycle_status is CapabilityLifecycle.PILOT
    assert read.lifecycle_status is CapabilityLifecycle.PILOT
    assert search.metadata["dynamic_schema_required"] == "true"
    assert read.metadata["dynamic_schema_required"] == "true"
    assert search.metadata["model_may_supply_provider_resource_handle"] == "false"
    assert read.metadata["model_may_supply_provider_resource_handle"] == "false"
    assert "microsoft" not in search.business_purpose.casefold()
    assert "it glue" not in search.business_purpose.casefold()
    assert "autotask" not in search.business_purpose.casefold()
    assert search.approval.required is False
    assert search.client_isolation_required is False
    assert search.tenant_isolation_required is True
