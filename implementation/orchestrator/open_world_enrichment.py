"""Enrich provider-neutral resource catalogs from governed structural reads.

Existing metadata/canonical hints are never treated as the complete schema.
When a resource can safely be sampled through its ordinary governed collection
read, newly observed structural fields are merged with the hints.

Selector-only resources may be enriched when a grounded selector is available.
"""

from __future__ import annotations

from dataclasses import dataclass

from .governed_schema_probe import (
    GovernedSchemaProbe,
)
from .open_world_schema import (
    DiscoveredResourceSchema,
    OpenWorldResourceCatalog,
)
from .query_source_discovery import (
    QuerySourceContribution,
)


@dataclass(frozen=True, slots=True)
class OpenWorldCatalogEnricher:
    probe: GovernedSchemaProbe

    def enrich(
        self,
        *,
        catalog: OpenWorldResourceCatalog,
        executor,
        selector_references: dict[
            tuple[str, str],
            str,
        ] | None = None,
    ) -> OpenWorldResourceCatalog:
        selectors = (
            selector_references
            or {}
        )

        enriched = []

        for resource in catalog.resources:
            selector = selectors.get(
                (
                    resource.resource_type,
                    resource.capability_name,
                )
            )

            # Collection resources can be structurally sampled without
            # guessing a target. Selector-only resources require an already
            # grounded selector and otherwise retain their declared schema.
            if (
                not resource.collection_supported
                and not selector
            ):
                enriched.append(
                    resource
                )
                continue

            contribution = QuerySourceContribution(
                provider_id=(
                    resource.provider_id
                ),
                capability_name=(
                    resource.capability_name
                ),
                resource_type=(
                    resource.resource_type
                ),
                # QuerySourceContribution currently requires a non-empty
                # structural coverage tuple. This is an internal execution
                # contract only; it is never exposed to semantic planning and
                # is not used as an information boundary here.
                canonical_facts=(
                    "__structural_introspection__",
                ),
                operation=(
                    resource.operation
                ),
                selector_keys=(
                    resource.selector_keys
                ),
                selector_required=(
                    not resource.collection_supported
                ),
                collection_scope=(
                    "runtime-discovered"
                    if resource.collection_supported
                    else None
                ),
                permission_mode="observe",
                risk="low",
                description=(
                    "Governed structural resource introspection"
                ),
            )

            try:
                probed = self.probe.probe(
                    contribution=contribution,
                    executor=executor,
                    selector_reference=selector,
                )
            except Exception:
                # Failure to introspect one resource must not erase declared
                # schema or broaden authority. The planner can still use any
                # structural information the capability already advertised.
                enriched.append(
                    resource
                )
                continue

            merged = {
                field.path: field
                for field in resource.fields
            }

            for field in probed.fields:
                merged.setdefault(
                    field.path,
                    field,
                )

            enriched.append(
                DiscoveredResourceSchema(
                    provider_id=(
                        resource.provider_id
                    ),
                    capability_name=(
                        resource.capability_name
                    ),
                    resource_type=(
                        resource.resource_type
                    ),
                    operation=(
                        resource.operation
                    ),
                    collection_supported=(
                        resource.collection_supported
                    ),
                    selector_keys=(
                        resource.selector_keys
                    ),
                    fields=tuple(
                        merged.values()
                    ),
                    selector_source_policy=(
                        resource.selector_source_policy
                    ),
                )
            )

        return OpenWorldResourceCatalog(
            resources=tuple(
                enriched
            )
        )
