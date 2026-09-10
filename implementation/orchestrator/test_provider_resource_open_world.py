from connectors.core.resource_catalog import (
    ProviderFieldDefinition,
    ProviderResourceCatalog,
    ProviderResourceDefinition,
)
from orchestrator.open_world_schema import (
    DiscoveredField,
    DiscoveredResourceSchema,
    OpenWorldResourceCatalog,
)
from orchestrator.provider_resource_open_world import (
    GENERIC_PROVIDER_RESOURCE_READ,
    GENERIC_PROVIDER_RESOURCE_SEARCH,
    ProviderResourceOpenWorldBridge,
)


def provider_catalog(resource_name="newProviderObject", resource_type="futureObject"):
    return ProviderResourceCatalog(
        provider_id="example_provider",
        source_reference="provider://authoritative-metadata/v1",
        resources=(
            ProviderResourceDefinition(
                provider_id="example_provider",
                provider_resource_handle=f"example_provider:{resource_name}",
                resource_type=resource_type,
                operations=("search", "read"),
                collection_supported=True,
                selector_keys=("id",),
                fields=(
                    ProviderFieldDefinition(name="id", path="id", value_type="string"),
                    ProviderFieldDefinition(
                        name="newField",
                        path="newField",
                        value_type="string",
                    ),
                ),
                source_reference="provider://authoritative-metadata/v1",
            ),
        ),
    )


def test_bridge_creates_generic_open_world_operations_without_resource_specific_code():
    catalog = ProviderResourceOpenWorldBridge().build(
        catalogs=(provider_catalog(),),
    )

    assert len(catalog.resources) == 2
    search, read = sorted(catalog.resources, key=lambda item: item.operation, reverse=True)
    assert search.operation == "search"
    assert search.capability_name == GENERIC_PROVIDER_RESOURCE_SEARCH
    assert search.collection_supported is True
    assert search.provider_resource_handle == "example_provider:newProviderObject"
    assert {field.path for field in search.fields} == {"id", "newField"}
    assert read.operation == "read"
    assert read.capability_name == GENERIC_PROVIDER_RESOURCE_READ
    assert read.collection_supported is False


def test_provider_resource_handle_is_not_exposed_to_the_model():
    catalog = ProviderResourceOpenWorldBridge().build(
        catalogs=(provider_catalog(),),
    )
    model_context = catalog.model_context()

    serialized = repr(model_context)
    assert "example_provider:newProviderObject" not in serialized
    assert "provider_resource_handle" not in serialized
    assert all(
        item["resource_handle"].startswith("resource_")
        for item in model_context["resources"]
    )


def test_new_provider_metadata_resource_gets_a_distinct_opaque_handle_automatically():
    bridge = ProviderResourceOpenWorldBridge()
    first = bridge.build(catalogs=(provider_catalog(),))
    second = bridge.build(
        catalogs=(provider_catalog(resource_name="anotherObject", resource_type="futureObject"),),
    )

    first_search = next(item for item in first.resources if item.operation == "search")
    second_search = next(item for item in second.resources if item.operation == "search")
    assert first_search.capability_name == second_search.capability_name
    assert first_search.resource_type == second_search.resource_type
    assert first_search.resource_handle != second_search.resource_handle


def test_merge_preserves_existing_capability_backed_resources():
    existing_resource = DiscoveredResourceSchema(
        provider_id="existing_provider",
        capability_name="endpoint.device.search",
        resource_type="endpoint_device",
        operation="search",
        collection_supported=True,
        selector_keys=("selector",),
        fields=(DiscoveredField(name="name", path="name", value_type="string"),),
    )
    existing_handle = existing_resource.resource_handle

    merged = ProviderResourceOpenWorldBridge().merge(
        existing=OpenWorldResourceCatalog(resources=(existing_resource,)),
        catalogs=(provider_catalog(),),
    )

    assert len(merged.resources) == 3
    assert merged.resources[0].resource_handle == existing_handle
    assert existing_handle == DiscoveredResourceSchema(
        provider_id="existing_provider",
        capability_name="endpoint.device.search",
        resource_type="endpoint_device",
        operation="search",
        collection_supported=True,
        selector_keys=("selector",),
        fields=(DiscoveredField(name="name", path="name", value_type="string"),),
    ).resource_handle
