from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kernel.capabilities import (
    CapabilityApproval,
    CapabilityDefinition,
    CapabilityEvidence,
    CapabilityLifecycle,
    CapabilityRegistryService,
    CapabilityRisk,
    CapabilityStewardship,
    IdempotencyBehavior,
    InMemoryCapabilityRegistry,
)
from orchestrator.resource_inquiry import (
    GovernedResourceInquiryPlanner,
    ResourceInquiry,
    ResourcePlanStep,
)


NOW = datetime(2026, 8, 10, tzinfo=timezone.utc)


def capability(
    name: str,
    *,
    provider_neutral: bool = True,
    resource_types: str = "endpoint",
    read_only: bool = True,
):
    return CapabilityDefinition(
        capability_name=name,
        version="1.0",
        display_name=name,
        lifecycle_status=CapabilityLifecycle.ACTIVE,
        business_purpose="Retrieve governed endpoint information.",
        owner_service="Jason Resource Intelligence",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-013"}),
        risk_level=CapabilityRisk.LOW,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference="schema://resource-query/1.0",
        output_schema_reference="schema://resource-result/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(required=True, requirements=("provider result",)),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=30,
        maximum_attempts=1,
        failure_behavior="Fail closed.",
        tenant_isolation_required=True,
        client_isolation_required=True,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification="Use existing managed-resource data before custom collection.",
            review_interval_days=90,
            retirement_criteria=("Replaced by a governed equivalent.",),
        ),
        created_at=NOW,
        metadata={
            "provider_neutral": "true" if provider_neutral else "false",
            "resource_types": resource_types,
            "read_only": "true" if read_only else "false",
        },
    )


class Reasoner:
    def __init__(self, capability_name: str):
        self.capability_name = capability_name
        self.candidates = ()

    def select(self, *, inquiry, candidates):
        self.candidates = tuple(candidates)
        return (
            ResourcePlanStep(
                capability_name=self.capability_name,
                arguments={
                    **dict(inquiry.resource_selector),
                    "requested_facts": inquiry.requested_facts,
                },
                purpose="retrieve endpoint data containing the requested facts",
            ),
        )


def registry_service(*definitions: CapabilityDefinition) -> CapabilityRegistryService:
    registry = InMemoryCapabilityRegistry()
    service = CapabilityRegistryService(registry=registry)
    for definition in definitions:
        service.register(definition)
    return service


def inquiry() -> ResourceInquiry:
    return ResourceInquiry(
        resource_type="endpoint",
        resource_selector={"hostname": "AOT-50282"},
        requested_facts=("last logged in user",),
    )


def test_planner_lets_reasoner_choose_from_registered_provider_neutral_capabilities():
    reasoner = Reasoner("endpoint.device.search")
    planner = GovernedResourceInquiryPlanner(
        registry=registry_service(
            capability("endpoint.device.search"),
            capability("datto.device.search", provider_neutral=False),
            capability("ticket.record.search", resource_types="ticket"),
        ),
        reasoner=reasoner,
    )

    plan = planner.plan(inquiry())

    assert [item.capability_name for item in reasoner.candidates] == ["endpoint.device.search"]
    assert plan.steps[0].capability_name == "endpoint.device.search"
    assert plan.steps[0].arguments["hostname"] == "AOT-50282"
    assert plan.steps[0].arguments["requested_facts"] == ("last logged in user",)


def test_planner_rejects_provider_specific_capability_selected_by_reasoner():
    reasoner = Reasoner("datto.device.search")
    planner = GovernedResourceInquiryPlanner(
        registry=registry_service(
            capability("endpoint.device.search"),
            capability("datto.device.search", provider_neutral=False),
        ),
        reasoner=reasoner,
    )

    with pytest.raises(PermissionError, match="outside the governed candidate set"):
        planner.plan(inquiry())


def test_planner_fails_closed_when_no_registered_resource_capability_exists():
    planner = GovernedResourceInquiryPlanner(
        registry=registry_service(capability("ticket.record.search", resource_types="ticket")),
        reasoner=Reasoner("ticket.record.search"),
    )

    with pytest.raises(LookupError, match="no governed read capabilities"):
        planner.plan(inquiry())


def test_resource_inquiry_rejects_non_read_permission_mode():
    with pytest.raises(PermissionError, match="read-only"):
        ResourceInquiry(
            resource_type="endpoint",
            resource_selector={"hostname": "AOT-50282"},
            requested_facts=("last logged in user",),
            permission_mode="execute",
        )


def test_planner_excludes_capabilities_not_declared_read_only():
    planner = GovernedResourceInquiryPlanner(
        registry=registry_service(capability("endpoint.device.change", read_only=False)),
        reasoner=Reasoner("endpoint.device.change"),
    )

    with pytest.raises(LookupError, match="no governed read capabilities"):
        planner.plan(inquiry())


def test_approved_semantic_mapping_guides_generic_capability_selection():
    from orchestrator.resource_capability_catalog import (
        endpoint_alert_search,
        endpoint_device_search,
    )
    from orchestrator.resource_reasoner import MetadataResourceCapabilityReasoner
    from orchestrator.semantic_mapping_registry import (
        ApprovedSemanticMapping,
        SemanticMappingRegistry,
    )

    mapping = ApprovedSemanticMapping(
        mapping_id="example-display-version",
        version=1,
        provider_id="example_provider",
        canonical_fact="operating system display version",
        provider_schema="Device",
        provider_field="displayVersion",
        resource_authority="managed_endpoint",
        approval_status="approved",
        approved_by="technology-steward",
        approval_basis="authoritative evidence",
        openapi_source_reference="openapi:test",
        semantic_source_reference="help:test",
        capability_names=("endpoint.device.search", "endpoint.device.read"),
        active=True,
    )

    inquiry = ResourceInquiry(
        resource_type="endpoint",
        resource_selector={"hostname": "EXAMPLE-1"},
        requested_facts=("operating system display version",),
    )

    selected = MetadataResourceCapabilityReasoner(
        semantic_mapping_registry=SemanticMappingRegistry((mapping,))
    ).select(
        inquiry=inquiry,
        candidates=(
            endpoint_alert_search(datetime.now(timezone.utc)),
            endpoint_device_search(datetime.now(timezone.utc)),
        ),
    )

    assert len(selected) == 1
    assert selected[0].capability_name == "endpoint.device.search"


def test_unrelated_approved_mapping_does_not_force_capability():
    from orchestrator.resource_capability_catalog import (
        endpoint_alert_search,
        endpoint_device_search,
    )
    from orchestrator.resource_reasoner import MetadataResourceCapabilityReasoner
    from orchestrator.semantic_mapping_registry import (
        ApprovedSemanticMapping,
        SemanticMappingRegistry,
    )

    mapping = ApprovedSemanticMapping(
        mapping_id="example-display-version",
        version=1,
        provider_id="example_provider",
        canonical_fact="operating system display version",
        provider_schema="Device",
        provider_field="displayVersion",
        resource_authority="managed_endpoint",
        approval_status="approved",
        approved_by="technology-steward",
        approval_basis="authoritative evidence",
        openapi_source_reference="openapi:test",
        semantic_source_reference="help:test",
        capability_names=("endpoint.device.search",),
        active=True,
    )

    inquiry = ResourceInquiry(
        resource_type="endpoint",
        resource_selector={"hostname": "EXAMPLE-1"},
        requested_facts=("open alerts",),
    )

    selected = MetadataResourceCapabilityReasoner(
        semantic_mapping_registry=SemanticMappingRegistry((mapping,))
    ).select(
        inquiry=inquiry,
        candidates=(
            endpoint_alert_search(datetime.now(timezone.utc)),
            endpoint_device_search(datetime.now(timezone.utc)),
        ),
    )

    assert len(selected) == 1
    assert selected[0].capability_name == "endpoint.alert.search"


def test_approved_mapping_can_recover_from_overly_narrow_resource_subtype():
    from orchestrator.resource_capability_catalog import (
        endpoint_alert_search,
        endpoint_device_search,
    )
    from orchestrator.resource_reasoner import MetadataResourceCapabilityReasoner
    from orchestrator.semantic_mapping_registry import (
        ApprovedSemanticMapping,
        SemanticMappingRegistry,
    )

    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    now = datetime.now(timezone.utc)

    for definition in (endpoint_alert_search(now), endpoint_device_search(now)):
        capabilities.register(definition)

    mapping = ApprovedSemanticMapping(
        mapping_id="example-display-version",
        version=1,
        provider_id="example_provider",
        canonical_fact="operating system display version",
        provider_schema="Device",
        provider_field="displayVersion",
        resource_authority="managed_endpoint",
        approval_status="approved",
        approved_by="technology-steward",
        approval_basis="authoritative evidence",
        openapi_source_reference="openapi:test",
        semantic_source_reference="help:test",
        capability_names=("endpoint.device.search", "endpoint.device.read"),
        active=True,
    )

    registry = SemanticMappingRegistry((mapping,))

    inquiry = ResourceInquiry(
        resource_type="endpoint_alert",
        resource_selector={"hostname": "EXAMPLE-1"},
        requested_facts=("operating system display version",),
    )

    plan = GovernedResourceInquiryPlanner(
        registry=capabilities,
        reasoner=MetadataResourceCapabilityReasoner(semantic_mapping_registry=registry),
        semantic_mapping_registry=registry,
    ).plan(inquiry)

    assert len(plan.steps) == 1
    assert plan.steps[0].capability_name == "endpoint.device.search"


def test_multi_fact_read_is_split_only_by_governed_fact_coverage():
    from orchestrator.resource_capability_catalog import (
        endpoint_alert_search,
        endpoint_device_search,
    )
    from orchestrator.resource_reasoner import MetadataResourceCapabilityReasoner

    inquiry = ResourceInquiry(
        resource_type="endpoint",
        resource_selector={"hostname": "AOT-50282"},
        requested_facts=("last logged in user", "alerts"),
    )

    selected = MetadataResourceCapabilityReasoner().select(
        inquiry=inquiry,
        candidates=(
            endpoint_alert_search(NOW),
            endpoint_device_search(NOW),
        ),
    )

    assert [step.capability_name for step in selected] == [
        "endpoint.device.search",
        "endpoint.alert.search",
    ]
    assert selected[0].arguments["requested_facts"] == ("last logged in user",)
    assert selected[1].arguments["requested_facts"] == ("alerts",)


def test_multi_fact_read_prefers_one_capability_when_it_covers_all_facts():
    from orchestrator.resource_capability_catalog import endpoint_device_search
    from orchestrator.resource_reasoner import MetadataResourceCapabilityReasoner

    inquiry = ResourceInquiry(
        resource_type="endpoint",
        resource_selector={"hostname": "AOT-50282"},
        requested_facts=("last logged in user", "operating system"),
    )

    selected = MetadataResourceCapabilityReasoner().select(
        inquiry=inquiry,
        candidates=(endpoint_device_search(NOW),),
    )

    assert len(selected) == 1
    assert selected[0].capability_name == "endpoint.device.search"
    assert selected[0].arguments["requested_facts"] == (
        "last logged in user",
        "operating system",
    )


def test_multi_fact_split_preserves_only_relevant_evidence_contexts_per_step():
    from orchestrator.resource_capability_catalog import (
        endpoint_alert_search,
        endpoint_device_search,
    )
    from orchestrator.resource_reasoner import MetadataResourceCapabilityReasoner

    inquiry = ResourceInquiry(
        resource_type="endpoint",
        resource_selector={"hostname": "AOT-50282"},
        requested_facts=("last logged in user", "alerts"),
        evidence_contexts={
            "last logged in user": ("current endpoint record",),
            "alerts": ("open endpoint alerts",),
        },
    )

    selected = MetadataResourceCapabilityReasoner().select(
        inquiry=inquiry,
        candidates=(endpoint_alert_search(NOW), endpoint_device_search(NOW)),
    )

    assert selected[0].arguments["evidence_contexts"] == {
        "last logged in user": ("current endpoint record",),
    }
    assert selected[1].arguments["evidence_contexts"] == {
        "alerts": ("open endpoint alerts",),
    }
