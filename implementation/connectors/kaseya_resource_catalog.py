from __future__ import annotations

from connectors.core.resource_gateway import (
    READ_ONLY_OPERATIONS,
    ResourceOperation,
    ResourceRegistry,
    ResourceTypeDefinition,
)


KASEYA_RESOURCE_FAMILIES: tuple[ResourceTypeDefinition, ...] = (
    ResourceTypeDefinition(
        name="entity",
        provider="it_glue",
        provider_type="generic_entity",
        operations=READ_ONLY_OPERATIONS,
    ),
    ResourceTypeDefinition(
        name="document",
        provider="it_glue",
        provider_type="document",
        operations=READ_ONLY_OPERATIONS,
    ),
    ResourceTypeDefinition(
        name="relationship",
        provider="it_glue",
        provider_type="relationship",
        operations=frozenset(
            {
                ResourceOperation.QUERY,
                ResourceOperation.RELATIONSHIPS,
            }
        ),
    ),
    ResourceTypeDefinition(
        name="device",
        provider="datto_rmm",
        provider_type="device",
        operations=READ_ONLY_OPERATIONS,
    ),
    ResourceTypeDefinition(
        name="alert",
        provider="datto_rmm",
        provider_type="alert",
        operations=frozenset(
            {ResourceOperation.GET, ResourceOperation.QUERY, ResourceOperation.DESCRIBE}
        ),
    ),
    ResourceTypeDefinition(
        name="job",
        provider="datto_rmm",
        provider_type="job",
        operations=frozenset(
            {ResourceOperation.GET, ResourceOperation.QUERY, ResourceOperation.DESCRIBE}
        ),
    ),
    ResourceTypeDefinition(
        name="patch_state",
        provider="datto_rmm",
        provider_type="patch_state",
        operations=frozenset(
            {ResourceOperation.GET, ResourceOperation.QUERY, ResourceOperation.DESCRIBE}
        ),
    ),
    ResourceTypeDefinition(
        name="incident",
        provider="rocketcyber",
        provider_type="incident",
        operations=READ_ONLY_OPERATIONS,
    ),
    ResourceTypeDefinition(
        name="detection",
        provider="rocketcyber",
        provider_type="detection",
        operations=READ_ONLY_OPERATIONS,
    ),
    ResourceTypeDefinition(
        name="alert",
        provider="saas_alerts",
        provider_type="alert",
        operations=READ_ONLY_OPERATIONS,
    ),
    ResourceTypeDefinition(
        name="user_activity",
        provider="saas_alerts",
        provider_type="user_activity",
        operations=READ_ONLY_OPERATIONS,
    ),
    ResourceTypeDefinition(
        name="vulnerability",
        provider="vulscan",
        provider_type="vulnerability",
        operations=READ_ONLY_OPERATIONS,
    ),
    ResourceTypeDefinition(
        name="asset_exposure",
        provider="vulscan",
        provider_type="asset_exposure",
        operations=READ_ONLY_OPERATIONS,
    ),
    ResourceTypeDefinition(
        name="email_detection",
        provider="graphus",
        provider_type="email_detection",
        operations=READ_ONLY_OPERATIONS,
    ),
    ResourceTypeDefinition(
        name="campaign",
        provider="bullphish",
        provider_type="campaign",
        operations=READ_ONLY_OPERATIONS,
    ),
    ResourceTypeDefinition(
        name="training_state",
        provider="bullphish",
        provider_type="training_state",
        operations=READ_ONLY_OPERATIONS,
    ),
    ResourceTypeDefinition(
        name="credential_exposure",
        provider="id_agent",
        provider_type="credential_exposure",
        operations=READ_ONLY_OPERATIONS,
    ),
)


def build_kaseya_resource_registry() -> ResourceRegistry:
    registry = ResourceRegistry()
    for definition in KASEYA_RESOURCE_FAMILIES:
        registry.register(definition)
    return registry
