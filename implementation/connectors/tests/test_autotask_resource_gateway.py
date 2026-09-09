from __future__ import annotations

import json

import pytest

from connectors.core.resource_gateway import ResourceOperation, ResourceQuery
from connectors.kaseya_resource_catalog import build_kaseya_resource_registry
from connectors.provider_resource_adapters import translate_autotask_resource


def test_autotask_resource_catalog_is_client_scoped_and_read_only() -> None:
    registry = build_kaseya_resource_registry()
    entity = registry.resolve("autotask", "entity")
    notes = registry.resolve("autotask", "ticket_note")

    assert entity.client_scoped
    assert not entity.mutable
    assert entity.operations == frozenset(
        {
            ResourceOperation.DESCRIBE,
            ResourceOperation.GET,
            ResourceOperation.QUERY,
        }
    )
    assert notes.operations == frozenset(
        {ResourceOperation.GET, ResourceOperation.QUERY}
    )


def test_autotask_generic_entity_describe_get_and_query_translation() -> None:
    describe = translate_autotask_resource(
        ResourceQuery(
            provider="autotask",
            resource_type="entity",
            operation=ResourceOperation.DESCRIBE,
            organization_id="org-aot",
            filters={"entity": "Tickets"},
        )
    )
    get = translate_autotask_resource(
        ResourceQuery(
            provider="autotask",
            resource_type="entity",
            operation=ResourceOperation.GET,
            organization_id="org-aot",
            resource_id="42",
            filters={"entity": "ConfigurationItems"},
        )
    )
    query = translate_autotask_resource(
        ResourceQuery(
            provider="autotask",
            resource_type="entity",
            operation=ResourceOperation.QUERY,
            organization_id="org-aot",
            filters={
                "entity": "Contacts",
                "companyID": 77,
                "emailAddress": "person@example.com",
            },
        )
    )

    assert describe.capability == "autotask.entity.describe"
    assert describe.arguments == {"entity": "Tickets"}
    assert get.capability == "autotask.entity.get"
    assert get.arguments == {
        "entity": "ConfigurationItems",
        "entity_id": "42",
    }
    assert query.capability == "autotask.entity.query"
    assert query.arguments["entity"] == "Contacts"
    assert json.loads(query.arguments["search"]) == {
        "filter": [
            {"op": "eq", "field": "companyID", "value": 77},
            {
                "op": "eq",
                "field": "emailAddress",
                "value": "person@example.com",
            },
        ]
    }


def test_autotask_ticket_note_translation_requires_authorized_scope() -> None:
    invocation = translate_autotask_resource(
        ResourceQuery(
            provider="autotask",
            resource_type="ticket_note",
            operation=ResourceOperation.QUERY,
            organization_id="org-aot",
            filters={"ticket_id": 101},
        )
    )
    assert invocation.capability == "autotask.ticket.notes.list"
    assert invocation.arguments == {"ticket_id": 101}


def test_autotask_resource_adapter_fails_closed_cross_provider() -> None:
    with pytest.raises(ValueError, match="another provider"):
        translate_autotask_resource(
            ResourceQuery(
                provider="it_glue",
                resource_type="entity",
                operation=ResourceOperation.QUERY,
                organization_id="org-aot",
                filters={"entity": "Contacts"},
            )
        )
