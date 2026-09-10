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
from .provider_resource_open_world import ProviderResourceOpenWorldBridge
from .query_source_discovery import _csv, _provider_available, _truthy


@dataclass(frozen=True, slots=True)
class OpenWorldResourceDiscovery:
    capabilities: Any
    providers: Any
    include_pilot: bool = True
    provider_catalog_sources: tuple[Any, ...] = ()

    def discover(
        self,
        *,
        client_id: str | None = None,
        correlation_id: str | None = None,
    ) -> OpenWorldResourceCatalog:
        """Discover static resources plus eligible provider-published schemas.

        A catalog source may publish provider-global structural metadata (for example,
        an API service metadata document) before a target client is known. Sources that
        require tenant/client scope are consulted only after a non-empty client scope is
        supplied. In both cases the execution provider and generic read capabilities
        must already be eligible in Jason's governed registries.
        """

        available_providers = tuple(
            provider
            for provider in self.providers.list_all()
            if _provider_available(provider)
        )
        available_provider_ids = {
            provider.provider_id for provider in available_providers
        }

        resources = self._capability_backed_resources(available_providers)
        base = OpenWorldResourceCatalog(
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

        provider_catalogs = []
        correlation = str(correlation_id or "").strip()
        client = str(client_id or "").strip()
        if correlation:
            for source in self.provider_catalog_sources:
                provider_id = str(getattr(source, "provider_id", "")).strip()
                if not provider_id:
                    raise OpenWorldSchemaError(
                        "provider catalog source does not declare provider identity"
                    )
                if provider_id not in available_provider_ids:
                    continue
                if not self._generic_provider_resource_capabilities_are_eligible(
                    provider_id
                ):
                    continue

                provider_global = getattr(source, "provider_catalog", None)
                provider_scoped = getattr(source, "provider_catalog_for_client", None)
                if callable(provider_global):
                    catalog = provider_global(correlation_id=correlation)
                elif client and callable(provider_scoped):
                    catalog = provider_scoped(
                        client_id=client,
                        correlation_id=correlation,
                    )
                else:
                    continue

                if catalog.provider_id != provider_id:
                    raise OpenWorldSchemaError(
                        "provider catalog identity does not match its registered source"
                    )
                provider_catalogs.append(catalog)

        if provider_catalogs:
            bridge = ProviderResourceOpenWorldBridge()
            base = (
                bridge.merge(existing=base, catalogs=tuple(provider_catalogs))
                if base.resources
                else bridge.build(catalogs=tuple(provider_catalogs))
            )

        if not base.resources:
            raise OpenWorldSchemaError(
                "runtime exposes no governed open-world resources"
            )
        return base

    def _generic_provider_resource_capabilities_are_eligible(
        self,
        provider_id: str,
    ) -> bool:
        try:
            provider = self.providers.get(provider_id)
        except LookupError:
            return False

        for capability_name in (
            "provider.resource.search",
            "provider.resource.read",
        ):
            if capability_name not in provider.capabilities:
                return False
            try:
                capability = self.capabilities.get_current(
                    capability_name=capability_name,
                    allow_pilot=self.include_pilot,
                )
            except LookupError:
                return False
            lifecycle = str(
                getattr(
                    capability.lifecycle_status,
                    "value",
                    capability.lifecycle_status,
                )
            ).strip().casefold()
            if lifecycle not in {"active", "pilot"}:
                return False
            if lifecycle == "pilot" and not self.include_pilot:
                return False
            if not _truthy(capability.metadata.get("read_only", "false")):
                return False
        return True

    def _capability_backed_resources(
        self,
        available_providers: tuple[Any, ...],
    ) -> list[DiscoveredResourceSchema]:
        resources = []

        for capability in self.capabilities.list_all():
            lifecycle = str(
                getattr(
                    capability.lifecycle_status,
                    "value",
                    capability.lifecycle_status,
                )
            ).strip().casefold()
            if lifecycle not in {"active", "pilot"}:
                continue
            if lifecycle == "pilot" and not self.include_pilot:
                continue

            metadata = capability.metadata
            if not _truthy(metadata.get("provider_neutral", "false")):
                continue
            if not _truthy(metadata.get("read_only", "false")):
                continue
            if _truthy(metadata.get("dynamic_schema_required", "false")):
                continue

            operation = str(metadata.get("operation", "")).strip().casefold()
            if operation not in {"read", "search"}:
                continue

            backed = tuple(
                provider
                for provider in available_providers
                if capability.capability_name in provider.capabilities
            )
            if not backed:
                continue

            resource_types = _csv(metadata.get("resource_types", ""))
            if not resource_types:
                continue
            selector_keys = _csv(metadata.get("selector_keys", ""))

            raw_selector_policy = metadata.get("selector_source_policy", {})
            selector_source_policy = ()
            if isinstance(raw_selector_policy, Mapping):
                selector_source_policy = tuple(
                    (str(key).strip(), str(value).strip())
                    for key, value in raw_selector_policy.items()
                    if str(key).strip() and str(value).strip()
                )

            collection_supported = (
                operation == "search"
                and not _truthy(metadata.get("selector_required", "true"))
            )
            declared_fields = self._declared_fields(metadata)

            for provider in backed:
                for resource_type in resource_types:
                    resources.append(
                        DiscoveredResourceSchema(
                            provider_id=provider.provider_id,
                            capability_name=capability.capability_name,
                            resource_type=resource_type,
                            operation=operation,
                            collection_supported=collection_supported,
                            selector_keys=tuple(selector_keys),
                            fields=declared_fields,
                            selector_source_policy=selector_source_policy,
                        )
                    )
        return resources

    def _declared_fields(
        self,
        metadata: Mapping[str, Any],
    ) -> tuple[DiscoveredField, ...]:
        """Use structural schema already exposed by a capability."""

        fields = []
        schema = metadata.get("resource_schema")
        if isinstance(schema, Mapping):
            fields.extend(flatten_schema_fields(schema))

        for path in _csv(metadata.get("field_paths", "")):
            fields.append(
                DiscoveredField(
                    name=path.rsplit(".", 1)[-1],
                    path=path,
                )
            )

        for fact in _csv(metadata.get("canonical_facts", "")):
            fields.append(
                DiscoveredField(
                    name=fact,
                    path=fact,
                    description="known semantic hint",
                )
            )

        unique = {}
        for field in fields:
            unique.setdefault(field.path, field)
        return tuple(unique.values())
