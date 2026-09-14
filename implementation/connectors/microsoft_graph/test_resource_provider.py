from datetime import datetime, timezone

from kernel.execution_providers import ProviderApproval, ProviderHealth, ProviderLifecycle
from connectors.microsoft_graph.resource_provider import (
    MICROSOFT_GRAPH_RESOURCE_PROVIDER,
    build_microsoft_graph_resource_provider,
)
from orchestrator.provider_resource_capability_catalog import (
    PROVIDER_RESOURCE_CAPABILITIES,
)


def test_microsoft_provider_advertises_generic_capabilities_without_entity_inventory():
    provider = build_microsoft_graph_resource_provider(
        now=datetime(2026, 9, 10, tzinfo=timezone.utc)
    )

    assert provider.provider_id == MICROSOFT_GRAPH_RESOURCE_PROVIDER
    assert provider.capabilities == PROVIDER_RESOURCE_CAPABILITIES
    assert provider.lifecycle_status is ProviderLifecycle.PLANNED
    assert provider.approval_status is ProviderApproval.PILOT
    assert provider.health_status is ProviderHealth.UNKNOWN
    assert provider.metadata["entity_inventory"] == "dynamic"
    assert not any(
        entity in repr(provider).casefold()
        for entity in ("users", "groups", "devices", "subscribedskus")
    )
