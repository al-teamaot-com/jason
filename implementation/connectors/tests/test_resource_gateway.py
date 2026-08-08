from __future__ import annotations

import pytest

from connectors.core.resource_gateway import (
    ResourceOperation,
    ResourceQuery,
    ResourceRegistry,
    ResourceTypeDefinition,
)
from connectors.kaseya_resource_catalog import build_kaseya_resource_registry


def test_generic_resource_registry_supports_multiple_provider_resource_types() -> None:
    registry = build_kaseya_resource_registry()

    it_glue = registry.list_provider_resources("it_glue")
    datto = registry.list_provider_resources("datto_rmm")
    security = registry.list_provider_resources("rocketcyber")

    assert {item.name for item in it_glue} >= {"entity", "document", "relationship"}
    assert {item.name for item in datto} >= {"device", "alert", "job", "patch_state"}
    assert {item.name for item in security} >= {"incident", "detection"}


def test_resource_queries_are_client_scoped() -> None:
    registry = build_kaseya_resource_registry()

    with pytest.raises(ValueError, match="organization_id is required"):
        registry.authorize(
            ResourceQuery(
                provider="it_glue",
                resource_type="entity",
                operation=ResourceOperation.QUERY,
            )
        )


def test_get_requires_resource_identity() -> None:
    registry = build_kaseya_resource_registry()

    with pytest.raises(ValueError, match="resource_id is required"):
        registry.authorize(
            ResourceQuery(
                provider="datto_rmm",
                resource_type="device",
                operation=ResourceOperation.GET,
                organization_id="client-1",
            )
        )


def test_unregistered_provider_resource_fails_closed() -> None:
    registry = build_kaseya_resource_registry()

    with pytest.raises(ValueError, match="Resource type is not registered"):
        registry.authorize(
            ResourceQuery(
                provider="it_glue",
                resource_type="made_up_resource",
                operation=ResourceOperation.QUERY,
                organization_id="client-1",
            )
        )


def test_registry_does_not_grant_mutation_authority() -> None:
    registry = build_kaseya_resource_registry()
    definition = registry.resolve("it_glue", "entity")

    assert definition.mutable is False
    assert all(item.mutable is False for item in registry.list_provider_resources("datto_rmm"))


def test_duplicate_resource_registration_is_denied() -> None:
    registry = ResourceRegistry()
    definition = ResourceTypeDefinition(
        name="thing",
        provider="provider",
        provider_type="thing",
        operations=frozenset({ResourceOperation.GET}),
    )

    registry.register(definition)

    with pytest.raises(ValueError, match="already registered"):
        registry.register(definition)
