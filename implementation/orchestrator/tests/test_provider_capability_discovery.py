from datetime import datetime, timezone

from kernel.execution_providers import (
    ExecutionProvider,
    ProviderApproval,
    ProviderFeatures,
    ProviderHealth,
    ProviderLifecycle,
    ProviderLimits,
    ProviderStewardship,
    ProviderType,
)
from orchestrator.provider_capability_discovery import GovernedProviderCapabilityDiscovery
from orchestrator.semantic_capability_gap import SemanticCapabilityGapAssessment


def provider(*, provider_id: str, sources=()) -> ExecutionProvider:
    now = datetime.now(timezone.utc)
    return ExecutionProvider(
        provider_id=provider_id,
        display_name=provider_id.upper(),
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
        health_status=ProviderHealth.HEALTHY,
        approval_status=ProviderApproval.APPROVED,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset({"endpoint.device.search", "endpoint.device.read"}),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="test",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification="test provider",
            review_interval_days=90,
            last_reviewed_at=now,
            retirement_criteria=("retire when replaced",),
            vendor_change_sources=tuple(sources),
        ),
        created_at=now,
        metadata={"connector_id": provider_id, "resource_authority": "managed_endpoint"},
    )


def test_gap_discovers_only_registered_providers_with_authoritative_sources():
    gap = SemanticCapabilityGapAssessment(
        unsupported_facts=("special fact",),
        inspected_context_views=("capability_registry", "evidence_catalog", "derivation_registry"),
    )
    result = GovernedProviderCapabilityDiscovery().discover(
        gap=gap,
        providers=(
            provider(provider_id="provider_b", sources=("Vendor B API docs",)),
            provider(provider_id="provider_a", sources=("Vendor A API docs",)),
            provider(provider_id="provider_without_docs"),
        ),
    )

    assert result.review_only is True
    assert result.unsupported_facts == ("special fact",)
    assert tuple(item.provider_id for item in result.candidates) == ("provider_a", "provider_b")
    assert result.candidates[0].vendor_change_sources == ("Vendor A API docs",)
    assert result.candidates[0].connector_id == "provider_a"
    assert result.candidates[0].resource_authority == "managed_endpoint"


def test_discovery_does_not_claim_provider_support_for_gap():
    gap = SemanticCapabilityGapAssessment(
        unsupported_facts=("unknown fact",),
        inspected_context_views=("capability_registry", "evidence_catalog", "derivation_registry"),
    )
    result = GovernedProviderCapabilityDiscovery().discover(
        gap=gap,
        providers=(provider(provider_id="provider_a", sources=("Vendor A API docs",)),),
    )
    context = result.as_context()

    assert context["review_only"] is True
    assert context["unsupported_facts"] == ("unknown fact",)
    assert "supported_facts" not in context
    assert "semantic_mapping" not in context
    assert "selected_provider" not in context
