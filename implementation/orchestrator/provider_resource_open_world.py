"""Expose provider-discovered structural resources to Jason's open-world planner.

This bridge is intentionally provider-neutral.  Connectors publish bounded
``ProviderResourceCatalog`` objects derived from their authoritative metadata.
Jason turns each safe read/search operation into an opaque open-world resource
without hard-coding the provider's entity names or field vocabulary.

The model sees only Jason opaque resource handles and structural fields.  The
underlying provider resource handle remains trusted orchestration state and is
not supplied by conversation/model output.
"""

from __future__ import annotations

from dataclasses import dataclass

from connectors.core.resource_catalog import (
    ProviderResourceCatalog,
    ProviderResourceDefinition,
)

from .open_world_schema import (
    DiscoveredField,
    DiscoveredResourceSchema,
    OpenWorldResourceCatalog,
    OpenWorldSchemaError,
)


GENERIC_PROVIDER_RESOURCE_SEARCH = "provider.resource.search"
GENERIC_PROVIDER_RESOURCE_READ = "provider.resource.read"


@dataclass(frozen=True, slots=True)
class ProviderResourceOpenWorldBridge:
    """Convert live provider structural catalogs into opaque planner resources."""

    def build(
        self,
        *,
        catalogs: tuple[ProviderResourceCatalog, ...],
    ) -> OpenWorldResourceCatalog:
        resources: list[DiscoveredResourceSchema] = []

        for catalog in catalogs:
            for resource in catalog.resources:
                resources.extend(self._resource_operations(resource))

        if not resources:
            raise OpenWorldSchemaError(
                "provider resource catalogs expose no governed read resources"
            )

        return OpenWorldResourceCatalog(
            resources=tuple(
                sorted(
                    resources,
                    key=lambda item: (
                        item.resource_type.casefold(),
                        item.operation,
                        item.provider_id.casefold(),
                        item.resource_handle,
                    ),
                )
            )
        )

    def merge(
        self,
        *,
        existing: OpenWorldResourceCatalog,
        catalogs: tuple[ProviderResourceCatalog, ...],
    ) -> OpenWorldResourceCatalog:
        discovered = self.build(catalogs=catalogs)
        return OpenWorldResourceCatalog(
            resources=tuple(existing.resources) + tuple(discovered.resources)
        )

    def _resource_operations(
        self,
        resource: ProviderResourceDefinition,
    ) -> tuple[DiscoveredResourceSchema, ...]:
        fields = tuple(
            DiscoveredField(
                name=field.name,
                path=field.path,
                value_type=field.value_type,
                description=field.description,
            )
            for field in resource.fields
        )

        output: list[DiscoveredResourceSchema] = []
        for operation in resource.operations:
            capability_name = (
                GENERIC_PROVIDER_RESOURCE_SEARCH
                if operation == "search"
                else GENERIC_PROVIDER_RESOURCE_READ
            )
            output.append(
                DiscoveredResourceSchema(
                    provider_id=resource.provider_id,
                    capability_name=capability_name,
                    resource_type=resource.resource_type,
                    operation=operation,
                    collection_supported=(
                        resource.collection_supported and operation == "search"
                    ),
                    selector_keys=tuple(resource.selector_keys),
                    fields=fields,
                    provider_resource_handle=resource.provider_resource_handle,
                )
            )

        return tuple(output)
