from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence


class DocumentationSourceLifecycle(str, Enum):
    PLANNED = "planned"
    AVAILABLE = "available"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class DocumentationSourceApproval(str, Enum):
    APPROVED = "approved"
    PILOT = "pilot"
    BLOCKED = "blocked"


class DocumentationRetrievalMethod(str, Enum):
    HTTPS = "https"
    OPENAPI = "openapi"
    LOCAL_ARTIFACT = "local_artifact"
    CONNECTOR_RESOURCE = "connector_resource"


@dataclass(frozen=True, slots=True)
class ProviderDocumentationSourceDefinition:
    source_id: str
    provider_id: str
    display_name: str
    authority: str
    retrieval_method: DocumentationRetrievalMethod
    locator: str
    content_type: str
    lifecycle_status: DocumentationSourceLifecycle
    approval_status: DocumentationSourceApproval
    technology_steward: str
    business_justification: str
    review_interval_days: int
    retirement_criteria: tuple[str, ...]
    allowed_resource_authorities: tuple[str, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        required = {
            "source_id": self.source_id,
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "authority": self.authority,
            "locator": self.locator,
            "content_type": self.content_type,
            "technology_steward": self.technology_steward,
            "business_justification": self.business_justification,
        }
        for name, value in required.items():
            if not str(value).strip():
                raise ValueError(f"{name} is required")

        if self.review_interval_days < 1:
            raise ValueError("review_interval_days must be at least one")

        if not self.retirement_criteria:
            raise ValueError("retirement_criteria must not be empty")

        if (
            self.lifecycle_status is DocumentationSourceLifecycle.AVAILABLE
            and self.approval_status
            not in {
                DocumentationSourceApproval.APPROVED,
                DocumentationSourceApproval.PILOT,
            }
        ):
            raise ValueError(
                "available documentation sources must be approved or pilot"
            )

    def as_context(self) -> Mapping[str, object]:
        return {
            "source_id": self.source_id,
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "authority": self.authority,
            "retrieval_method": self.retrieval_method.value,
            "locator": self.locator,
            "content_type": self.content_type,
            "lifecycle_status": self.lifecycle_status.value,
            "approval_status": self.approval_status.value,
            "technology_steward": self.technology_steward,
            "review_interval_days": self.review_interval_days,
            "allowed_resource_authorities": self.allowed_resource_authorities,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class ProviderDocumentationSourceQuery:
    provider_id: str
    documentation_name: str | None = None
    resource_authority: str | None = None

    def __post_init__(self) -> None:
        if not self.provider_id.strip():
            raise ValueError("provider_id is required")


class ProviderDocumentationSourceRegistry:
    def __init__(self) -> None:
        self._sources: dict[str, ProviderDocumentationSourceDefinition] = {}

    def register(
        self,
        source: ProviderDocumentationSourceDefinition,
    ) -> None:
        if source.source_id in self._sources:
            raise ValueError(
                f"documentation source already registered: {source.source_id}"
            )
        self._sources[source.source_id] = source

    def get(
        self,
        source_id: str,
    ) -> ProviderDocumentationSourceDefinition:
        try:
            return self._sources[source_id]
        except KeyError as exc:
            raise KeyError(
                f"documentation source is not registered: {source_id}"
            ) from exc

    def list_all(
        self,
    ) -> tuple[ProviderDocumentationSourceDefinition, ...]:
        return tuple(
            sorted(
                self._sources.values(),
                key=lambda item: item.source_id.casefold(),
            )
        )

    def find(
        self,
        query: ProviderDocumentationSourceQuery,
    ) -> tuple[ProviderDocumentationSourceDefinition, ...]:
        results: list[ProviderDocumentationSourceDefinition] = []

        for source in self._sources.values():
            if source.provider_id != query.provider_id:
                continue

            if (
                source.lifecycle_status
                is not DocumentationSourceLifecycle.AVAILABLE
            ):
                continue

            if source.approval_status not in {
                DocumentationSourceApproval.APPROVED,
                DocumentationSourceApproval.PILOT,
            }:
                continue

            if query.documentation_name:
                requested = query.documentation_name.strip().casefold()
                names = {
                    source.display_name.strip().casefold(),
                    source.authority.strip().casefold(),
                }
                aliases = {
                    item.strip().casefold()
                    for item in str(
                        source.metadata.get("aliases", "")
                    ).split("|")
                    if item.strip()
                }
                if requested not in names | aliases:
                    continue

            if query.resource_authority:
                authority = query.resource_authority.strip().casefold()
                allowed = {
                    item.strip().casefold()
                    for item in source.allowed_resource_authorities
                }
                if allowed and authority not in allowed:
                    continue

            results.append(source)

        return tuple(
            sorted(
                results,
                key=lambda item: item.source_id.casefold(),
            )
        )


@dataclass(frozen=True, slots=True)
class GovernedDocumentationSourceResolver:
    registry: ProviderDocumentationSourceRegistry

    def resolve(
        self,
        *,
        provider_id: str,
        documentation_name: str,
        resource_authority: str | None = None,
    ) -> ProviderDocumentationSourceDefinition:
        matches = self.registry.find(
            ProviderDocumentationSourceQuery(
                provider_id=provider_id,
                documentation_name=documentation_name,
                resource_authority=resource_authority,
            )
        )

        if not matches:
            raise LookupError(
                "no approved governed documentation source matches the review target"
            )

        if len(matches) > 1:
            raise LookupError(
                "governed documentation source resolution is ambiguous"
            )

        return matches[0]
