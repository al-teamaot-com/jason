import pytest

from orchestrator.open_world_execution import (
    OpenWorldExecutionCoordinator,
    OpenWorldExecutionError,
)
from orchestrator.open_world_schema import DiscoveredField, DiscoveredResourceSchema


def dynamic_resource():
    return DiscoveredResourceSchema(
        provider_id="example_provider",
        capability_name="provider.resource.search",
        resource_type="futureObject",
        operation="search",
        collection_supported=True,
        selector_keys=("id",),
        fields=(
            DiscoveredField(name="id", path="id", value_type="string"),
            DiscoveredField(name="friendly", path="friendly", value_type="string"),
        ),
        provider_resource_handle="example_provider:futureObjects",
    )


def test_dynamic_resource_binding_is_derived_from_catalog_not_model_arguments():
    coordinator = OpenWorldExecutionCoordinator(materializer=None, query_engine=None)
    intent = coordinator._intent(
        resource=dynamic_resource(),
        selector_reference="example literal",
        field_paths=("id", "friendly"),
    )

    assert intent.capability_name == "provider.resource.search"
    assert intent.permission_mode == "observe"
    assert intent.execution_mode == "deterministic"
    assert intent.arguments == {
        "selector": "example literal",
        "provider_resource_handle": "example_provider:futureObjects",
        "field_paths": ("id", "friendly"),
    }


def test_dynamic_resource_execution_revalidates_field_projection_fail_closed():
    coordinator = OpenWorldExecutionCoordinator(materializer=None, query_engine=None)
    with pytest.raises(OpenWorldExecutionError, match="outside the governed schema"):
        coordinator._intent(
            resource=dynamic_resource(),
            selector_reference=None,
            field_paths=("id", "notAField"),
        )


def test_existing_capability_intent_shape_does_not_change():
    coordinator = OpenWorldExecutionCoordinator(materializer=None, query_engine=None)
    resource = DiscoveredResourceSchema(
        provider_id="datto_rmm",
        capability_name="endpoint.device.search",
        resource_type="endpoint_device",
        operation="search",
        collection_supported=True,
        selector_keys=("selector",),
        fields=(DiscoveredField(name="name", path="name", value_type="string"),),
    )

    intent = coordinator._intent(
        resource=resource,
        selector_reference="AOT-50282",
        field_paths=("name",),
    )

    assert intent.capability_name == "endpoint.device.search"
    assert intent.arguments == {"selector": "AOT-50282"}
