from orchestrator.provider_capability_discovery import (
    ProviderCapabilityDiscoveryAssessment,
    ProviderCapabilityDiscoveryCandidate,
)
from orchestrator.provider_documentation_review import GovernedProviderDocumentationReviewPlanner


def test_discovery_candidates_become_review_only_documentation_targets():
    discovery = ProviderCapabilityDiscoveryAssessment(
        unsupported_facts=("example governed fact",),
        candidates=(
            ProviderCapabilityDiscoveryCandidate(
                provider_id="example_provider",
                display_name="Example Provider",
                registered_capabilities=("endpoint.device.search",),
                vendor_change_sources=("Example Provider API documentation",),
                technology_steward="technology-steward",
                resource_authority="managed_endpoint",
                connector_id="example_connector",
            ),
        ),
    )

    plan = GovernedProviderDocumentationReviewPlanner().plan(discovery=discovery)

    assert plan.review_only is True
    assert plan.governance_owner == "technology-steward"
    assert len(plan.targets) == 1
    target = plan.targets[0]
    assert target.provider_id == "example_provider"
    assert target.documentation_source == "Example Provider API documentation"
    assert target.unsupported_facts == ("example governed fact",)
    assert target.resource_authority == "managed_endpoint"
    assert target.connector_id == "example_connector"


def test_documentation_review_plan_does_not_claim_semantic_support():
    discovery = ProviderCapabilityDiscoveryAssessment(
        unsupported_facts=("unknown fact",),
        candidates=(
            ProviderCapabilityDiscoveryCandidate(
                provider_id="provider_a",
                display_name="Provider A",
                registered_capabilities=("resource.read",),
                vendor_change_sources=("Provider A docs", "Provider A schema"),
                technology_steward="technology-steward",
            ),
        ),
    )

    context = GovernedProviderDocumentationReviewPlanner().plan(discovery=discovery).as_context()

    assert context["review_only"] is True
    assert len(context["targets"]) == 2
    rule = str(context["interpretation_rule"])
    assert "candidate evidence only" in rule
    assert "No semantic mapping" in rule
