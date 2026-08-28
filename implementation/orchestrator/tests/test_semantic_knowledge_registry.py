import pytest

from orchestrator.semantic_knowledge_registry import (
    SemanticConcept,
    SemanticKnowledgeRegistry,
    SemanticLifecycleState,
    SemanticProviderFieldBinding,
    SemanticProvenance,
    SemanticRelationshipDefinition,
    SemanticTermBinding,
    promote_concept_to_active,
    promote_term_to_active,
)


def provenance() -> SemanticProvenance:
    return SemanticProvenance(
        source="engineering-test",
        evidence="explicit test fixture",
    )


def processor_registry() -> SemanticKnowledgeRegistry:
    registry = SemanticKnowledgeRegistry()
    registry.add_concept(
        SemanticConcept(
            concept_id="processor.model",
            canonical_label="processor model",
            kind="fact",
            expected_shape="descriptive_string",
            evidence_contexts=("processor", "hardware_inventory"),
            provenance=provenance(),
            review_interval_days=180,
            retirement_criteria="retire only when replaced by a governed canonical concept",
        )
    )
    registry.add_term(
        SemanticTermBinding(
            term="CPU",
            concept_id="processor.model",
            provenance=provenance(),
        )
    )
    return registry


def test_candidate_knowledge_does_not_resolve_as_operational_truth():
    registry = processor_registry()
    assert registry.resolve_term("CPU") is None


def test_approved_active_term_resolves_deterministically():
    registry = processor_registry()
    promote_concept_to_active(registry, "processor.model")
    promote_term_to_active(registry, term="CPU")

    concept = registry.resolve_term("cpu")

    assert concept is not None
    assert concept.concept_id == "processor.model"
    assert concept.evidence_contexts == ("processor", "hardware_inventory")


def test_invalid_lifecycle_jump_fails_closed():
    registry = processor_registry()
    with pytest.raises(ValueError, match="invalid semantic lifecycle transition"):
        registry.transition_concept("processor.model", SemanticLifecycleState.ACTIVE)


def test_conflicting_term_in_same_scope_is_rejected():
    registry = processor_registry()
    registry.add_concept(
        SemanticConcept(
            concept_id="processor.count",
            canonical_label="logical processor count",
            kind="fact",
            provenance=provenance(),
        )
    )
    with pytest.raises(ValueError, match="ambiguous"):
        registry.add_term(
            SemanticTermBinding(
                term="CPU",
                concept_id="processor.count",
                provenance=provenance(),
            )
        )


def test_provider_field_mapping_is_provider_and_resource_scoped():
    registry = processor_registry()
    promote_concept_to_active(registry, "processor.model")
    registry.add_provider_field(
        SemanticProviderFieldBinding(
            provider="datto_rmm",
            resource_type="endpoint",
            provider_field="cpuModel",
            concept_id="processor.model",
            provenance=provenance(),
        )
    )
    for state in (
        SemanticLifecycleState.REVIEWED,
        SemanticLifecycleState.APPROVED,
        SemanticLifecycleState.ACTIVE,
    ):
        registry.transition_provider_field(
            provider="datto_rmm",
            resource_type="endpoint",
            provider_field="cpuModel",
            target=state,
        )

    assert registry.resolve_provider_field(
        provider="datto_rmm",
        resource_type="endpoint",
        provider_field="cpuModel",
    ).concept_id == "processor.model"
    assert registry.resolve_provider_field(
        provider="autotask",
        resource_type="endpoint",
        provider_field="cpuModel",
    ) is None


def test_relationship_definition_carries_temporal_contract():
    registry = SemanticKnowledgeRegistry()
    registry.add_relationship(
        SemanticRelationshipDefinition(
            relationship_id="person.logged_in_to.endpoint",
            subject_type="person",
            target_type="endpoint",
            temporal_semantics=("current", "most_recent", "historical"),
            provenance=provenance(),
        )
    )
    for state in (
        SemanticLifecycleState.REVIEWED,
        SemanticLifecycleState.APPROVED,
        SemanticLifecycleState.ACTIVE,
    ):
        registry.transition_relationship("person.logged_in_to.endpoint", state)

    relationship = registry.active_relationship("person.logged_in_to.endpoint")
    assert relationship is not None
    assert relationship.subject_type == "person"
    assert relationship.target_type == "endpoint"
    assert "most_recent" in relationship.temporal_semantics


def test_registry_version_changes_on_governed_mutation():
    registry = SemanticKnowledgeRegistry()
    assert registry.version == 0
    registry.add_concept(
        SemanticConcept(
            concept_id="memory.total",
            canonical_label="total memory",
            kind="fact",
            canonical_unit="byte",
            provenance=provenance(),
        )
    )
    first = registry.version
    registry.transition_concept("memory.total", SemanticLifecycleState.REVIEWED)
    assert registry.version > first


def test_equivalent_provider_field_registration_is_idempotent():
    registry = processor_registry()
    promote_concept_to_active(registry, "processor.model")
    first = SemanticProviderFieldBinding(
        provider="datto_rmm",
        resource_type="endpoint",
        provider_field="cpuModel",
        concept_id="processor.model",
        provenance=provenance(),
    )
    equivalent = SemanticProviderFieldBinding(
        provider="datto_rmm",
        resource_type="endpoint",
        provider_field="CPUModel",
        concept_id="processor.model",
        provenance=provenance(),
    )
    registry.add_provider_field(first)
    version_after_first = registry.version
    registry.add_provider_field(equivalent)

    assert registry.version == version_after_first


def test_equivalent_provider_field_cannot_map_to_different_concept():
    registry = processor_registry()
    registry.add_concept(
        SemanticConcept(
            concept_id="processor.count",
            canonical_label="logical processor count",
            kind="fact",
            provenance=provenance(),
        )
    )
    registry.add_provider_field(
        SemanticProviderFieldBinding(
            provider="datto_rmm",
            resource_type="endpoint",
            provider_field="cpuModel",
            concept_id="processor.model",
            provenance=provenance(),
        )
    )
    with pytest.raises(ValueError, match="ambiguous"):
        registry.add_provider_field(
            SemanticProviderFieldBinding(
                provider="datto_rmm",
                resource_type="endpoint",
                provider_field="CPUModel",
                concept_id="processor.count",
                provenance=provenance(),
            )
        )


def test_active_relationships_returns_only_authoritative_relationships():
    registry = SemanticKnowledgeRegistry()
    relationship = SemanticRelationshipDefinition(
        relationship_id="person.assigned_to.ticket",
        subject_type="person",
        target_type="ticket",
    )
    registry.add_relationship(relationship)
    assert registry.active_relationships() == ()
    for state in (
        SemanticLifecycleState.REVIEWED,
        SemanticLifecycleState.APPROVED,
        SemanticLifecycleState.ACTIVE,
    ):
        registry.transition_relationship(relationship.relationship_id, state)
    assert tuple(item.relationship_id for item in registry.active_relationships()) == (
        "person.assigned_to.ticket",
    )
