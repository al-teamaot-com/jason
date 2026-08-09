from datetime import datetime, timezone

import pytest

from connectors.core.relationships import (
    CanonicalPromotionPolicy,
    ProviderRelationshipEvidence,
    ResourceRef,
    VerificationState,
    promote_provider_evidence,
)


def _evidence(*, organization_id="org-a", confidence=0.99, verification=VerificationState.VERIFIED):
    return ProviderRelationshipEvidence(
        provider="jason_resource_convergence",
        source=ResourceRef("microsoft_graph", "user", "u-1", organization_id),
        target=ResourceRef("autotask", "contact", "c-1", organization_id),
        provider_relationship="governed_identity_corroboration",
        canonical_relationship="represents",
        verification=verification,
        confidence=confidence,
        observed_at=datetime(2026, 8, 9, 19, 30, tzinfo=timezone.utc),
        source_authority="central-orchestrator:graph+autotask",
    )


def _policy(**overrides):
    values = dict(
        policy_id="relationship-promotion",
        policy_version="1",
        organization_id="org-a",
        allowed_relationships=frozenset({"represents"}),
        minimum_confidence=0.95,
        allowed_verification_states=frozenset({VerificationState.VERIFIED}),
        allowed_source_providers=frozenset({"microsoft_graph"}),
        allowed_target_providers=frozenset({"autotask"}),
    )
    values.update(overrides)
    return CanonicalPromotionPolicy(**values)


def test_explicit_policy_promotes_verified_relationship():
    relationship = promote_provider_evidence(
        _evidence(),
        relationship_id="rel-1",
        established_by="central-orchestrator",
        policy=_policy(),
    )
    assert relationship.relationship_id == "rel-1"
    assert relationship.relationship_type == "represents"
    assert relationship.source.organization_id == "org-a"
    assert "promotion-policy:relationship-promotion@1" in relationship.provenance


def test_corroborated_evidence_does_not_promote_under_verified_only_policy():
    with pytest.raises(PermissionError, match="verification state"):
        promote_provider_evidence(
            _evidence(verification=VerificationState.CORROBORATED),
            relationship_id="rel-2",
            established_by="central-orchestrator",
            policy=_policy(),
        )


def test_low_confidence_evidence_fails_closed():
    with pytest.raises(PermissionError, match="confidence"):
        promote_provider_evidence(
            _evidence(confidence=0.90),
            relationship_id="rel-3",
            established_by="central-orchestrator",
            policy=_policy(),
        )


def test_cross_policy_organization_fails_closed():
    with pytest.raises(PermissionError, match="organization mismatch"):
        promote_provider_evidence(
            _evidence(organization_id="org-b"),
            relationship_id="rel-4",
            established_by="central-orchestrator",
            policy=_policy(),
        )


def test_unapproved_provider_pair_fails_closed():
    evidence = ProviderRelationshipEvidence(
        provider="jason_resource_convergence",
        source=ResourceRef("it_glue", "configuration", "cfg-1", "org-a"),
        target=ResourceRef("datto_rmm", "device", "dev-1", "org-a"),
        provider_relationship="governed_identity_corroboration",
        canonical_relationship="represents",
        verification=VerificationState.VERIFIED,
        confidence=1.0,
        observed_at=datetime(2026, 8, 9, 19, 30, tzinfo=timezone.utc),
        source_authority="central-orchestrator:itglue+datto",
    )
    with pytest.raises(PermissionError, match="source provider"):
        promote_provider_evidence(
            evidence,
            relationship_id="rel-5",
            established_by="central-orchestrator",
            policy=_policy(),
        )
