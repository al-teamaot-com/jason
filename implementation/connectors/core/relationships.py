from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Mapping


class RelationshipState(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    REVOKED = "revoked"
    SUPERSEDED = "superseded"
    RETIRED = "retired"


class VerificationState(str, Enum):
    UNKNOWN = "unknown"
    REPORTED = "reported"
    INFERRED = "inferred"
    DISCOVERED = "discovered"
    CORROBORATED = "corroborated"
    VERIFIED = "verified"
    DISPUTED = "disputed"
    REJECTED = "rejected"


CANONICAL_RELATIONSHIPS = frozenset(
    {
        "owns",
        "belongs_to",
        "contains",
        "represents",
        "maps_to",
        "requests",
        "performs",
        "affects",
        "supports",
        "depends_on",
        "governs",
        "approves",
        "authorizes",
        "is_accountable_for",
        "is_responsible_for",
        "documents",
        "references",
        "provides_evidence_for",
        "supersedes",
        "connects_to",
        "communicates_with",
        "monitors",
        "protects",
    }
)


@dataclass(frozen=True, slots=True)
class ResourceRef:
    provider: str
    resource_type: str
    external_id: str
    organization_id: str
    tenant_id: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderRelationshipEvidence:
    provider: str
    source: ResourceRef
    target: ResourceRef
    provider_relationship: str
    canonical_relationship: str
    verification: VerificationState
    confidence: float
    observed_at: datetime
    source_authority: str
    metadata: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if self.canonical_relationship not in CANONICAL_RELATIONSHIPS:
            raise ValueError(
                f"Unknown canonical relationship: {self.canonical_relationship}"
            )
        if self.source.organization_id != self.target.organization_id:
            raise ValueError(
                "Cross-organization relationship evidence requires an explicit governed cross-tenant boundary."
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Relationship confidence must be between 0 and 1.")


@dataclass(frozen=True, slots=True)
class CanonicalRelationship:
    relationship_id: str
    relationship_type: str
    source: ResourceRef
    target: ResourceRef
    state: RelationshipState
    verification: VerificationState
    confidence: float
    established_by: str
    provenance: tuple[str, ...]
    effective_at: datetime
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.relationship_type not in CANONICAL_RELATIONSHIPS:
            raise ValueError(
                f"Unknown canonical relationship: {self.relationship_type}"
            )
        if self.source.organization_id != self.target.organization_id:
            raise ValueError(
                "Canonical cross-organization relationships require a separate governed admission path."
            )
        if not self.provenance:
            raise ValueError("Canonical relationships require provenance.")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Relationship confidence must be between 0 and 1.")


def promote_provider_evidence(
    evidence: ProviderRelationshipEvidence,
    *,
    relationship_id: str,
    established_by: str,
    state: RelationshipState = RelationshipState.ACTIVE,
) -> CanonicalRelationship:
    if evidence.verification not in {
        VerificationState.CORROBORATED,
        VerificationState.VERIFIED,
    }:
        raise ValueError(
            "Provider relationship evidence must be corroborated or verified before canonical promotion."
        )

    return CanonicalRelationship(
        relationship_id=relationship_id,
        relationship_type=evidence.canonical_relationship,
        source=evidence.source,
        target=evidence.target,
        state=state,
        verification=evidence.verification,
        confidence=evidence.confidence,
        established_by=established_by,
        provenance=(
            f"provider:{evidence.provider}",
            f"authority:{evidence.source_authority}",
            f"observed:{evidence.observed_at.isoformat()}",
        ),
        effective_at=evidence.observed_at,
    )
