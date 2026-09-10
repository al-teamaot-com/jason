from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterable

from connectors.core.relationships import ResourceRef, VerificationState


class CanonicalEntityType(str, Enum):
    ORGANIZATION = "organization"
    ENDPOINT = "endpoint"
    PERSON = "person"


class CorrelationBasis(str, Enum):
    """Ordered evidence basis for provider-to-canonical identity mappings."""

    CONFIGURED = "configured"
    EXPLICIT = "explicit"
    CORROBORATED = "corroborated"
    INFERRED = "inferred"


_BASIS_RANK = {
    CorrelationBasis.CONFIGURED: 400,
    CorrelationBasis.EXPLICIT: 300,
    CorrelationBasis.CORROBORATED: 200,
    CorrelationBasis.INFERRED: 100,
}


@dataclass(frozen=True, slots=True)
class CanonicalEntityMapping:
    canonical_id: str
    entity_type: CanonicalEntityType
    organization_id: str
    resource: ResourceRef
    basis: CorrelationBasis
    verification: VerificationState
    confidence: float
    provenance: tuple[str, ...]
    observed_at: datetime
    source_version: str | None = None

    def __post_init__(self) -> None:
        if not self.canonical_id.strip():
            raise ValueError("canonical_id is required")
        if not self.organization_id.strip():
            raise ValueError("organization_id is required")
        if self.resource.organization_id != self.organization_id:
            raise ValueError("provider resource organization must match canonical mapping organization")
        if not self.resource.provider.strip() or not self.resource.resource_type.strip():
            raise ValueError("provider and resource_type are required")
        if not self.resource.external_id.strip():
            raise ValueError("provider external_id is required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("correlation confidence must be between 0 and 1")
        if not self.provenance or not all(item.strip() for item in self.provenance):
            raise ValueError("correlation mapping requires non-empty provenance")
        if self.observed_at.tzinfo is None:
            raise ValueError("correlation mapping observed_at must be timezone-aware")

        # Inference may be useful routing evidence, but it must never silently
        # acquire a verification state that implies certainty.
        if self.basis is CorrelationBasis.INFERRED and self.verification in {
            VerificationState.VERIFIED,
            VerificationState.CORROBORATED,
        }:
            raise ValueError("inferred correlation cannot be silently promoted to certain evidence")

    @property
    def authoritative(self) -> bool:
        return (
            self.basis in {CorrelationBasis.CONFIGURED, CorrelationBasis.EXPLICIT}
            and self.verification is VerificationState.VERIFIED
            and self.confidence == 1.0
        )


@dataclass(frozen=True, slots=True)
class CorrelationResolution:
    canonical_id: str
    entity_type: CanonicalEntityType
    organization_id: str
    provider: str
    candidates: tuple[CanonicalEntityMapping, ...]
    selected: CanonicalEntityMapping | None
    ambiguous: bool

    @property
    def authoritative(self) -> bool:
        return self.selected is not None and self.selected.authoritative and not self.ambiguous


class CanonicalEntityCorrelationRegistry:
    """Provider-neutral identity mapping registry with fail-closed precedence.

    The registry does not infer matches itself. Callers may supply inferred or
    corroborated evidence, but configured/explicit mappings always outrank them.
    Equal-rank conflicting candidates remain ambiguous instead of being silently
    resolved. This registry grants no provider access or execution authority.
    """

    def __init__(self, mappings: Iterable[CanonicalEntityMapping] = ()) -> None:
        self._mappings = tuple(mappings)
        self._validate_duplicates()

    def _validate_duplicates(self) -> None:
        seen: set[tuple[str, str, str, str, str]] = set()
        for mapping in self._mappings:
            key = (
                mapping.organization_id,
                mapping.entity_type.value,
                mapping.canonical_id,
                mapping.resource.provider,
                mapping.resource.external_id,
            )
            if key in seen:
                raise ValueError("duplicate canonical provider mapping")
            seen.add(key)

    def mappings_for(
        self,
        *,
        canonical_id: str,
        entity_type: CanonicalEntityType,
        organization_id: str,
        provider: str | None = None,
    ) -> tuple[CanonicalEntityMapping, ...]:
        matches = tuple(
            mapping
            for mapping in self._mappings
            if mapping.canonical_id == canonical_id
            and mapping.entity_type is entity_type
            and mapping.organization_id == organization_id
            and (provider is None or mapping.resource.provider == provider)
        )
        return tuple(
            sorted(
                matches,
                key=lambda item: (
                    -_BASIS_RANK[item.basis],
                    -item.confidence,
                    item.resource.provider,
                    item.resource.external_id,
                ),
            )
        )

    def resolve_provider(
        self,
        *,
        canonical_id: str,
        entity_type: CanonicalEntityType,
        organization_id: str,
        provider: str,
    ) -> CorrelationResolution:
        candidates = self.mappings_for(
            canonical_id=canonical_id,
            entity_type=entity_type,
            organization_id=organization_id,
            provider=provider,
        )
        if not candidates:
            return CorrelationResolution(
                canonical_id=canonical_id,
                entity_type=entity_type,
                organization_id=organization_id,
                provider=provider,
                candidates=(),
                selected=None,
                ambiguous=False,
            )

        best_rank = _BASIS_RANK[candidates[0].basis]
        best_confidence = candidates[0].confidence
        strongest = tuple(
            item
            for item in candidates
            if _BASIS_RANK[item.basis] == best_rank
            and item.confidence == best_confidence
        )
        external_ids = {item.resource.external_id for item in strongest}
        ambiguous = len(external_ids) != 1
        selected = None if ambiguous else strongest[0]

        return CorrelationResolution(
            canonical_id=canonical_id,
            entity_type=entity_type,
            organization_id=organization_id,
            provider=provider,
            candidates=candidates,
            selected=selected,
            ambiguous=ambiguous,
        )

    def canonical_for_resource(
        self,
        *,
        resource: ResourceRef,
        entity_type: CanonicalEntityType,
    ) -> tuple[CanonicalEntityMapping, ...]:
        return tuple(
            sorted(
                (
                    mapping
                    for mapping in self._mappings
                    if mapping.entity_type is entity_type
                    and mapping.organization_id == resource.organization_id
                    and mapping.resource.provider == resource.provider
                    and mapping.resource.resource_type == resource.resource_type
                    and mapping.resource.external_id == resource.external_id
                ),
                key=lambda item: (
                    -_BASIS_RANK[item.basis],
                    -item.confidence,
                    item.canonical_id,
                ),
            )
        )
