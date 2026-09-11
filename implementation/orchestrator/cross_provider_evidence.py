from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from connectors.core.relationships import ResourceRef

from .canonical_entity_correlation import (
    CanonicalEntityCorrelationRegistry,
    CanonicalEntityMapping,
    CanonicalEntityType,
    CorrelationResolution,
)
from .contracts import OrchestrationResult, OrchestrationStatus
from .evidence_sanitization import sanitize_evidence_tree
from .governed_evidence_cache import FreshnessClass


class CrossProviderEvidenceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CorrelatedResourcePlan:
    canonical_id: str
    entity_type: CanonicalEntityType
    organization_id: str
    seed: ResourceRef
    resources: tuple[ResourceRef, ...]
    mappings: tuple[CanonicalEntityMapping, ...]


@dataclass(frozen=True, slots=True)
class ProviderEvidenceObservation:
    provider_id: str
    capability_name: str
    provider_capability: str | None
    freshness: FreshnessClass
    observed_at: datetime
    evidence_references: tuple[str, ...]
    source_references: tuple[str, ...]
    data: Any

    def __post_init__(self) -> None:
        if not self.provider_id.strip() or not self.capability_name.strip():
            raise ValueError("provider observation requires provider and capability")
        if self.observed_at.tzinfo is None:
            raise ValueError("provider observation timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class GovernedCrossProviderEvidencePackage:
    correlation_id: str
    principal_id: str
    organization_id: str
    client_id: str | None
    created_at: datetime
    canonical_ids: tuple[str, ...]
    observations: tuple[ProviderEvidenceObservation, ...]
    mappings: tuple[CanonicalEntityMapping, ...]
    ambiguity_notes: tuple[str, ...]
    hosted_model_used_by_jason: bool
    hosted_model_input_tokens: int
    hosted_model_output_tokens: int
    hosted_model_cost_usd: str
    package_sha256: str

    def __post_init__(self) -> None:
        if not self.correlation_id.strip() or not self.principal_id.strip():
            raise ValueError("evidence package requires correlation and principal")
        if not self.organization_id.strip():
            raise ValueError("evidence package requires organization")
        if self.created_at.tzinfo is None:
            raise ValueError("evidence package timestamp must be timezone-aware")
        if self.hosted_model_input_tokens < 0 or self.hosted_model_output_tokens < 0:
            raise ValueError("hosted model token counts must not be negative")
        if not self.hosted_model_used_by_jason:
            if self.hosted_model_input_tokens or self.hosted_model_output_tokens:
                raise ValueError("zero-model evidence package cannot report model tokens")
            if self.hosted_model_cost_usd not in {"0", "0.0", "0.00", "0.000000"}:
                raise ValueError("zero-model evidence package must report zero model cost")


def plan_correlated_resources(
    *,
    seed: ResourceRef,
    entity_type: CanonicalEntityType,
    registry: CanonicalEntityCorrelationRegistry,
    target_providers: Iterable[str],
) -> CorrelatedResourcePlan:
    """Expand a known provider identity into unambiguous canonical peer resources.

    The seed must map to exactly one canonical entity. Every requested provider must
    then resolve without ambiguity. Inferred mappings remain visible through their
    provenance/confidence but are never represented as authoritative by this plan.
    """

    canonical_candidates = registry.canonical_for_resource(
        resource=seed,
        entity_type=entity_type,
    )
    canonical_ids = {item.canonical_id for item in canonical_candidates}
    if not canonical_candidates:
        raise LookupError("seed resource has no governed canonical mapping")
    if len(canonical_ids) != 1:
        raise CrossProviderEvidenceError("seed resource maps to multiple canonical entities")

    canonical_id = next(iter(canonical_ids))
    resources: list[ResourceRef] = [seed]
    mappings: list[CanonicalEntityMapping] = list(canonical_candidates)

    for provider in tuple(dict.fromkeys(target_providers)):
        if not provider.strip() or provider == seed.provider:
            continue
        resolution = registry.resolve_provider(
            canonical_id=canonical_id,
            entity_type=entity_type,
            organization_id=seed.organization_id,
            provider=provider,
        )
        _require_unambiguous_resolution(resolution)
        if resolution.selected is None:
            continue
        resources.append(resolution.selected.resource)
        mappings.append(resolution.selected)

    return CorrelatedResourcePlan(
        canonical_id=canonical_id,
        entity_type=entity_type,
        organization_id=seed.organization_id,
        seed=seed,
        resources=tuple(resources),
        mappings=_deduplicate_mappings(mappings),
    )


def build_evidence_package(
    *,
    correlation_id: str,
    principal_id: str,
    organization_id: str,
    client_id: str | None,
    results: Sequence[OrchestrationResult],
    freshness_by_capability: Mapping[str, FreshnessClass],
    mappings: Sequence[CanonicalEntityMapping] = (),
    source_references: Mapping[tuple[str, str], tuple[str, ...]] | None = None,
    ambiguity_notes: Sequence[str] = (),
    created_at: datetime | None = None,
) -> GovernedCrossProviderEvidencePackage:
    """Compose successful governed reads into one sanitized reasoning package.

    This is deterministic composition only. No hosted model is called. Provider data
    remains evidence with provider/capability/source provenance; correlation mappings
    retain their basis, verification state and confidence for downstream reasoning.
    """

    if not results:
        raise CrossProviderEvidenceError("at least one provider result is required")
    observations: list[ProviderEvidenceObservation] = []
    observed_at = (created_at or datetime.now(timezone.utc)).astimezone(timezone.utc)

    for result in results:
        if result.correlation_id != correlation_id:
            raise CrossProviderEvidenceError("provider result correlation_id mismatch")
        if result.status is not OrchestrationStatus.SUCCEEDED:
            raise CrossProviderEvidenceError("failed or denied provider result cannot enter evidence package")
        provider_id = (result.provider_id or "").strip()
        output_provider = str(result.output.get("provider", "")).strip()
        if not provider_id or output_provider != provider_id:
            raise CrossProviderEvidenceError("provider result provenance is missing or inconsistent")
        if "data" not in result.output:
            raise CrossProviderEvidenceError("provider result is missing evidence data")
        freshness = freshness_by_capability.get(result.capability_name)
        if freshness is None:
            raise CrossProviderEvidenceError(
                f"freshness class is required for capability: {result.capability_name}"
            )
        raw_evidence = result.output.get("evidence_ids", ())
        evidence_references = tuple(str(item) for item in raw_evidence if str(item).strip())
        source_key = (provider_id, result.capability_name)
        observations.append(
            ProviderEvidenceObservation(
                provider_id=provider_id,
                capability_name=result.capability_name,
                provider_capability=(
                    str(result.output.get("provider_capability")).strip()
                    if result.output.get("provider_capability") is not None
                    else None
                ),
                freshness=freshness,
                observed_at=observed_at,
                evidence_references=evidence_references,
                source_references=tuple((source_references or {}).get(source_key, ())),
                data=sanitize_evidence_tree(result.output["data"]),
            )
        )

    for mapping in mappings:
        if mapping.organization_id != organization_id:
            raise CrossProviderEvidenceError("correlation mapping organization mismatch")

    canonical_ids = tuple(sorted({mapping.canonical_id for mapping in mappings}))
    payload = {
        "correlation_id": correlation_id,
        "principal_id": principal_id,
        "organization_id": organization_id,
        "client_id": client_id,
        "canonical_ids": canonical_ids,
        "observations": [
            {
                "provider_id": item.provider_id,
                "capability_name": item.capability_name,
                "provider_capability": item.provider_capability,
                "freshness": item.freshness.value,
                "observed_at": item.observed_at.isoformat(),
                "evidence_references": item.evidence_references,
                "source_references": item.source_references,
                "data": item.data,
            }
            for item in observations
        ],
        "mappings": [
            {
                "canonical_id": item.canonical_id,
                "entity_type": item.entity_type.value,
                "provider": item.resource.provider,
                "resource_type": item.resource.resource_type,
                "external_id": item.resource.external_id,
                "basis": item.basis.value,
                "verification": item.verification.value,
                "confidence": item.confidence,
                "provenance": item.provenance,
                "source_version": item.source_version,
            }
            for item in mappings
        ],
        "ambiguity_notes": tuple(ambiguity_notes),
        "hosted_model_used_by_jason": False,
        "hosted_model_input_tokens": 0,
        "hosted_model_output_tokens": 0,
        "hosted_model_cost_usd": "0",
    }
    package_hash = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()

    return GovernedCrossProviderEvidencePackage(
        correlation_id=correlation_id,
        principal_id=principal_id,
        organization_id=organization_id,
        client_id=client_id,
        created_at=observed_at,
        canonical_ids=canonical_ids,
        observations=tuple(observations),
        mappings=tuple(mappings),
        ambiguity_notes=tuple(ambiguity_notes),
        hosted_model_used_by_jason=False,
        hosted_model_input_tokens=0,
        hosted_model_output_tokens=0,
        hosted_model_cost_usd="0",
        package_sha256=package_hash,
    )


def _require_unambiguous_resolution(resolution: CorrelationResolution) -> None:
    if resolution.ambiguous:
        raise CrossProviderEvidenceError(
            f"canonical mapping is ambiguous for provider: {resolution.provider}"
        )


def _deduplicate_mappings(
    mappings: Sequence[CanonicalEntityMapping],
) -> tuple[CanonicalEntityMapping, ...]:
    seen: set[tuple[str, str, str]] = set()
    result: list[CanonicalEntityMapping] = []
    for item in mappings:
        key = (
            item.canonical_id,
            item.resource.provider,
            item.resource.external_id,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return tuple(result)
