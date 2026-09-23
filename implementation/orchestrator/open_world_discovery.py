"""Build a live provider-neutral resource/schema catalog from governed runtime metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .open_world_schema import (
    DiscoveredField,
    DiscoveredResourceSchema,
    OpenWorldResourceCatalog,
    OpenWorldSchemaError,
    flatten_schema_fields,
)
from .query_source_discovery import (
    _csv,
    _provider_available,
    _truthy,
)


@dataclass(frozen=True, slots=True)
class OpenWorldResourceDiscovery:
    capabilities: Any
    providers: Any
    include_pilot: bool = True

    def discover(
        self,
    ) -> OpenWorldResourceCatalog:
        providers = tuple(
            provider
            for provider in self.providers.list_all()
            if _provider_available(
                provider
            )
        )

        resources = []

        for capability in self.capabilities.list_all():
            lifecycle = str(
                getattr(
                    capability.lifecycle_status,
                    "value",
                    capability.lifecycle_status,
                )
            ).strip().casefold()

            if lifecycle not in {
                "active",
                "pilot",
            }:
                continue

            if (
                lifecycle == "pilot"
                and not self.include_pilot
            ):
                continue

            metadata = capability.metadata

            if not _truthy(
                metadata.get(
                    "provider_neutral",
                    "false",
                )
            ):
                continue

            if not _truthy(
                metadata.get(
                    "read_only",
                    "false",
                )
            ):
                continue

            operation = str(
                metadata.get(
                    "operation",
                    "",
                )
            ).strip().casefold()

            if operation not in {
                "read",
                "search",
            }:
                continue

            backed = tuple(
                provider
                for provider in providers
                if capability.capability_name
                in provider.capabilities
            )

            if not backed:
                continue

            resource_types = _csv(
                metadata.get(
                    "resource_types",
                    "",
                )
            )

            if not resource_types:
                continue

            selector_keys = _csv(
                metadata.get(
                    "selector_keys",
                    "",
                )
            )

            raw_selector_policy = metadata.get(
                "selector_source_policy",
                {}
            )

            selector_source_policy = ()

            if isinstance(
                raw_selector_policy,
                Mapping,
            ):
                selector_source_policy = tuple(
                    (
                        str(key).strip(),
                        str(value).strip(),
                    )
                    for key, value
                    in raw_selector_policy.items()
                    if (
                        str(key).strip()
                        and str(value).strip()
                    )
                )

            collection_supported = (
                operation == "search"
                and not _truthy(
                    metadata.get(
                        "selector_required",
                        "true",
                    )
                )
            )

            declared_fields = (
                self._declared_fields(
                    metadata
                )
            )

            for provider in backed:
                for resource_type in resource_types:
                    resources.append(
                        DiscoveredResourceSchema(
                            provider_id=(
                                provider.provider_id
                            ),
                            capability_name=(
                                capability.capability_name
                            ),
                            resource_type=(
                                resource_type
                            ),
                            operation=operation,
                            collection_supported=(
                                collection_supported
                            ),
                            selector_keys=tuple(
                                selector_keys
                            ),
                            fields=declared_fields,
                            selector_source_policy=(
                                selector_source_policy
                            ),
                        )
                    )

        if not resources:
            raise OpenWorldSchemaError(
                "runtime exposes no governed "
                "open-world resources"
            )

        return OpenWorldResourceCatalog(
            resources=tuple(
                sorted(
                    resources,
                    key=lambda item: (
                        item.resource_type.casefold(),
                        item.capability_name.casefold(),
                        item.provider_id.casefold(),
                    ),
                )
            )
        )

    def _declared_fields(
        self,
        metadata: Mapping[str, Any],
    ) -> tuple[
        DiscoveredField,
        ...
    ]:
        """Use any structural schema already exposed by a capability.

        canonical_facts are accepted as hints, not as the hard information boundary.
        """

        fields = []

        schema = metadata.get(
            "resource_schema"
        )

        if isinstance(
            schema,
            Mapping,
        ):
            fields.extend(
                flatten_schema_fields(
                    schema
                )
            )

        field_paths = _csv(
            metadata.get(
                "field_paths",
                "",
            )
        )

        for path in field_paths:
            fields.append(
                DiscoveredField(
                    name=(
                        path.rsplit(
                            ".",
                            1,
                        )[-1]
                    ),
                    path=path,
                )
            )

        canonical = _csv(
            metadata.get(
                "canonical_facts",
                "",
            )
        )

        for fact in canonical:
            fields.append(
                DiscoveredField(
                    name=fact,
                    path=fact,
                    description=(
                        "known semantic hint"
                    ),
                )
            )

        unique = {}

        for field in fields:
            unique.setdefault(
                field.path,
                field,
            )

        return tuple(
            unique.values()
        )
