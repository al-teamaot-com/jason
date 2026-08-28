from __future__ import annotations

import pytest

from orchestrator.conversation_interpretation_quality import ReviewedConversationKernel
from orchestrator.conversation_kernel import (
    ConversationKernelError,
    DynamicConversationContext,
    ReasoningBackend,
    ValidatedReasoningPool,
)


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


def context():
    return DynamicConversationContext(
        conversation_id="review-verdict",
        principal_id="person-al",
        organization_id="aot",
    )


def information_proposal():
    return {
        "outcome": "information",
        "information_needs": [
            {
                "target_kind": "printer",
                "target_source": "literal",
                "target_reference": "PRINTER-55",
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


def clarification_proposal():
    return {
        "outcome": "clarify",
        "information_needs": [],
        "clarification_question": "Which printer do you want me to check?",
        "conversational_response": None,
        "topic": "printer selection",
    }


def conversation_proposal():
    return {
        "outcome": "conversation",
        "information_needs": [],
        "clarification_question": None,
        "conversational_response": "You're welcome.",
        "topic": None,
    }


def review(
    *,
    approved=True,
    captures=True,
    targets=True,
    complete=True,
    clarification_ok=True,
    missing=False,
    material=False,
    no_internal=True,
    claims=False,
):
    return {
        "approved": approved,
        "captures_human_request": captures,
        "targets_are_relevant": targets,
        "complete_bounded_request": complete,
        "clarification_policy_ok": clarification_ok,
        "clarification_requires_missing_human_input": missing,
        "clarification_material_choice": material,
        "no_internal_routing": no_internal,
        "unsupported_operational_claim_risk": claims,
    }


def test_valid_target_clarification_is_not_vetoed_by_reviewer_aggregate_or_generic_fields():
    kernel = ReviewedConversationKernel(
        proposing=pool(FakeClient(clarification_proposal())),
        reviewing=pool(
            FakeClient(
                review(
                    approved=False,
                    captures=False,
                    targets=False,
                    complete=False,
                    clarification_ok=False,
                    missing=True,
                    material=True,
                )
            )
        ),
        resource_kinds=lambda: ("printer",),
    )

    decision, _ = kernel.interpret(
        text="Check that printer.",
        context=context(),
    )

    assert decision.outcome == "clarify"
    assert decision.clarification_question == "Which printer do you want me to check?"


def test_clarification_specific_policy_dimensions_remain_mandatory():
    kernel = ReviewedConversationKernel(
        proposing=pool(FakeClient(clarification_proposal())),
        reviewing=pool(FakeClient(review(approved=True, missing=False, material=True))),
        resource_kinds=lambda: ("printer",),
    )

    with pytest.raises(ConversationKernelError):
        kernel.interpret(text="Check that printer.", context=context())


def test_information_verdict_uses_information_dimensions_not_aggregate_approval():
    kernel = ReviewedConversationKernel(
        proposing=pool(FakeClient(information_proposal())),
        reviewing=pool(FakeClient(review(approved=False))),
        resource_kinds=lambda: ("printer",),
    )

    decision, _ = kernel.interpret(
        text="What is the current status of PRINTER-55?",
        context=context(),
    )

    assert decision.outcome == "information"


def test_conversation_verdict_does_not_require_target_or_clarification_dimensions():
    kernel = ReviewedConversationKernel(
        proposing=pool(FakeClient(conversation_proposal())),
        reviewing=pool(
            FakeClient(
                review(
                    approved=False,
                    captures=True,
                    targets=False,
                    complete=False,
                    clarification_ok=False,
                )
            )
        ),
    )

    decision, _ = kernel.interpret(text="Thanks.", context=context())

    assert decision.outcome == "conversation"


def test_universal_internal_routing_and_unsupported_claim_guards_cannot_be_overridden():
    for reviewer in (
        review(approved=True, no_internal=False),
        review(approved=True, claims=True),
    ):
        kernel = ReviewedConversationKernel(
            proposing=pool(FakeClient(information_proposal())),
            reviewing=pool(FakeClient(reviewer)),
            resource_kinds=lambda: ("printer",),
        )

        with pytest.raises(ConversationKernelError):
            kernel.interpret(
                text="What is the current status of PRINTER-55?",
                context=context(),
            )
