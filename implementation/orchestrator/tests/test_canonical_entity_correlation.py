from datetime import datetime, timezone

import pytest

from connectors.core.relationships import ResourceRef, VerificationState
from orchestrator.canonical_entity_correlation import (
    CanonicalEntityCorrelationRegistry,
    CanonicalEntityMapping,
    CanonicalEntityType,
    CorrelationBasis,
)


NOW = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)


def mapping(
    provider,
    external_id,
    *,
    canonical_id="endpoint:aot-50282",
    basis=CorrelationBasis.CORROBORATED,
    verification=VerificationState.CORROBORATED,
    confidence=0.98,
    resource_type="device",
):
    return CanonicalEntityMapping(
        canonical_id=canonical_id,
        entity_type=CanonicalEntityType.ENDPOINT,
        organization_id="aot",
        resource=ResourceRef(
            provider=provider,
            resource_type=resource_type,
            external_id=external_id,
            organization_id="aot",
        ),
        basis=basis,
        verification=verification,
        confidence=confidence,
        provenance=(f"provider:{provider}", "match:serial+hostname"),
        observed_at=NOW,
    )


def test_configured_mapping_outranks_inferred_mapping() -> None:
    registry = CanonicalEntityCorrelationRegistry(
        (
            mapping(
                "autotask",
                "ci-inferred",
                basis=CorrelationBasis.INFERRED,
                verification=VerificationState.INFERRED,
                confidence=0.99,
                resource_type="configuration_item",
            ),
            mapping(
                "autotask",
                "ci-configured",
                basis=CorrelationBasis.CONFIGURED,
                verification=VerificationState.VERIFIED,
                confidence=1.0,
                resource_type="configuration_item",
            ),
        )
    )

    result = registry.resolve_provider(
        canonical_id="endpoint:aot-50282",
        entity_type=CanonicalEntityType.ENDPOINT,
        organization_id="aot",
        provider="autotask",
    )

    assert result.selected is not None
    assert result.selected.resource.external_id == "ci-configured"
    assert result.authoritative is True
    assert result.ambiguous is False


def test_equal_strength_conflicting_mappings_remain_ambiguous() -> None:
    registry = CanonicalEntityCorrelationRegistry(
        (
            mapping("it_glue", "config-1"),
            mapping("it_glue", "config-2"),
        )
    )

    result = registry.resolve_provider(
        canonical_id="endpoint:aot-50282",
        entity_type=CanonicalEntityType.ENDPOINT,
        organization_id="aot",
        provider="it_glue",
    )

    assert result.selected is None
    assert result.ambiguous is True
    assert result.authoritative is False


def test_inferred_mapping_can_never_claim_verified_certain_identity() -> None:
    with pytest.raises(ValueError, match="inferred correlation"):
        mapping(
            "datto_rmm",
            "device-1",
            basis=CorrelationBasis.INFERRED,
            verification=VerificationState.VERIFIED,
            confidence=1.0,
        )


def test_three_provider_endpoint_mapping_retains_provenance_and_confidence() -> None:
    registry = CanonicalEntityCorrelationRegistry(
        (
            mapping(
                "autotask",
                "ci-77",
                basis=CorrelationBasis.EXPLICIT,
                verification=VerificationState.VERIFIED,
                confidence=1.0,
                resource_type="configuration_item",
            ),
            mapping("it_glue", "config-42", resource_type="configuration"),
            mapping(
                "datto_rmm",
                "device-50282",
                basis=CorrelationBasis.EXPLICIT,
                verification=VerificationState.VERIFIED,
                confidence=1.0,
            ),
        )
    )

    all_mappings = registry.mappings_for(
        canonical_id="endpoint:aot-50282",
        entity_type=CanonicalEntityType.ENDPOINT,
        organization_id="aot",
    )

    assert {item.resource.provider for item in all_mappings} == {
        "autotask",
        "it_glue",
        "datto_rmm",
    }
    assert all(item.provenance for item in all_mappings)
    assert all(0.0 <= item.confidence <= 1.0 for item in all_mappings)


def test_cross_organization_mapping_is_rejected() -> None:
    with pytest.raises(ValueError, match="organization"):
        CanonicalEntityMapping(
            canonical_id="person:1",
            entity_type=CanonicalEntityType.PERSON,
            organization_id="aot",
            resource=ResourceRef(
                provider="autotask",
                resource_type="contact",
                external_id="7",
                organization_id="other-org",
            ),
            basis=CorrelationBasis.EXPLICIT,
            verification=VerificationState.VERIFIED,
            confidence=1.0,
            provenance=("configured:mapping-table",),
            observed_at=NOW,
        )
