from __future__ import annotations

import pytest

from orchestrator.conversation_interpretation_quality import ReviewedConversationKernel
from orchestrator.conversation_kernel import (
    ConversationKernelError,
    DynamicConversationContext,
    ReasoningBackend,
    ValidatedReasoningPool,
    _validate_decision,
)
from orchestrator.dynamic_conversation_kernel import ConversationEntity


class FakeClient:
    def __init__(self, *responses):
        self.responses = list(responses)

    def complete(self, *, system, user, schema, max_output_tokens=160):
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def pool(*clients):
    return ValidatedReasoningPool(
        backends=tuple(
            ReasoningBackend(name=f"model-{index}", client=client)
            for index, client in enumerate(clients, start=1)
        )
    )


def review(*, missing_human_input=False, material_choice=False):
    return {
        "approved": True,
        "captures_human_request": True,
        "targets_are_relevant": True,
        "complete_bounded_request": True,
        "clarification_policy_ok": True,
        "clarification_requires_missing_human_input": missing_human_input,
        "clarification_material_choice": material_choice,
        "no_internal_routing": True,
        "unsupported_operational_claim_risk": False,
    }


def information_proposal():
    return {
        "outcome": "information",
        "information_needs": [
            {
                "target_kind": "printer",
                "target_source": "literal",
                "target_reference": "PRINTER-22",
                "target_entity_ref": None,
                "need": "current status",
                "authority": "observe",
                "temporal_scope": "current",
                "completeness": "sufficient",
                "relationship": None,
            }
        ],
        "clarification_question": None,
        "conversational_response": None,
        "topic": "printer status",
    }


def conversation_proposal():
    return {
        "outcome": "conversation",
        "information_needs": [],
        "clarification_question": None,
        "conversational_response": "Glad to help.",
        "topic": None,
    }


def clarification_proposal():
    return {
        "outcome": "clarify",
        "information_needs": [],
        "clarification_question": "Which printer do you mean?",
        "conversational_response": None,
        "topic": "printer selection",
    }


def empty_context():
    return DynamicConversationContext(
        conversation_id="review-applicability",
        principal_id="person-al",
        organization_id="aot",
    )


def verified_printer_context():
    return DynamicConversationContext(
        conversation_id="verified-printer",
        principal_id="person-al",
        organization_id="aot",
        entities=(
            ConversationEntity(
                ref="verified-printer-1",
                kind="printer",
                canonical_id="printer-resource-22",
                display_name="PRINTER-22",
                provenance="synthetic verified resource",
            ),
        ),
        active_entity_refs={"printer": "verified-printer-1"},
        active_topic="printer condition",
    )


def test_information_review_does_not_require_clarification_only_dimensions():
    kernel = ReviewedConversationKernel(
        proposing=pool(FakeClient(information_proposal())),
        reviewing=pool(FakeClient(review())),
        resource_kinds=lambda: ("printer",),
    )

    decision, _ = kernel.interpret(
        text="What is the current status of PRINTER-22?",
        context=empty_context(),
    )

    assert decision.outcome == "information"
    assert decision.information_needs[0].target.kind == "printer"


def test_conversation_review_does_not_require_clarification_only_dimensions():
    kernel = ReviewedConversationKernel(
        proposing=pool(FakeClient(conversation_proposal())),
        reviewing=pool(FakeClient(review())),
    )

    decision, _ = kernel.interpret(text="Thanks.", context=empty_context())

    assert decision.outcome == "conversation"
    assert decision.conversational_response == "Glad to help."


def test_clarification_still_requires_missing_human_input_and_material_choice():
    kernel = ReviewedConversationKernel(
        proposing=pool(FakeClient(clarification_proposal())),
        reviewing=pool(FakeClient(review())),
    )

    with pytest.raises(ConversationKernelError):
        kernel.interpret(text="Check that printer.", context=empty_context())


def test_verified_entity_kind_is_owned_by_verified_context_not_model_text():
    proposed = {
        "outcome": "information",
        "information_needs": [
            {
                "target_kind": "endpoint",
                "target_source": "verified_entity",
                "target_reference": "printer-resource-22",
                "target_entity_ref": "verified-printer-1",
                "need": "current abnormal conditions",
                "authority": "observe",
                "temporal_scope": "current",
                "completeness": "sufficient",
                "relationship": "same verified resource",
            }
        ],
        "clarification_question": None,
        "conversational_response": None,
        "topic": "printer condition",
    }
    kernel = ReviewedConversationKernel(
        proposing=pool(FakeClient(proposed)),
        reviewing=pool(FakeClient(review())),
        resource_kinds=lambda: ("endpoint", "printer"),
    )

    decision, _ = kernel.interpret(
        text="What else is wrong with it?",
        context=verified_printer_context(),
    )

    assert decision.information_needs[0].target.kind == "printer"
    assert decision.information_needs[0].target.entity_ref == "verified-printer-1"


def test_canonical_validation_rejects_verified_entity_kind_mismatch_without_projection():
    proposed = {
        "outcome": "information",
        "information_needs": [
            {
                "target_kind": "endpoint",
                "target_source": "verified_entity",
                "target_reference": "PRINTER-22",
                "target_entity_ref": "verified-printer-1",
                "need": "current status",
                "authority": "observe",
                "temporal_scope": "current",
                "completeness": "sufficient",
                "relationship": None,
            }
        ],
        "clarification_question": None,
        "conversational_response": None,
        "topic": "printer condition",
    }

    with pytest.raises(
        ConversationKernelError,
        match="target kind must match verified entity data",
    ):
        _validate_decision(
            proposal=proposed,
            text="What else is wrong with it?",
            context=verified_printer_context(),
        )
