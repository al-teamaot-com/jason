from __future__ import annotations

import json

import pytest

from orchestrator.conversation_kernel import (
    ConversationKernel,
    ConversationKernelError,
    ReasoningBackend,
    ValidatedReasoningPool,
)
from orchestrator.dynamic_conversation_kernel import (
    ConversationEntity,
    DynamicConversationContext,
)


class FakeClient:
    def __init__(self, *responses):
        self.responses = list(responses)
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
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def empty_context():
    return DynamicConversationContext(
        conversation_id="conv-1",
        principal_id="person-al",
        organization_id="aot",
    )


def information_proposal(reference="NODE-77"):
    return {
        "outcome": "information",
        "information_needs": [
            {
                "target_kind": "endpoint",
                "target_source": "literal",
                "target_reference": reference,
                "target_entity_ref": None,
                "need": "current cooling mode",
                "authority": "observe",
                "temporal_scope": "current",
                "completeness": "sufficient",
                "relationship": None,
            }
        ],
        "clarification_question": None,
        "conversational_response": None,
        "topic": "endpoint state",
    }


def test_kernel_never_receives_capability_catalog_and_falls_back_after_invalid_backend():
    cheap = FakeClient(
        {
            **information_proposal(),
            "capability_name": "endpoint.device.search",
        }
    )
    stronger = FakeClient(information_proposal())

    kernel = ConversationKernel(
        reasoning=ValidatedReasoningPool(
            backends=(
                ReasoningBackend(name="cheap", client=cheap),
                ReasoningBackend(name="stronger", client=stronger),
            )
        )
    )

    decision, attempts = kernel.interpret(
        text="What is the current cooling mode for NODE-77?",
        context=empty_context(),
    )

    assert decision.outcome == "information"
    assert decision.information_needs[0].target.reference == "NODE-77"
    assert [item.outcome for item in attempts] == ["rejected", "accepted"]
    assert [item.backend for item in attempts] == ["cheap", "stronger"]

    call = stronger.calls[0]
    payload = json.loads(call["user"])
    assert set(payload) == {"message", "context"}
    serialized_schema = json.dumps(call["schema"]).casefold()
    assert "capability_name" not in serialized_schema
    assert "provider_id" not in serialized_schema
    assert "connector_id" not in serialized_schema
    assert "do not select or name providers" in call["system"].casefold()


def test_literal_target_must_be_copied_exactly_from_human_message():
    invalid = FakeClient(information_proposal(reference="NODE77"))
    valid = FakeClient(information_proposal(reference="NODE-77"))
    kernel = ConversationKernel(
        reasoning=ValidatedReasoningPool(
            backends=(
                ReasoningBackend(name="first", client=invalid),
                ReasoningBackend(name="second", client=valid),
            )
        )
    )

    decision, attempts = kernel.interpret(
        text="Inspect NODE-77.",
        context=empty_context(),
    )

    assert decision.information_needs[0].target.reference == "NODE-77"
    assert attempts[0].error_type == "ConversationKernelError"


def test_verified_context_entity_can_be_targeted_without_repeating_literal():
    context = DynamicConversationContext(
        conversation_id="conv-2",
        principal_id="person-al",
        organization_id="aot",
        entities=(
            ConversationEntity(
                ref="entity-1",
                kind="endpoint",
                canonical_id="resource-123",
                display_name="NODE-77",
                provenance="verified provider evidence",
            ),
        ),
        active_entity_refs={"endpoint": "entity-1"},
    )
    client = FakeClient(
        {
            "outcome": "information",
            "information_needs": [
                {
                    "target_kind": "endpoint",
                    "target_source": "verified_entity",
                    "target_reference": "resource-123",
                    "target_entity_ref": "entity-1",
                    "need": "open problems affecting this resource",
                    "authority": "observe",
                    "temporal_scope": "current",
                    "completeness": "sufficient",
                    "relationship": None,
                }
            ],
            "clarification_question": None,
            "conversational_response": None,
            "topic": "endpoint health",
        }
    )
    kernel = ConversationKernel(
        reasoning=ValidatedReasoningPool(
            backends=(ReasoningBackend(name="local", client=client),)
        )
    )

    decision, _ = kernel.interpret(text="Anything wrong with it?", context=context)

    target = decision.information_needs[0].target
    assert target.source == "verified_entity"
    assert target.entity_ref == "entity-1"
    assert target.reference == "resource-123"


def test_multi_need_turn_preserves_complete_bounded_request_without_capability_selection():
    client = FakeClient(
        {
            "outcome": "information",
            "information_needs": [
                {
                    "target_kind": "endpoint",
                    "target_source": "literal",
                    "target_reference": "NODE-77",
                    "target_entity_ref": None,
                    "need": "identity associated with the most recent interactive session",
                    "authority": "observe",
                    "temporal_scope": "most_recent",
                    "completeness": "sufficient",
                    "relationship": None,
                },
                {
                    "target_kind": "endpoint",
                    "target_source": "literal",
                    "target_reference": "NODE-77",
                    "target_entity_ref": None,
                    "need": "current open monitoring problems",
                    "authority": "observe",
                    "temporal_scope": "current",
                    "completeness": "complete",
                    "relationship": None,
                },
            ],
            "clarification_question": None,
            "conversational_response": None,
            "topic": "endpoint state",
        }
    )
    kernel = ConversationKernel(
        reasoning=ValidatedReasoningPool(
            backends=(ReasoningBackend(name="any-model", client=client),)
        )
    )

    decision, _ = kernel.interpret(
        text="Who was most recently logged into NODE-77, and what open problems does it have?",
        context=empty_context(),
    )

    assert len(decision.information_needs) == 2
    assert {item.need for item in decision.information_needs} == {
        "identity associated with the most recent interactive session",
        "current open monitoring problems",
    }


def test_clarification_remains_a_conversation_decision_not_an_execution_choice():
    client = FakeClient(
        {
            "outcome": "clarify",
            "information_needs": [],
            "clarification_question": "Which of the two customer environments do you mean?",
            "conversational_response": None,
            "topic": "customer environment",
        }
    )
    kernel = ConversationKernel(
        reasoning=ValidatedReasoningPool(
            backends=(ReasoningBackend(name="model", client=client),)
        )
    )

    decision, _ = kernel.interpret(text="Check that customer.", context=empty_context())

    assert decision.outcome == "clarify"
    assert not decision.information_needs
    assert "which" in decision.clarification_question.casefold()


def test_information_outcome_rejects_model_generated_human_facing_answer():
    bad = information_proposal()
    bad["conversational_response"] = "NODE-77 is fine."
    client = FakeClient(bad)
    kernel = ConversationKernel(
        reasoning=ValidatedReasoningPool(
            backends=(ReasoningBackend(name="only", client=client),)
        )
    )

    with pytest.raises(
        ConversationKernelError,
        match="all configured reasoning backends failed",
    ):
        kernel.interpret(
            text="What is the current cooling mode for NODE-77?",
            context=empty_context(),
        )
