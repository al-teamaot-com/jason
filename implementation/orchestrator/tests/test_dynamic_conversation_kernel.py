from __future__ import annotations

import json

import pytest

from orchestrator.dynamic_conversation_kernel import (
    ConversationEntity,
    ConversationReferenceResolution,
    DynamicConversationContext,
    DynamicConversationPlanError,
    DynamicConversationResolver,
    OfferedConversationCapability,
)


class FakeStructuredClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def complete(self, *, system, user, schema, max_output_tokens=160):
        self.calls.append(
            {
                "system": system,
                "user": user,
                "schema": schema,
                "max_output_tokens": max_output_tokens,
            }
        )
        return dict(self.response)


def context() -> DynamicConversationContext:
    return DynamicConversationContext(
        conversation_id="conv-1",
        principal_id="person-al",
        organization_id="aot",
        entities=(
            ConversationEntity(
                ref="entity-device-1",
                kind="device",
                canonical_id="AOT-50107",
                display_name="AOT-50107",
                provenance="verified provider evidence",
            ),
            ConversationEntity(
                ref="entity-person-1",
                kind="person",
                canonical_id="person-arnold",
                display_name="Arnold Heath",
                provenance="verified identity correlation",
            ),
        ),
        active_entity_refs={
            "device": "entity-device-1",
            "person": "entity-person-1",
        },
        active_topic="endpoint investigation",
    )


def capabilities():
    return (
        OfferedConversationCapability(
            capability_id="endpoint.read.runtime-generated-id",
            provider="datto_rmm",
            description="Read authorized endpoint inventory and operating observations for a device.",
            input_schema={"type": "object"},
        ),
        OfferedConversationCapability(
            capability_id="identity.signin.investigate.runtime-generated-id",
            provider="microsoft_graph",
            description="Inspect authorized cloud identity sign-in and risk observations for an identity.",
            input_schema={"type": "object"},
        ),
    )


def test_contextual_reference_can_pivot_to_different_provider_without_static_mapping():
    client = FakeStructuredClient(
        {
            "outcome": "plan",
            "requirements": [
                {
                    "capability_id": "identity.signin.investigate.runtime-generated-id",
                    "purpose": "Investigate the cloud sign-in concern in the human request.",
                    "entity_refs": ["entity-person-1"],
                }
            ],
            "resolved_references": [
                {
                    "mention": "it",
                    "entity_ref": "entity-device-1",
                    "basis": "the active device in this conversation",
                }
            ],
            "topic": "identity security investigation",
            "clarification_question": None,
        }
    )
    resolver = DynamicConversationResolver(client=client)

    plan = resolver.resolve(
        text="Does it have any suspicious Office 365 logins?",
        context=context(),
        capabilities=capabilities(),
    )

    assert plan.outcome == "plan"
    assert plan.requirements[0].capability_id == "identity.signin.investigate.runtime-generated-id"
    assert plan.requirements[0].entity_refs == ("entity-person-1",)
    assert plan.resolved_references[0].entity_ref == "entity-device-1"

    model_input = json.loads(client.calls[0]["user"])
    assert model_input["context"]["active_entity_refs"]["device"] == "entity-device-1"
    assert {item["provider"] for item in model_input["capabilities"]} == {
        "datto_rmm",
        "microsoft_graph",
    }
    # Production logic receives descriptions/schemas dynamically; this test phrase
    # appears only in test input and is not encoded in the resolver implementation.
    assert "Office 365" not in client.calls[0]["system"]


def test_previously_unseen_future_capability_can_be_selected_without_code_change():
    future = OfferedConversationCapability(
        capability_id="future.vendor.quantum.telemetry.read.v9",
        provider="future_vendor",
        description="Read the future platform's authorized quantum telemetry for a governed entity.",
        input_schema={"required": ["entity"]},
        output_schema={"properties": {"telemetry": {"type": "array"}}},
    )
    client = FakeStructuredClient(
        {
            "outcome": "plan",
            "requirements": [
                {
                    "capability_id": future.capability_id,
                    "purpose": "Read the requested future telemetry.",
                    "entity_refs": ["entity-device-1"],
                }
            ],
            "resolved_references": [],
            "topic": "future telemetry",
            "clarification_question": None,
        }
    )

    plan = DynamicConversationResolver(client=client).resolve(
        text="Check the new telemetry for this workstation.",
        context=context(),
        capabilities=(future,),
    )

    assert plan.requirements[0].capability_id == future.capability_id
    assert future.capability_id in client.calls[0]["schema"]["properties"]["requirements"]["items"]["properties"]["capability_id"]["enum"]


def test_material_ambiguity_returns_natural_clarification_without_execution():
    client = FakeStructuredClient(
        {
            "outcome": "clarify",
            "requirements": [],
            "resolved_references": [],
            "topic": "ambiguous target",
            "clarification_question": "Which user or workstation do you mean?",
        }
    )

    plan = DynamicConversationResolver(client=client).resolve(
        text="Check their account.",
        context=context(),
        capabilities=capabilities(),
    )

    assert plan.outcome == "clarify"
    assert plan.requirements == ()
    assert plan.clarification_question == "Which user or workstation do you mean?"


def test_model_cannot_select_capability_not_offered_by_governed_runtime():
    client = FakeStructuredClient(
        {
            "outcome": "plan",
            "requirements": [
                {
                    "capability_id": "unregistered.provider.escape",
                    "purpose": "bypass",
                    "entity_refs": [],
                }
            ],
            "resolved_references": [],
            "topic": None,
            "clarification_question": None,
        }
    )

    with pytest.raises(DynamicConversationPlanError, match="not offered"):
        DynamicConversationResolver(client=client).resolve(
            text="Do something.",
            context=context(),
            capabilities=capabilities(),
        )


def test_model_cannot_resolve_reference_to_unknown_entity():
    client = FakeStructuredClient(
        {
            "outcome": "conversation",
            "requirements": [],
            "resolved_references": [
                {
                    "mention": "they",
                    "entity_ref": "invented-person",
                    "basis": "guess",
                }
            ],
            "topic": None,
            "clarification_question": None,
        }
    )

    with pytest.raises(DynamicConversationPlanError, match="unknown entity"):
        DynamicConversationResolver(client=client).resolve(
            text="What did they say?",
            context=context(),
            capabilities=capabilities(),
        )


def test_context_accepts_only_verified_entity_records_and_preserves_provider_independence():
    original = context()
    ticket = ConversationEntity(
        ref="entity-ticket-1",
        kind="ticket",
        canonical_id="T20260816.0042",
        display_name="Ticket T20260816.0042",
        provenance="verified autotask evidence",
    )
    resolution = ConversationReferenceResolution(
        mention="that ticket",
        entity_ref=ticket.ref,
        basis="ticket returned by governed ticket search",
    )

    updated = original.with_verified_entities(
        (ticket,),
        active_kinds={"ticket": ticket.ref},
        topic="cross-platform incident investigation",
        resolutions=(resolution,),
    )

    assert updated.active_entity_refs["device"] == "entity-device-1"
    assert updated.active_entity_refs["person"] == "entity-person-1"
    assert updated.active_entity_refs["ticket"] == "entity-ticket-1"
    assert updated.entity("entity-ticket-1").provenance == "verified autotask evidence"
    assert updated.active_topic == "cross-platform incident investigation"


def test_unverified_active_entity_reference_is_rejected():
    with pytest.raises(ValueError, match="must be verified"):
        context().with_verified_entities(
            (),
            active_kinds={"mailbox": "model-invented-mailbox"},
        )


def test_conversation_label_with_governed_requirements_normalizes_to_plan():
    """Repair structural model contradiction without introducing semantic mapping."""

    client = FakeStructuredClient(
        {
            "outcome": "conversation",
            "requirements": [
                {
                    "capability_id": "endpoint.read.runtime-generated-id",
                    "purpose": "Read the endpoint observations requested by the human.",
                    "entity_refs": ["entity-device-1"],
                }
            ],
            "resolved_references": [],
            "topic": "endpoint investigation",
            "clarification_question": None,
        }
    )

    plan = DynamicConversationResolver(client=client).resolve(
        text="Read the requested endpoint information.",
        context=context(),
        capabilities=capabilities(),
    )

    assert plan.outcome == "plan"
    assert len(plan.requirements) == 1
    assert plan.requirements[0].capability_id == "endpoint.read.runtime-generated-id"


def test_clarify_outcome_discards_model_requirements_and_remains_non_executable():
    """Clarification dominates contradictory model capability requirements."""

    client = FakeStructuredClient(
        {
            "outcome": "clarify",
            "requirements": [
                {
                    "capability_id": "endpoint.read.runtime-generated-id",
                    "purpose": "Read endpoint observations if clarification permits.",
                    "entity_refs": ["entity-device-1"],
                }
            ],
            "resolved_references": [],
            "topic": "ambiguous endpoint investigation",
            "clarification_question": "Which workstation do you mean?",
        }
    )

    plan = DynamicConversationResolver(client=client).resolve(
        text="Check that workstation.",
        context=context(),
        capabilities=capabilities(),
    )

    assert plan.outcome == "clarify"
    assert plan.requirements == ()
    assert plan.clarification_question == "Which workstation do you mean?"


def test_planner_contract_prefers_governed_read_over_evidence_source_clarification():
    """Evidence-location uncertainty is not material human ambiguity."""

    client = FakeStructuredClient(
        {
            "outcome": "plan",
            "requirements": [
                {
                    "capability_id": "endpoint.read.runtime-generated-id",
                    "purpose": "Read the clearly targeted resource for the requested observation.",
                    "entity_refs": [],
                }
            ],
            "resolved_references": [],
            "topic": "resource observation",
            "clarification_question": None,
        }
    )

    DynamicConversationResolver(client=client).resolve(
        text="What is the current cooling mode for NODE-77?",
        context=context(),
        capabilities=capabilities(),
    )

    system = client.calls[0]["system"]

    assert (
        "Uncertainty about whether a requested fact exists in returned evidence "
        "is not material ambiguity."
    ) in system

    assert (
        "Do not ask the human to choose or provide an internal provider, registry, "
        "log, evidence source, or evidence location"
    ) in system

    # The production rule remains provider/fact independent.
    assert "Datto" not in system
    assert "lastLoggedInUser" not in system
    assert "last logged in" not in system.lower()
