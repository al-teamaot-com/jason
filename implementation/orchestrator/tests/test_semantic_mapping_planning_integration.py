from orchestrator.planning_context_views import PlanningContextRequest
from orchestrator.semantic_mapping_capability_overlay import (
    GovernedSemanticMappingCapabilityOverlay,
)
from orchestrator.semantic_mapping_planning_context import (
    SemanticMappingPlanningContextProvider,
)
from orchestrator.semantic_mapping_registry import (
    ApprovedSemanticMapping,
    SemanticMappingRegistry,
)


def mapping():
    return ApprovedSemanticMapping(
        mapping_id="example-release",
        version=1,
        provider_id="example_provider",
        canonical_fact="operating system release name",
        provider_schema="Device",
        provider_field="releaseName",
        resource_authority="managed_endpoint",
        approval_status="approved",
        approved_by="technology-steward",
        approval_basis="authoritative cross-source evidence",
        openapi_source_reference="openapi:test",
        semantic_source_reference="help:test",
        capability_names=(
            "endpoint.device.search",
            "endpoint.device.read",
        ),
        active=True,
    )


def test_overlay_adds_approved_fact_to_bound_capabilities_only():
    registry = SemanticMappingRegistry((mapping(),))

    records = (
        {
            "capability_name": "endpoint.device.search",
            "fact_hints": "hostname,operating system",
        },
        {
            "capability_name": "endpoint.audit.read",
            "fact_hints": "bios,memory",
        },
    )

    overlaid = GovernedSemanticMappingCapabilityOverlay(
        registry=registry,
    ).apply(
        capability_records=records,
    )

    assert "operating system release name" in overlaid[0]["fact_hints"]
    assert (
        "operating system release name"
        not in overlaid[1]["fact_hints"]
    )


def test_semantic_context_exposes_only_active_approved_mapping():
    provider = SemanticMappingPlanningContextProvider(
        registry=SemanticMappingRegistry((mapping(),)),
        view_name="semantic_knowledge",
    )

    view = provider.read(
        PlanningContextRequest(
            view_name="semantic_knowledge",
            query="operating system release name",
            limit=10,
        )
    )

    assert len(view.items) == 1
    assert (
        view.items[0]["provider_field"]
        == "releaseName"
    )
    assert view.items[0]["approval_status"] == "approved"


def test_derivation_context_exposes_evidence_backed_mapping():
    provider = SemanticMappingPlanningContextProvider(
        registry=SemanticMappingRegistry((mapping(),)),
        view_name="derivations",
    )

    view = provider.read(
        PlanningContextRequest(
            view_name="derivations",
            query="operating system release name",
            limit=10,
        )
    )

    assert len(view.items) == 1
    assert view.items[0]["approved"] is True
    assert view.items[0]["provider_field"] == "releaseName"
