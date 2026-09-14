"""Provider-neutral contracts for resources discovered from provider metadata.

A provider connector may learn resources and fields from an authoritative schema,
manifest, or metadata endpoint and publish them through this bounded structural
contract.  The contract deliberately contains no provider URL, credential, token,
or arbitrary request text and does not itself grant execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


_ALLOWED_OPERATIONS = frozenset({"search", "read"})
_MAX_RESOURCES = 4096
_MAX_FIELDS = 2048


class ProviderResourceCatalogError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProviderFieldDefinition:
    name: str
    path: str
    value_type: str | None = None
    description: str | None = None
    filterable: bool = False
    sortable: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ProviderResourceCatalogError("provider field name is required")
        if not self.path.strip():
            raise ProviderResourceCatalogError("provider field path is required")


@dataclass(frozen=True, slots=True)
class ProviderResourceDefinition:
    """One provider-published structural resource Jason may reason over.

    ``provider_resource_handle`` is opaque outside the provider adapter.  It is a
    stable reference to provider metadata, not a URL and not a model-generated
    request path.
    """

    provider_id: str
    provider_resource_handle: str
    resource_type: str
    operations: tuple[str, ...]
    collection_supported: bool
    selector_keys: tuple[str, ...]
    fields: tuple[ProviderFieldDefinition, ...]
    source_reference: str
    metadata: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if not self.provider_id.strip():
            raise ProviderResourceCatalogError("provider id is required")
        if not self.provider_resource_handle.strip():
            raise ProviderResourceCatalogError("provider resource handle is required")
        if not self.resource_type.strip():
            raise ProviderResourceCatalogError("resource type is required")
        if not self.source_reference.strip():
            raise ProviderResourceCatalogError("resource source reference is required")
        if not self.operations:
            raise ProviderResourceCatalogError("provider resource requires an operation")
        invalid_operations = tuple(
            operation for operation in self.operations if operation not in _ALLOWED_OPERATIONS
        )
        if invalid_operations:
            raise ProviderResourceCatalogError(
                f"unsupported provider resource operations: {invalid_operations!r}"
            )
        if len(self.fields) > _MAX_FIELDS:
            raise ProviderResourceCatalogError("provider resource exceeds field bound")
        field_paths = [field.path for field in self.fields]
        if len(field_paths) != len(set(field_paths)):
            raise ProviderResourceCatalogError("provider resource contains duplicate field paths")
        unknown_selectors = set(self.selector_keys).difference(field_paths)
        if unknown_selectors:
            raise ProviderResourceCatalogError(
                f"provider resource selectors reference unknown fields: {sorted(unknown_selectors)!r}"
            )


@dataclass(frozen=True, slots=True)
class ProviderResourceCatalog:
    provider_id: str
    resources: tuple[ProviderResourceDefinition, ...]
    source_reference: str

    def __post_init__(self) -> None:
        if not self.provider_id.strip():
            raise ProviderResourceCatalogError("provider catalog id is required")
        if not self.source_reference.strip():
            raise ProviderResourceCatalogError("provider catalog source reference is required")
        if not self.resources:
            raise ProviderResourceCatalogError("provider catalog exposes no resources")
        if len(self.resources) > _MAX_RESOURCES:
            raise ProviderResourceCatalogError("provider catalog exceeds resource bound")
        handles = [resource.provider_resource_handle for resource in self.resources]
        if len(handles) != len(set(handles)):
            raise ProviderResourceCatalogError("provider catalog contains duplicate resource handles")
        mismatched = tuple(
            resource.provider_resource_handle
            for resource in self.resources
            if resource.provider_id != self.provider_id
        )
        if mismatched:
            raise ProviderResourceCatalogError(
                "provider catalog contains resources belonging to another provider"
            )

    def get(self, provider_resource_handle: str) -> ProviderResourceDefinition:
        wanted = str(provider_resource_handle).strip()
        for resource in self.resources:
            if resource.provider_resource_handle == wanted:
                return resource
        raise ProviderResourceCatalogError(
            f"unknown provider resource handle: {wanted!r}"
        )
