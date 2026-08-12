from orchestrator.canonical_fact_vocabulary import DEFAULT_CANONICAL_FACT_VOCABULARY
from orchestrator.semantic_request_bridge import SemanticRequestBridge


def bridge():
    return SemanticRequestBridge(DEFAULT_CANONICAL_FACT_VOCABULARY)


def test_windows_display_version_gets_semantic_evidence_context():
    semantic = bridge().build(
        human_text="What is the Windows Display Version for AOT-50282?",
        resource_type="endpoint",
        resource_selector={"hostname": "AOT-50282"},
        requested_facts=("display", "version"),
        result_intent="summary",
        completeness_requirement="sufficient",
    )
    assert semantic.requested_facts == ("operating system display version",)
    constraint = semantic.evidence_constraints["operating system display version"]
    assert constraint.contexts == ("operating_system", "windows_release")
    assert constraint.expected_shape == "descriptive_string"


def test_person_device_question_becomes_relationship_semantics():
    semantic = bridge().build(
        human_text="What device is Lindsey Collins on?",
        resource_type="endpoint",
        resource_selector={"user_identity": "Lindsey Collins"},
        requested_facts=("hostname",),
        result_intent="summary",
        completeness_requirement="sufficient",
    )
    assert semantic.subject.entity_type == "person"
    assert semantic.subject.reference == "Lindsey Collins"
    assert semantic.relationship.relationship_type == "logged_in_to"
    assert semantic.relationship.target_resource_type == "endpoint"
    assert semantic.relationship.temporal_semantics == "current"


def test_last_logged_into_becomes_most_recent_semantics():
    semantic = bridge().build(
        human_text="Which endpoint was AzureAD\\LindseyCollins last logged into?",
        resource_type="endpoint",
        resource_selector={"user_identity": "AzureAD\\LindseyCollins"},
        requested_facts=("hostname",),
        result_intent="summary",
        completeness_requirement="sufficient",
    )
    assert semantic.relationship.temporal_semantics == "most_recent"


def test_lowering_preserves_existing_governed_planner_contract():
    b = bridge()
    semantic = b.build(
        human_text="How much RAM is in AOT-50282?",
        resource_type="endpoint",
        resource_selector={"hostname": "AOT-50282"},
        requested_facts=("ram",),
        result_intent="summary",
        completeness_requirement="sufficient",
    )
    inquiry = b.lower(semantic, selector={"hostname": "AOT-50282"})
    assert inquiry.resource_type == "endpoint"
    assert inquiry.resource_selector == {"hostname": "AOT-50282"}
    assert inquiry.requested_facts == ("total memory",)


def test_semantic_bridge_rejects_execute_permission_mode():
    import pytest

    with pytest.raises(PermissionError, match="read-only"):
        bridge().build(
            human_text="What processor is on AOT-50282?",
            resource_type="endpoint",
            resource_selector={"hostname": "AOT-50282"},
            requested_facts=("processor",),
            result_intent="summary",
            completeness_requirement="sufficient",
            permission_mode="execute",
        )


def test_lowering_preserves_evidence_and_relationship_semantics():
    b = bridge()
    semantic = b.build(
        human_text="Which endpoint was Lindsey Collins last logged into?",
        resource_type="endpoint",
        resource_selector={"user_identity": "Lindsey Collins"},
        requested_facts=("hostname",),
        result_intent="summary",
        completeness_requirement="sufficient",
        permission_mode="observe",
    )
    inquiry = b.lower(semantic, selector={"user_identity": "Lindsey Collins"})
    assert inquiry.relationship_type == "logged_in_to"
    assert inquiry.temporal_semantics == "most_recent"


def test_windows_display_version_lowering_preserves_evidence_contexts():
    b = bridge()
    semantic = b.build(
        human_text="What is the Windows Display Version for AOT-50282?",
        resource_type="endpoint",
        resource_selector={"hostname": "AOT-50282"},
        requested_facts=("display", "version"),
        result_intent="summary",
        completeness_requirement="sufficient",
        permission_mode="observe",
    )
    inquiry = b.lower(semantic, selector={"hostname": "AOT-50282"})
    assert inquiry.evidence_contexts == {
        "operating system display version": ("operating_system", "windows_release")
    }


def test_registry_first_fact_resolver_drives_bridge_fact_and_evidence_contexts():
    from orchestrator.semantic_fact_resolver import SemanticFactResolver
    from orchestrator.semantic_knowledge_seed import build_trusted_semantic_registry

    semantic_bridge = SemanticRequestBridge(
        fact_resolver=SemanticFactResolver(
            registry=build_trusted_semantic_registry(),
            legacy_vocabulary=None,
        )
    )

    request = semantic_bridge.build(
        human_text="What CPU does AOT-50282 have?",
        resource_type="endpoint",
        resource_selector={"hostname": "AOT-50282"},
        requested_facts=("CPU",),
        result_intent="summary",
        completeness_requirement="sufficient",
    )

    assert request.requested_facts == ("processor model",)
    assert request.evidence_constraints is not None
    constraint = request.evidence_constraints["processor model"]
    assert constraint.contexts == ("processor", "hardware_inventory")
    assert constraint.expected_shape == "descriptive_string"
