from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

import pytest

from connectors.core.resource_catalog import (
    ProviderFieldDefinition,
    ProviderResourceCatalog,
    ProviderResourceDefinition,
)
from connectors.microsoft_graph.resource_provider import build_microsoft_graph_resource_provider
from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
    ProviderApproval,
    ProviderHealth,
    ProviderLifecycle,
)
from orchestrator.open_world_discovery import OpenWorldResourceDiscovery
from orchestrator.open_world_schema import OpenWorldSchemaError
from orchestrator.provider_resource_capability_catalog import (
    register_provider_resource_capabilities,
)


@dataclass
class CatalogSource:
    provider_id: str = "microsoft_graph"
    calls: list[tuple[str, str]] = field(default_factory=list)

    def provider_catalog_for_client(self, *, client_id: str, correlation_id: str):
        self.calls.append((client_id, correlation_id))
        return ProviderResourceCatalog(
            provider_id=self.provider_id,
            source_reference="provider:test-metadata",
            resources=(
                ProviderResourceDefinition(
                    provider_id=self.provider_id,
                    provider_resource_handle="microsoft_graph:newObjects",
                    resource_type="newObject",
                    operations=("search", "read"),
                    collection_supported=True,
                    selector_keys=("id",),
                    fields=(
                        ProviderFieldDefinition(name="id", path="id", value_type="string"),
                        ProviderFieldDefinition(name="label", path="label", value_type="string"),
                    ),
                    source_reference="provider:test-metadata",
                ),
            ),
        )


def runtime(*, provider_available: bool = True):
    now = datetime(2026, 9, 10, tzinfo=timezone.utc)
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    register_provider_resource_capabilities(capabilities=capabilities, now=now)

    providers = ExecutionProviderRegistryService(
        registry=InMemoryExecutionProviderRegistry()
    )
    provider = build_microsoft_graph_resource_provider(now=now)
    if provider_available:
        provider = replace(
            provider,
            lifecycle_status=ProviderLifecycle.AVAILABLE,
            health_status=ProviderHealth.HEALTHY,
            approval_status=ProviderApproval.APPROVED,
        )
    providers.register(provider)
    return capabilities, providers


def test_client_scoped_provider_metadata_becomes_open_world_resources():
    capabilities, providers = runtime()
    source = CatalogSource()
    discovery = OpenWorldResourceDiscovery(
        capabilities=capabilities,
        providers=providers,
        provider_catalog_sources=(source,),
    )

    catalog = discovery.discover(client_id="client-1", correlation_id="corr-1")

    assert source.calls == [("client-1", "corr-1")]
    assert {item.resource_type for item in catalog.resources} == {"newObject"}
    assert {item.capability_name for item in catalog.resources} == {
        "provider.resource.search",
        "provider.resource.read",
    }
    assert all(item.provider_resource_handle for item in catalog.resources)
    assert not any(item.resource_type == "provider_resource" for item in catalog.resources)


def test_provider_catalog_source_is_not_probed_without_bound_client_scope():
    capabilities, providers = runtime()
    source = CatalogSource()
    discovery = OpenWorldResourceDiscovery(
        capabilities=capabilities,
        providers=providers,
        provider_catalog_sources=(source,),
    )

    with pytest.raises(OpenWorldSchemaError, match="no governed open-world resources"):
        discovery.discover()

    assert source.calls == []


def test_nonoperational_provider_catalog_source_is_not_probed():
    capabilities, providers = runtime(provider_available=False)
    source = CatalogSource()
    discovery = OpenWorldResourceDiscovery(
        capabilities=capabilities,
        providers=providers,
        provider_catalog_sources=(source,),
    )

    with pytest.raises(OpenWorldSchemaError, match="no governed open-world resources"):
        discovery.discover(client_id="client-1", correlation_id="corr-1")

    assert source.calls == []
