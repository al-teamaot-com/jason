from __future__ import annotations

import pytest

from connectors.core.resource_gateway import ResourceOperation, ResourceQuery
from connectors.provider_resource_adapters import (
    translate_datto_rmm_resource,
    translate_it_glue_resource,
)


def test_it_glue_generic_entity_get_translation() -> None:
    invocation = translate_it_glue_resource(
        ResourceQuery(
            provider="it_glue",
            resource_type="entity",
            operation=ResourceOperation.GET,
            organization_id="208",
            resource_id="42",
            filters={"entity": "Configurations"},
        )
    )

    assert invocation.capability == "it_glue.entity.get"
    assert invocation.arguments == {
        "entity": "Configurations",
        "entity_id": "42",
    }


def test_it_glue_generic_entity_query_translation_preserves_filters() -> None:
    invocation = translate_it_glue_resource(
        ResourceQuery(
            provider="it_glue",
            resource_type="entity",
            operation=ResourceOperation.QUERY,
            organization_id="208",
            filters={
                "entity": "Contacts",
                "organization_id": "208",
                "first_name": "Alex",
            },
            page_size=100,
        )
    )

    assert invocation.capability == "it_glue.entity.query"
    assert invocation.arguments["entity"] == "Contacts"
    assert invocation.arguments["filters"] == {
        "organization_id": "208",
        "first_name": "Alex",
    }
    assert invocation.arguments["page_size"] == 100


def test_it_glue_relationship_translation_is_generic() -> None:
    invocation = translate_it_glue_resource(
        ResourceQuery(
            provider="it_glue",
            resource_type="relationship",
            operation=ResourceOperation.RELATIONSHIPS,
            organization_id="208",
            filters={
                "resource_type": "Configuration",
                "resource_id": "42",
            },
        )
    )

    assert invocation.capability == "it_glue.relationships.list"
    assert invocation.arguments["resource_type"] == "Configuration"
    assert invocation.arguments["resource_id"] == "42"


def test_datto_device_and_related_resource_translation() -> None:
    device = translate_datto_rmm_resource(
        ResourceQuery(
            provider="datto_rmm",
            resource_type="device",
            operation=ResourceOperation.GET,
            organization_id="208",
            resource_id="device-123",
        )
    )
    jobs = translate_datto_rmm_resource(
        ResourceQuery(
            provider="datto_rmm",
            resource_type="job",
            operation=ResourceOperation.QUERY,
            organization_id="208",
            filters={"device_uid": "device-123"},
        )
    )

    assert device.capability == "datto_rmm.device.get"
    assert device.arguments == {"device_uid": "device-123"}
    assert jobs.capability == "datto_rmm.component_results.list"
    assert jobs.arguments == {"device_uid": "device-123"}


def test_adapter_fails_closed_for_untranslated_operation() -> None:
    with pytest.raises(ValueError, match="No Datto RMM resource translation"):
        translate_datto_rmm_resource(
            ResourceQuery(
                provider="datto_rmm",
                resource_type="alert",
                operation=ResourceOperation.GET,
                organization_id="208",
                resource_id="alert-1",
            )
        )


def test_adapter_rejects_cross_provider_query() -> None:
    with pytest.raises(ValueError, match="another provider"):
        translate_it_glue_resource(
            ResourceQuery(
                provider="datto_rmm",
                resource_type="entity",
                operation=ResourceOperation.QUERY,
                organization_id="208",
            )
        )
