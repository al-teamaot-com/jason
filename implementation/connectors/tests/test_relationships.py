from datetime import datetime, timezone

import pytest

from connectors.core.relationships import (
    CanonicalPromotionPolicy,
    ProviderRelationshipEvidence,
    RelationshipState,
    ResourceRef,
    VerificationState,
    promote_provider_evidence,
)


def ref(provider: str, resource_type: str, external_id: str) -> ResourceRef:
    return ResourceRef(provider=provider, resource_type=resource_type, external_id=external_id, organization_id="org-208", tenant_id="tenant-208")


def policy(*, minimum_confidence: float = 1.0) -> CanonicalPromotionPolicy:
    return CanonicalPromotionPolicy(
        policy_id="relationship-promotion",
        policy_version="1.0.0",
        organization_id="org-208",
        allowed_relationships=frozenset({"belongs_to", "represents"}),
        minimum_confidence=minimum_confidence,
        allowed_verification_states=frozenset({VerificationState.VERIFIED}),
    )


def test_verified_provider_relationship_can_be_promoted() -> None:
    observed = datetime(2026, 8, 8, 15, 0, tzinfo=timezone.utc)
    evidence = ProviderRelationshipEvidence(
        provider="datto_rmm", source=ref("datto_rmm", "device", "device-1"),
        target=ref("autotask", "company", "208"), provider_relationship="site_company_mapping",
        canonical_relationship="belongs_to", verification=VerificationState.VERIFIED,
        confidence=1.0, observed_at=observed, source_authority="governed-provider-read",
    )
    relationship = promote_provider_evidence(
        evidence, relationship_id="rel-001", established_by="central-orchestrator", policy=policy()
    )
    assert relationship.relationship_type == "belongs_to"
    assert relationship.state is RelationshipState.ACTIVE
    assert relationship.verification is VerificationState.VERIFIED
    assert relationship.source.provider == "datto_rmm"
    assert relationship.target.provider == "autotask"
    assert relationship.provenance[0] == "provider:datto_rmm"
    assert relationship.provenance[-1] == "promotion-policy:relationship-promotion@1.0.0"


def test_unverified_provider_link_cannot_become_canonical_truth() -> None:
    evidence = ProviderRelationshipEvidence(
        provider="it_glue", source=ref("it_glue", "configuration", "10"),
        target=ref("datto_rmm", "device", "device-1"), provider_relationship="name_match",
        canonical_relationship="represents", verification=VerificationState.INFERRED,
        confidence=0.6, observed_at=datetime.now(timezone.utc), source_authority="bounded-discovery",
    )
    with pytest.raises(PermissionError, match="verification state"):
        promote_provider_evidence(
            evidence, relationship_id="rel-002", established_by="central-orchestrator", policy=policy(minimum_confidence=0.5)
        )


def test_cross_organization_provider_link_fails_closed() -> None:
    with pytest.raises(ValueError, match="Cross-organization"):
        ProviderRelationshipEvidence(
            provider="microsoft_graph",
            source=ResourceRef(provider="microsoft_graph", resource_type="user", external_id="user-1", organization_id="org-a"),
            target=ResourceRef(provider="autotask", resource_type="contact", external_id="contact-1", organization_id="org-b"),
            provider_relationship="email_match", canonical_relationship="represents",
            verification=VerificationState.CORROBORATED, confidence=0.9,
            observed_at=datetime.now(timezone.utc), source_authority="bounded-discovery",
        )


def test_unknown_relationship_type_fails_closed() -> None:
    with pytest.raises(ValueError, match="Unknown canonical relationship"):
        ProviderRelationshipEvidence(
            provider="it_glue", source=ref("it_glue", "configuration", "10"), target=ref("autotask", "company", "208"),
            provider_relationship="custom", canonical_relationship="looks_like", verification=VerificationState.VERIFIED,
            confidence=1.0, observed_at=datetime.now(timezone.utc), source_authority="governed-provider-read",
        )
