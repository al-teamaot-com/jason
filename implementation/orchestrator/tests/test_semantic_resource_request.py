from __future__ import annotations

import pytest

from orchestrator.semantic_resource_request import (
    SemanticEntityReference,
    SemanticEvidenceConstraint,
    SemanticRelationship,
    SemanticResourceRequest,
)


def test_person_to_endpoint_relationship_is_provider_neutral():
    request = SemanticResourceRequest(
        subject=SemanticEntityReference(
            entity_type="person",
            reference="Lindsey Collins",
        ),
        target_resource_type="endpoint",
        relationship=SemanticRelationship(
            relationship_type="logged_in_to",
            target_resource_type="endpoint",
            temporal_semantics="most_recent",
        ),
        requested_facts=("hostname",),
    )

    assert request.subject.reference == "Lindsey Collins"
    assert request.relationship.relationship_type == "logged_in_to"
    assert request.relationship.temporal_semantics == "most_recent"
    assert not hasattr(request, "provider")
    assert not hasattr(request, "connector")


def test_fact_evidence_context_is_semantic_not_provider_path():
    request = SemanticResourceRequest(
        subject=SemanticEntityReference(
            entity_type="endpoint",
            reference="AOT-50282",
            selector_kind="hostname",
        ),
        target_resource_type="endpoint",
        requested_facts=("operating system display version",),
        evidence_constraints={
            "operating system display version": SemanticEvidenceConstraint(
                contexts=("operating_system", "windows_release"),
                expected_shape="descriptive_string",
            )
        },
    )

    constraint = request.evidence_constraints["operating system display version"]
    assert "operating_system" in constraint.contexts
    assert all(not context.startswith("/") for context in constraint.contexts)


def test_relationship_target_must_match_requested_resource():
    with pytest.raises(ValueError, match="relationship target"):
        SemanticResourceRequest(
            subject=SemanticEntityReference(entity_type="person", reference="Al Davis"),
            target_resource_type="ticket",
            relationship=SemanticRelationship(
                relationship_type="uses",
                target_resource_type="endpoint",
            ),
            requested_facts=("ticket number",),
        )


def test_evidence_constraints_cannot_expand_requested_facts():
    with pytest.raises(ValueError, match="unrequested facts"):
        SemanticResourceRequest(
            subject=None,
            target_resource_type="organization",
            requested_facts=("name",),
            evidence_constraints={
                "secret field": SemanticEvidenceConstraint(contexts=("organization",))
            },
        )
