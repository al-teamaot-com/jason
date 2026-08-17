from __future__ import annotations

from orchestrator.conversation_interpretation_quality import ReviewedConversationKernel
from orchestrator.conversation_kernel import (
    DynamicConversationContext,
    ReasoningBackend,
    ValidatedReasoningPool,
)


class FakeClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, *, system, user, schema, max_output_tokens=160):
        self.calls.append((system, user, schema, max_output_tokens))
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
        conversation_id="conv-1",
        principal_id="person-al",
        organization_id="aot",
    )


def proposal(*, need="current requested value", outcome="information"):
    if outcome == "clarify":
        return {
            "outcome": "clarify",
            "information_needs": [],
            "clarification_question": "Which customer environment do you mean?",
            "conversational_response": None,
            "topic": "customer environment",
        }
    return {
        "outcome": "information",
        "information_needs": [
            {
                "target_kind": "endpoint",
                "target_source": "literal",
                "target_reference": "NODE-77",
                "target_entity_ref": None,
                "need": need,
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


def review(*, approved=True, complete=True, clarification_ok=True, claims=False):
    return {
        "approved": approved,
        "captures_human_request": approved,
        "targets_are_relevant": approved,
        "complete_bounded_request": complete,
        "clarification_policy_ok": clarification_ok,
        "no_internal_routing": approved,
        "unsupported_operational_claim_risk": claims,
    }


def test_semantically_bad_cheap_interpretation_is_rejected_and_stronger_backend_can_replace_it():
    cheap = FakeClient(proposal(need="historical unrelated alerts"))
    stronger = FakeClient(proposal(need="current requested value"))
    reviewer = FakeClient(
        review(approved=False),
        review(),
    )
    kernel = ReviewedConversationKernel(
        proposing=pool(cheap, stronger),
        reviewing=pool(reviewer),
    )

    decision, attempts = kernel.interpret(
        text="What is the current requested value for NODE-77?",
        context=context(),
    )

    assert decision.information_needs[0].need == "current requested value"
    assert [item.outcome for item in attempts] == ["rejected", "accepted"]
    assert len(reviewer.calls) == 2


def test_incomplete_multi_fact_interpretation_is_rejected():
    incomplete = FakeClient(proposal(need="first requested value"))
    complete = FakeClient(
        {
            "outcome": "information",
            "information_needs": [
                {
                    "target_kind": "endpoint",
                    "target_source": "literal",
                    "target_reference": "NODE-77",
                    "target_entity_ref": None,
                    "need": "first requested value",
                    "authority": "observe",
                    "temporal_scope": "current",
                    "completeness": "sufficient",
                    "relationship": None,
                },
                {
                    "target_kind": "endpoint",
                    "target_source": "literal",
                    "target_reference": "NODE-77",
                    "target_entity_ref": None,
                    "need": "second requested value",
                    "authority": "observe",
                    "temporal_scope": "current",
                    "completeness": "sufficient",
                    "relationship": None,
                },
            ],
            "clarification_question": None,
            "conversational_response": None,
            "topic": "endpoint state",
        }
    )
    reviewer = FakeClient(
        {
            **review(),
            "approved": False,
            "complete_bounded_request": False,
        },
        review(),
    )
    kernel = ReviewedConversationKernel(
        proposing=pool(incomplete, complete),
        reviewing=pool(reviewer),
    )

    decision, _ = kernel.interpret(
        text="Give me the first and second requested values for NODE-77.",
        context=context(),
    )

    assert len(decision.information_needs) == 2


def test_internal_evidence_source_clarification_can_be_rejected_as_policy_violation():
    bad = FakeClient(
        {
            "outcome": "clarify",
            "information_needs": [],
            "clarification_question": "Which internal evidence source should I search?",
            "conversational_response": None,
            "topic": "resource question",
        }
    )
    good = FakeClient(proposal())
    reviewer = FakeClient(
        {
            **review(),
            "approved": False,
            "clarification_policy_ok": False,
        },
        review(),
    )
    kernel = ReviewedConversationKernel(
        proposing=pool(bad, good),
        reviewing=pool(reviewer),
    )

    decision, _ = kernel.interpret(
        text="What is the current requested value for NODE-77?",
        context=context(),
    )

    assert decision.outcome == "information"


def test_material_clarification_can_pass_review_without_execution_plan():
    proposing = FakeClient(proposal(outcome="clarify"))
    reviewer = FakeClient(review())
    kernel = ReviewedConversationKernel(
        proposing=pool(proposing),
        reviewing=pool(reviewer),
    )

    decision, _ = kernel.interpret(
        text="Check that customer.",
        context=context(),
    )

    assert decision.outcome == "clarify"
    assert decision.information_needs == ()


def test_malformed_reviewer_boolean_falls_back_to_stronger_reviewer_backend():
    proposing = FakeClient(proposal())
    malformed = FakeClient(
        {
            "approved": "true",
            "captures_human_request": True,
            "targets_are_relevant": True,
            "complete_bounded_request": True,
            "clarification_policy_ok": True,
            "no_internal_routing": True,
            "unsupported_operational_claim_risk": False,
        }
    )
    stronger = FakeClient(review())
    kernel = ReviewedConversationKernel(
        proposing=pool(proposing),
        reviewing=pool(malformed, stronger),
    )

    decision, _ = kernel.interpret(
        text="What is the current requested value for NODE-77?",
        context=context(),
    )

    assert decision.outcome == "information"
    assert len(malformed.calls) == 1
    assert len(stronger.calls) == 1
