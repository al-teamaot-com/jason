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


@dataclass(frozen=True, slots=True)
class CanonicalPromotionPolicy:
    """Versioned policy-as-data for admitting provider evidence as canonical truth."""

    policy_id: str
    policy_version: str
    organization_id: str
    allowed_relationships: frozenset[str]
    minimum_confidence: float = 1.0
    allowed_verification_states: frozenset[VerificationState] = frozenset(
        {VerificationState.VERIFIED}
    )
    allowed_source_providers: frozenset[str] | None = None
    allowed_target_providers: frozenset[str] | None = None

    def __post_init__(self) -> None:
        if not self.policy_id.strip() or not self.policy_version.strip():
            raise ValueError("canonical promotion policy id and version are required")
        if not self.organization_id.strip():
            raise ValueError("canonical promotion policy organization is required")
        if not self.allowed_relationships:
            raise ValueError("canonical promotion policy requires allowed relationships")
        unknown = self.allowed_relationships - CANONICAL_RELATIONSHIPS
        if unknown:
            raise ValueError(f"canonical promotion policy contains unknown relationships: {sorted(unknown)}")
        if not 0.0 <= self.minimum_confidence <= 1.0:
            raise ValueError("canonical promotion minimum confidence must be between 0 and 1")
        if not self.allowed_verification_states:
            raise ValueError("canonical promotion policy requires verification states")

    def authorize(self, evidence: ProviderRelationshipEvidence) -> None:
        if evidence.source.organization_id != self.organization_id:
            raise PermissionError("canonical promotion policy organization mismatch")
        if evidence.target.organization_id != self.organization_id:
            raise PermissionError("canonical promotion target organization mismatch")
        if evidence.canonical_relationship not in self.allowed_relationships:
            raise PermissionError("canonical relationship is not allowed by promotion policy")
        if evidence.verification not in self.allowed_verification_states:
            raise PermissionError("relationship verification state is not allowed by promotion policy")
        if evidence.confidence < self.minimum_confidence:
            raise PermissionError("relationship confidence is below promotion policy threshold")
        if self.allowed_source_providers is not None:
            if evidence.source.provider not in self.allowed_source_providers:
                raise PermissionError("relationship source provider is not allowed by promotion policy")
        if self.allowed_target_providers is not None:
            if evidence.target.provider not in self.allowed_target_providers:
                raise PermissionError("relationship target provider is not allowed by promotion policy")


def promote_provider_evidence(
    evidence: ProviderRelationshipEvidence,
    *,
    relationship_id: str,
    established_by: str,
    policy: CanonicalPromotionPolicy,
    state: RelationshipState = RelationshipState.ACTIVE,
) -> CanonicalRelationship:
    """Promote evidence only after an explicit versioned policy admits it.

    Provider evidence never becomes canonical truth merely because a provider read
    succeeded or because evidence is corroborated. Promotion is an independent
    governed decision. This function grants no execution authority.
    """
    if not relationship_id.strip() or not established_by.strip():
        raise ValueError("canonical promotion relationship_id and established_by are required")
    policy.authorize(evidence)

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
            f"promotion-policy:{policy.policy_id}@{policy.policy_version}",
        ),
        effective_at=evidence.observed_at,
    )
