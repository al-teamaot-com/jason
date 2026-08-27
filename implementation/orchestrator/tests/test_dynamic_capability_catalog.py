from __future__ import annotations

from datetime import datetime, timezone

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

from orchestrator.dynamic_capability_catalog import (
    RegistryBackedDynamicCapabilityCatalog,
)


NOW = datetime(2026, 8, 16, 14, 0, tzinfo=timezone.utc)


def capability(
    name: str,
    *,
    lifecycle: CapabilityLifecycle = CapabilityLifecycle.ACTIVE,
    metadata: dict[str, str] | None = None,
    risk: CapabilityRisk = CapabilityRisk.LOW,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=name,
        version="1.0",
        display_name=f"Capability {name}",
        lifecycle_status=lifecycle,
        business_purpose=f"Perform the governed business purpose for {name}.",
        owner_service="test",
        architectural_capability_ids=frozenset({"JAC-005"}),
        risk_level=risk,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference=f"schema://test/{name}/input",
        output_schema_reference=f"schema://test/{name}/output",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(required=False),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=30,
        maximum_attempts=1,
        failure_behavior="fail closed",
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification="test dynamic discovery",
            review_interval_days=90,
            retirement_criteria=("replaced",),
        ),
        created_at=NOW,
        metadata=metadata or {},
    )


def catalog_for(*items: CapabilityDefinition) -> RegistryBackedDynamicCapabilityCatalog:
    registry = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    for item in items:
        registry.register(item)
    return RegistryBackedDynamicCapabilityCatalog(registry=registry)


def test_catalog_exposes_active_capability_without_semantic_hint_metadata():
    catalog = catalog_for(
        capability(
            "future.quantum.asset.inspect",
            metadata={
                "resource_types": "quantum_asset",
                "operation": "inspect",
                "selector_keys": "asset_reference",
            },
        )
    )

    offered = catalog.list_offered()

    assert [item.capability_id for item in offered] == ["future.quantum.asset.inspect"]
    assert offered[0].provider is None
    assert offered[0].input_schema["selector_keys"] == ["asset_reference"]
    assert "quantum_asset" in offered[0].description


def test_catalog_does_not_expose_legacy_semantic_hint_lists_to_model():
    catalog = catalog_for(
        capability(
            "endpoint.device.search",
            metadata={
                "read_only": "true",
                "resource_types": "endpoint",
                "operation": "search",
                "selector_keys": "hostname,resource_id",
                "fact_hints": "legacy phrase hint",
                "canonical_facts": "legacy canonical fact",
                "inquiry_hints": "legacy inquiry hint",
                "planning_guidance": "legacy planning guidance",
            },
        )
    )

    item = catalog.list_offered()[0]
    serialized = repr(item.model_view())

    assert item.permission_mode == "observe"
    assert "legacy phrase hint" not in serialized
    assert "legacy canonical fact" not in serialized
    assert "legacy inquiry hint" not in serialized
    assert "legacy planning guidance" not in serialized


def test_catalog_filters_non_operational_lifecycle_states_and_can_include_pilot():
    catalog = catalog_for(
        capability("alpha.read.one", lifecycle=CapabilityLifecycle.ACTIVE),
        capability("alpha.read.two", lifecycle=CapabilityLifecycle.PILOT),
        capability("alpha.read.three", lifecycle=CapabilityLifecycle.PROPOSED),
        capability("alpha.read.four", lifecycle=CapabilityLifecycle.SUSPENDED),
    )

    assert [item.capability_id for item in catalog.list_offered()] == [
        "alpha.read.one",
        "alpha.read.two",
    ]


def test_non_read_capability_defaults_to_execute_authority_intent_without_provider_binding():
    item = catalog_for(
        capability(
            "communication.message.send",
            metadata={},
            risk=CapabilityRisk.MEDIUM,
        )
    ).list_offered()[0]

    assert item.permission_mode == "execute"
    assert item.risk == "medium"
    assert item.provider is None


def test_invalid_declared_conversation_permission_mode_fails_closed():
    catalog = catalog_for(
        capability(
            "future.action.perform",
            metadata={"conversation_permission_mode": "superuser"},
        )
    )

    try:
        catalog.list_offered()
    except ValueError as error:
        assert "invalid conversation permission mode" in str(error)
    else:
        raise AssertionError("invalid permission mode must fail closed")



def test_discovery_description_does_not_expose_internal_selector_choices():
    offered = catalog_for(
        capability(
            "synthetic.resource.search",
            metadata={
                "read_only": "true",
                "resource_types": "synthetic_resource",
                "operation": "search",
                "selector_keys": "hostname,resource_id,name",
            },
        )
    ).list_offered()[0]

    # Discovery explains what the capability does, not how its internal
    # argument contract happens to represent the human-supplied target.
    assert "Accepted selector keys:" not in offered.description
    assert "hostname" not in offered.description
    assert "resource_id" not in offered.description

    discovery = offered.discovery_view()

    assert "selector_keys" not in discovery
    assert "provider" not in discovery
    assert "input_schema" not in discovery
    assert "output_schema" not in discovery

    # The complete selected capability retains the structural binding contract.
    assert offered.input_schema["selector_keys"] == [
        "hostname",
        "resource_id",
        "name",
    ]
