from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


_ALLOWED_STATUSES = frozenset(
    {
        "approved",
        "deprecated",
        "retired",
    }
)


@dataclass(frozen=True, slots=True)
class ApprovedSemanticMapping:
    mapping_id: str
    version: int
    provider_id: str
    canonical_fact: str
    provider_schema: str
    provider_field: str
    resource_authority: str
    approval_status: str
    approved_by: str
    approval_basis: str
    openapi_source_reference: str
    semantic_source_reference: str
    active: bool

    def __post_init__(self) -> None:
        required = {
            "mapping_id": self.mapping_id,
            "provider_id": self.provider_id,
            "canonical_fact": self.canonical_fact,
            "provider_schema": self.provider_schema,
            "provider_field": self.provider_field,
            "resource_authority": self.resource_authority,
            "approval_status": self.approval_status,
            "approved_by": self.approved_by,
            "approval_basis": self.approval_basis,
            "openapi_source_reference": self.openapi_source_reference,
            "semantic_source_reference": self.semantic_source_reference,
        }

        for name, value in required.items():
            if not str(value).strip():
                raise ValueError(f"{name} is required")

        if self.version < 1:
            raise ValueError("semantic mapping version must be positive")

        if self.approval_status not in _ALLOWED_STATUSES:
            raise ValueError("semantic mapping approval status is invalid")

        if self.active and self.approval_status != "approved":
            raise PermissionError(
                "only approved semantic mappings may be active"
            )

    def as_context(self) -> Mapping[str, object]:
        return {
            "mapping_id": self.mapping_id,
            "version": self.version,
            "provider_id": self.provider_id,
            "canonical_fact": self.canonical_fact,
            "provider_schema": self.provider_schema,
            "provider_field": self.provider_field,
            "resource_authority": self.resource_authority,
            "approval_status": self.approval_status,
            "approved_by": self.approved_by,
            "approval_basis": self.approval_basis,
            "openapi_source_reference": self.openapi_source_reference,
            "semantic_source_reference": self.semantic_source_reference,
            "active": self.active,
        }


class SemanticMappingRegistry:
    def __init__(
        self,
        mappings: Sequence[ApprovedSemanticMapping] = (),
    ) -> None:
        self._mappings = tuple(mappings)
        self._validate_uniqueness()

    def _validate_uniqueness(self) -> None:
        ids: set[tuple[str, int]] = set()

        for mapping in self._mappings:
            key = (mapping.mapping_id, mapping.version)
            if key in ids:
                raise ValueError(
                    "duplicate semantic mapping identifier/version"
                )
            ids.add(key)

    def find_active(
        self,
        *,
        canonical_fact: str,
        resource_authority: str | None = None,
        provider_id: str | None = None,
    ) -> tuple[ApprovedSemanticMapping, ...]:
        fact = canonical_fact.strip().casefold()
        authority = (
            resource_authority.strip().casefold()
            if resource_authority
            else None
        )
        provider = provider_id.strip() if provider_id else None

        matches = [
            mapping
            for mapping in self._mappings
            if mapping.active
            and mapping.approval_status == "approved"
            and mapping.canonical_fact.strip().casefold() == fact
            and (
                authority is None
                or mapping.resource_authority.strip().casefold() == authority
            )
            and (
                provider is None
                or mapping.provider_id == provider
            )
        ]

        return tuple(
            sorted(
                matches,
                key=lambda item: (
                    item.provider_id.casefold(),
                    item.mapping_id.casefold(),
                    -item.version,
                ),
            )
        )

    def resolve_active(
        self,
        *,
        canonical_fact: str,
        resource_authority: str | None = None,
        provider_id: str | None = None,
    ) -> ApprovedSemanticMapping:
        matches = self.find_active(
            canonical_fact=canonical_fact,
            resource_authority=resource_authority,
            provider_id=provider_id,
        )

        if not matches:
            raise LookupError(
                "no active approved semantic mapping matches the governed fact"
            )

        if len(matches) > 1:
            raise LookupError(
                "active semantic mapping resolution is ambiguous"
            )

        return matches[0]

    def as_context(
        self,
        *,
        query: str | None = None,
    ) -> tuple[Mapping[str, object], ...]:
        normalized = query.strip().casefold() if query else ""

        results = []
        for mapping in self._mappings:
            if not mapping.active or mapping.approval_status != "approved":
                continue

            searchable = " ".join(
                (
                    mapping.canonical_fact,
                    mapping.provider_id,
                    mapping.provider_schema,
                    mapping.provider_field,
                    mapping.resource_authority,
                )
            ).casefold()

            if normalized and normalized not in searchable:
                continue

            results.append(mapping.as_context())

        return tuple(results)


@dataclass(frozen=True, slots=True)
class JsonSemanticMappingRegistryLoader:
    path: Path

    def load(self) -> SemanticMappingRegistry:
        payload = json.loads(self.path.read_text())

        if not isinstance(payload, Mapping):
            raise ValueError("semantic mapping registry root must be an object")

        raw_mappings = payload.get("mappings", ())
        if not isinstance(raw_mappings, list):
            raise ValueError("semantic mapping registry mappings must be a list")

        mappings = tuple(
            ApprovedSemanticMapping(
                mapping_id=str(item["mapping_id"]),
                version=int(item["version"]),
                provider_id=str(item["provider_id"]),
                canonical_fact=str(item["canonical_fact"]),
                provider_schema=str(item["provider_schema"]),
                provider_field=str(item["provider_field"]),
                resource_authority=str(item["resource_authority"]),
                approval_status=str(item["approval_status"]),
                approved_by=str(item["approved_by"]),
                approval_basis=str(item["approval_basis"]),
                openapi_source_reference=str(
                    item["openapi_source_reference"]
                ),
                semantic_source_reference=str(
                    item["semantic_source_reference"]
                ),
                active=bool(item["active"]),
            )
            for item in raw_mappings
        )

        return SemanticMappingRegistry(mappings)
