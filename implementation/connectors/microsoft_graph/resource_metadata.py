"""Discover Microsoft Graph read resources from authoritative OData CSDL metadata.

This module deliberately does not encode a list of Graph entities or business
workflows.  It interprets the provider-published metadata document and produces a
bounded catalog that higher Jason layers can reason over.  Provider paths therefore
come from governed metadata, not from conversation-generated URLs or one-off code.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Mapping
from xml.etree import ElementTree


_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_MAX_METADATA_BYTES = 20 * 1024 * 1024
_MAX_RESOURCES = 4096
_MAX_FIELDS_PER_RESOURCE = 2048


class MicrosoftGraphMetadataError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MicrosoftGraphField:
    name: str
    type_name: str
    nullable: bool = True
    collection: bool = False

    def __post_init__(self) -> None:
        if not _IDENTIFIER.fullmatch(self.name):
            raise MicrosoftGraphMetadataError(
                f"unsafe Microsoft Graph field name: {self.name!r}"
            )
        if not self.type_name.strip():
            raise MicrosoftGraphMetadataError("Graph field type must be non-empty")


@dataclass(frozen=True, slots=True)
class MicrosoftGraphResource:
    """One provider-published Graph entity set and its structural fields."""

    entity_set: str
    entity_type: str
    fields: tuple[MicrosoftGraphField, ...]
    key_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _IDENTIFIER.fullmatch(self.entity_set):
            raise MicrosoftGraphMetadataError(
                f"unsafe Microsoft Graph entity-set name: {self.entity_set!r}"
            )
        if not self.entity_type.strip():
            raise MicrosoftGraphMetadataError("Graph entity type must be non-empty")
        if len(self.fields) > _MAX_FIELDS_PER_RESOURCE:
            raise MicrosoftGraphMetadataError("Graph resource exceeds field bound")
        names = [field.name for field in self.fields]
        if len(names) != len(set(names)):
            raise MicrosoftGraphMetadataError(
                f"duplicate Graph field in resource {self.entity_set!r}"
            )
        unknown_keys = set(self.key_fields).difference(names)
        if unknown_keys:
            raise MicrosoftGraphMetadataError(
                f"Graph resource key references unknown fields: {sorted(unknown_keys)!r}"
            )

    @property
    def resource_handle(self) -> str:
        return f"microsoft_graph:{self.entity_set}"

    @property
    def resource_type(self) -> str:
        return self.entity_type.rsplit(".", 1)[-1]

    @property
    def collection_path(self) -> str:
        return f"/{self.entity_set}"

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(field.name for field in self.fields)

    def as_context(self) -> Mapping[str, object]:
        """Return model-safe structural context without credentials or raw metadata."""

        return {
            "resource_handle": self.resource_handle,
            "resource_type": self.resource_type,
            "entity_set": self.entity_set,
            "fields": tuple(
                {
                    "name": field.name,
                    "type": field.type_name,
                    "nullable": field.nullable,
                    "collection": field.collection,
                }
                for field in self.fields
            ),
            "key_fields": self.key_fields,
            "operations": ("search", "read"),
        }


@dataclass(frozen=True, slots=True)
class MicrosoftGraphResourceCatalog:
    resources: tuple[MicrosoftGraphResource, ...]
    source_reference: str

    def __post_init__(self) -> None:
        if not self.source_reference.strip():
            raise MicrosoftGraphMetadataError("metadata source reference is required")
        if not self.resources:
            raise MicrosoftGraphMetadataError("Graph metadata exposed no entity sets")
        if len(self.resources) > _MAX_RESOURCES:
            raise MicrosoftGraphMetadataError("Graph metadata exceeds resource bound")
        handles = [resource.resource_handle for resource in self.resources]
        if len(handles) != len(set(handles)):
            raise MicrosoftGraphMetadataError("duplicate Graph resource handle")

    def get(self, resource_handle: str) -> MicrosoftGraphResource:
        wanted = str(resource_handle).strip()
        for resource in self.resources:
            if resource.resource_handle == wanted:
                return resource
        raise MicrosoftGraphMetadataError(
            f"unknown governed Microsoft Graph resource handle: {wanted!r}"
        )

    def model_context(self) -> tuple[Mapping[str, object], ...]:
        return tuple(resource.as_context() for resource in self.resources)


def discover_graph_resources(
    metadata_xml: str | bytes,
    *,
    source_reference: str,
) -> MicrosoftGraphResourceCatalog:
    """Build a bounded read catalog from Microsoft Graph OData CSDL metadata.

    Entity-set names, entity types, primitive field names, inheritance, and key
    declarations are derived from the metadata document.  Navigation properties are
    intentionally omitted from the initial read surface because following them can
    materially widen evidence scope; they can be added later as separately governed
    relationships.
    """

    if isinstance(metadata_xml, str):
        raw = metadata_xml.encode("utf-8")
    elif isinstance(metadata_xml, bytes):
        raw = metadata_xml
    else:
        raise MicrosoftGraphMetadataError("Graph metadata must be text or bytes")

    if not raw or len(raw) > _MAX_METADATA_BYTES:
        raise MicrosoftGraphMetadataError(
            "Graph metadata is empty or exceeds the governed size bound"
        )

    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as error:
        raise MicrosoftGraphMetadataError("Graph metadata is not valid XML") from error

    entity_types: dict[str, ElementTree.Element] = {}
    entity_sets: list[tuple[str, str]] = []

    for schema in _descendants(root, "Schema"):
        namespace = str(schema.attrib.get("Namespace", "")).strip()
        if not namespace:
            continue

        for entity in _children(schema, "EntityType"):
            name = str(entity.attrib.get("Name", "")).strip()
            if name:
                entity_types[f"{namespace}.{name}"] = entity

        for container in _children(schema, "EntityContainer"):
            for entity_set in _children(container, "EntitySet"):
                name = str(entity_set.attrib.get("Name", "")).strip()
                entity_type = str(entity_set.attrib.get("EntityType", "")).strip()
                if not name or not entity_type:
                    continue
                if not _IDENTIFIER.fullmatch(name):
                    raise MicrosoftGraphMetadataError(
                        f"unsafe Graph entity-set name in metadata: {name!r}"
                    )
                entity_sets.append((name, entity_type))

    resources: list[MicrosoftGraphResource] = []
    for entity_set, entity_type in entity_sets:
        fields, keys = _resolve_entity_shape(
            entity_type,
            entity_types=entity_types,
            visiting=frozenset(),
        )
        if not fields:
            continue
        resources.append(
            MicrosoftGraphResource(
                entity_set=entity_set,
                entity_type=entity_type,
                fields=fields,
                key_fields=keys,
            )
        )

    resources.sort(key=lambda item: item.entity_set.casefold())
    return MicrosoftGraphResourceCatalog(
        resources=tuple(resources),
        source_reference=source_reference,
    )


def _resolve_entity_shape(
    entity_type: str,
    *,
    entity_types: Mapping[str, ElementTree.Element],
    visiting: frozenset[str],
) -> tuple[tuple[MicrosoftGraphField, ...], tuple[str, ...]]:
    if entity_type in visiting:
        raise MicrosoftGraphMetadataError("cyclic Graph entity inheritance")

    entity = entity_types.get(entity_type)
    if entity is None:
        return (), ()

    inherited_fields: tuple[MicrosoftGraphField, ...] = ()
    inherited_keys: tuple[str, ...] = ()
    base_type = str(entity.attrib.get("BaseType", "")).strip()
    if base_type:
        inherited_fields, inherited_keys = _resolve_entity_shape(
            base_type,
            entity_types=entity_types,
            visiting=visiting | {entity_type},
        )

    fields: dict[str, MicrosoftGraphField] = {
        field.name: field for field in inherited_fields
    }
    for prop in _children(entity, "Property"):
        name = str(prop.attrib.get("Name", "")).strip()
        raw_type = str(prop.attrib.get("Type", "")).strip()
        if not name or not raw_type:
            continue
        collection = raw_type.startswith("Collection(") and raw_type.endswith(")")
        type_name = raw_type[11:-1] if collection else raw_type
        nullable = str(prop.attrib.get("Nullable", "true")).strip().casefold() != "false"
        fields[name] = MicrosoftGraphField(
            name=name,
            type_name=type_name,
            nullable=nullable,
            collection=collection,
        )

    keys = list(inherited_keys)
    for key in _children(entity, "Key"):
        for ref in _children(key, "PropertyRef"):
            name = str(ref.attrib.get("Name", "")).strip()
            if name and name not in keys:
                keys.append(name)

    ordered_fields = tuple(sorted(fields.values(), key=lambda item: item.name.casefold()))
    ordered_keys = tuple(key for key in keys if key in fields)
    return ordered_fields, ordered_keys


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(element: ElementTree.Element, name: str) -> Iterable[ElementTree.Element]:
    return (child for child in element if _local_name(child.tag) == name)


def _descendants(element: ElementTree.Element, name: str) -> Iterable[ElementTree.Element]:
    return (child for child in element.iter() if _local_name(child.tag) == name)
