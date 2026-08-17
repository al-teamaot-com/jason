from __future__ import annotations

import json

from orchestrator.conversation_interpretation_quality import ReviewedConversationKernel
from orchestrator.conversation_kernel import (
    DynamicConversationContext,
    ReasoningBackend,
    ValidatedReasoningPool,
)
from orchestrator.dynamic_conversation_kernel import ConversationEntity


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


def verified_endpoint_context():
    return DynamicConversationContext(
        conversation_id="conv-verified",
        principal_id="person-al",
        organization_id="aot",
        entities=(
            ConversationEntity(
                ref="verified-endpoint-1",
                kind="endpoint",
                canonical_id="resource-9",
                display_name="DEVICE-9",
                provenance="verified synthetic evidence",
            ),
        ),
        active_entity_refs={"endpoint": "verified-endpoint-1"},
        active_topic="endpoint condition",
    )


def verified_printer_context():
    return DynamicConversationContext(
        conversation_id="conv-printer",
        principal_id="person-al",
        organization_id="aot",
        entities=(
            ConversationEntity(
                ref="verified-printer-1",
                kind="printer",
                canonical_id="printer-resource-44",
                display_name="PRINTER-44",
                provenance="verified synthetic printer evidence",
            ),
        ),
        active_entity_refs={"printer": "verified-printer-1"},
        active_topic="printer condition",
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
    if outcome == "conversation":
        return {
            "outcome": "conversation",
            "information_needs": [],
            "clarification_question": None,
            "conversational_response": "You're welcome.",
            "topic": None,
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


def verified_proposal(
    *,
    kind: str,
    reference: str,
    entity_ref: str,
    need: str,
    topic: str,
):
    return {
        "outcome": "information",
        "information_needs": [
            {
                "target_kind": kind,
                "target_source": "verified_entity",
                "target_reference": reference,
                "target_entity_ref": entity_ref,
                "need": need,
                "authority": "observe",
                "temporal_scope": "current",
                "completeness": "sufficient",
                "relationship": "same verified resource",
            }
        ],
        "clarification_question": None,
        "conversational_response": None,
        "topic": topic,
    }


def review(
    *,
    approved=True,
    complete=True,
    clarification_ok=True,
    missing_human_input=True,
    material_choice=True,
    claims=False,
):
    return {
        "approved": approved,
        "captures_human_request": approved,
        "targets_are_relevant": approved,
        "complete_bounded_request": complete,
        "clarification_policy_ok": clarification_ok,
        "clarification_requires_missing_human_input": missing_human_input,
        "clarification_material_choice": material_choice,
        "no_internal_routing": approved,
        "unsupported_operational_claim_risk": claims,
    }


def test_semantically_bad_cheap_interpretation_is_rejected_and_stronger_backend_can_replace_it():
    cheap = FakeClient(proposal(need="historical unrelated alerts"))
    stronger = FakeClient(proposal(need="current requested value"))
    reviewer = FakeClient(review(approved=False), review())
    kernel = ReviewedConversationKernel(proposing=pool(cheap, stronger), reviewing=pool(reviewer))

    decision, attempts = kernel.interpret(
        text="What is the current requested value for NODE-77?", context=context()
    )

    assert decision.information_needs[0].need == "current requested value"
    assert [item.outcome for item in attempts] == ["rejected", "accepted"]
    assert [item.backend for item in attempts] == ["model-1", "model-2"]
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
        {**review(), "approved": False, "complete_bounded_request": False},
        review(),
    )
    kernel = ReviewedConversationKernel(proposing=pool(incomplete, complete), reviewing=pool(reviewer))

    decision, _ = kernel.interpret(
        text="Give me the first and second requested values for NODE-77.", context=context()
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
            "clarification_requires_missing_human_input": False,
            "clarification_material_choice": False,
        },
        review(),
    )
    kernel = ReviewedConversationKernel(proposing=pool(bad, good), reviewing=pool(reviewer))

    decision, _ = kernel.interpret(
        text="What is the current requested value for NODE-77?", context=context()
    )

    assert decision.outcome == "information"


def test_material_clarification_can_pass_review_without_execution_plan():
    proposing = FakeClient(proposal(outcome="clarify"))
    reviewer = FakeClient(review())
    kernel = ReviewedConversationKernel(proposing=pool(proposing), reviewing=pool(reviewer))

    decision, _ = kernel.interpret(text="Check that customer.", context=context())

    assert decision.outcome == "clarify"
    assert decision.information_needs == ()


def test_self_answerable_clarification_is_rejected_and_bounded_read_can_replace_it():
    bad = FakeClient(
        {
            "outcome": "clarify",
            "information_needs": [],
            "clarification_question": "What additional current problems are present on this endpoint?",
            "conversational_response": None,
            "topic": "endpoint condition",
        }
    )
    good = FakeClient(
        verified_proposal(
            kind="endpoint",
            reference="DEVICE-9",
            entity_ref="verified-endpoint-1",
            need="additional current problems or abnormal conditions",
            topic="endpoint condition",
        )
    )
    reviewer = FakeClient(
        review(
            approved=False,
            clarification_ok=False,
            missing_human_input=False,
            material_choice=False,
        ),
        review(),
    )
    kernel = ReviewedConversationKernel(proposing=pool(bad, good), reviewing=pool(reviewer))

    decision, attempts = kernel.interpret(
        text="Are there any additional current problems with it?",
        context=verified_endpoint_context(),
    )

    assert decision.outcome == "information"
    assert decision.information_needs[0].target.entity_ref == "verified-endpoint-1"
    assert [item.outcome for item in attempts] == ["rejected", "accepted"]


def test_verified_active_focus_is_projected_for_unrelated_resource_without_static_mapping():
    proposing = FakeClient(
        verified_proposal(
            kind="printer",
            reference="PRINTER-44",
            entity_ref="verified-printer-1",
            need="current abnormal conditions",
            topic="printer condition",
        )
    )
    reviewer = FakeClient(review())
    kernel = ReviewedConversationKernel(
        proposing=pool(proposing),
        reviewing=pool(reviewer),
        resource_kinds=lambda: ("printer",),
    )

    decision, _ = kernel.interpret(
        text="What else is wrong with it?",
        context=verified_printer_context(),
    )

    system, user, _, _ = proposing.calls[0]
    payload = json.loads(user)
    active = payload["context"]["active_entities"]
    assert active == [
        {
            "kind": "printer",
            "entity_ref": "verified-printer-1",
            "canonical_id": "printer-resource-44",
            "display_name": "PRINTER-44",
        }
    ]
    assert "active_entity_refs and active_entities" in system
    assert "repeat a target already resolved by verified context" in system
    assert decision.information_needs[0].target.kind == "printer"
    assert decision.information_needs[0].target.entity_ref == "verified-printer-1"
    serialized = json.dumps(payload)
    assert "capability_name" not in serialized
    assert "provider_id" not in serialized
    assert "connector_id" not in serialized


def test_clarification_review_contract_defines_unresolved_target_as_material_choice():
    proposing = FakeClient(
        {
            "outcome": "clarify",
            "information_needs": [],
            "clarification_question": "Which printer do you mean?",
            "conversational_response": None,
            "topic": "printer selection",
        }
    )
    reviewer = FakeClient(review())
    kernel = ReviewedConversationKernel(proposing=pool(proposing), reviewing=pool(reviewer))

    decision, _ = kernel.interpret(text="Check that printer.", context=context())

    system, _, _, _ = reviewer.calls[0]
    assert decision.outcome == "clarify"
    assert "selecting an otherwise unresolved target" in system
    assert "selects among possible targets" in system
    assert "choice changes the target" in system


def test_clarification_review_contract_requires_missing_human_input_and_material_choice():
    proposing = FakeClient(proposal(outcome="clarify"))
    reviewer = FakeClient(review())
    kernel = ReviewedConversationKernel(proposing=pool(proposing), reviewing=pool(reviewer))

    kernel.interpret(text="Check that customer.", context=context())

    system, _, schema, _ = reviewer.calls[0]
    required = set(schema["required"])
    assert "clarification_requires_missing_human_input" in required
    assert "clarification_material_choice" in required
    assert "specific human-supplied discriminator" in system.casefold()
    assert "broad, open-ended" in system.casefold()


def test_malformed_reviewer_boolean_falls_back_to_stronger_reviewer_backend():
    proposing = FakeClient(proposal())
    malformed = FakeClient(
        {
            "approved": "true",
            "captures_human_request": True,
            "targets_are_relevant": True,
            "complete_bounded_request": True,
            "clarification_policy_ok": True,
            "clarification_requires_missing_human_input": True,
            "clarification_material_choice": True,
            "no_internal_routing": True,
            "unsupported_operational_claim_risk": False,
        }
    )
    stronger = FakeClient(review())
    kernel = ReviewedConversationKernel(proposing=pool(proposing), reviewing=pool(malformed, stronger))

    decision, _ = kernel.interpret(
        text="What is the current requested value for NODE-77?", context=context()
    )

    assert decision.outcome == "information"
    assert len(malformed.calls) == 1
    assert len(stronger.calls) == 1


def test_outcome_projection_discards_incompatible_clarification_branch_noise_before_review():
    noisy = proposal(outcome="clarify")
    noisy["information_needs"] = [
        {
            "target_kind": "endpoint",
            "target_source": "literal",
            "target_reference": "customer",
            "target_entity_ref": None,
            "need": "identify the customer environment that must be clarified",
            "authority": "request_approval",
            "temporal_scope": "current",
            "completeness": "sufficient",
            "relationship": None,
        }
    ]
    proposing = FakeClient(noisy)
    reviewer = FakeClient(review())
    kernel = ReviewedConversationKernel(proposing=pool(proposing), reviewing=pool(reviewer))

    decision, _ = kernel.interpret(text="Check that customer.", context=context())

    assert decision.outcome == "clarify"
    assert decision.information_needs == ()
    reviewed = json.loads(reviewer.calls[0][1])["proposed_interpretation"]
    assert reviewed["information_needs"] == []
    assert reviewed["clarification_question"] == "Which customer environment do you mean?"


def test_information_read_authority_is_owned_by_jason_not_the_reasoning_model():
    proposed = proposal()
    proposed["information_needs"][0]["authority"] = "administer"
    proposing = FakeClient(proposed)
    reviewer = FakeClient(review())
    kernel = ReviewedConversationKernel(proposing=pool(proposing), reviewing=pool(reviewer))

    decision, _ = kernel.interpret(
        text="What is the current requested value for NODE-77?", context=context()
    )

    assert decision.information_needs[0].authority == "observe"
    schema = proposing.calls[0][2]
    authority = schema["properties"]["information_needs"]["items"]["properties"]["authority"]
    assert authority["enum"] == ["observe"]
    assert "jason owns read authority" in proposing.calls[0][0].casefold()


def test_outcome_projection_does_not_rescue_a_wrong_information_discriminator():
    wrong = FakeClient(
        {
            "outcome": "information",
            "information_needs": [],
            "clarification_question": None,
            "conversational_response": "You're welcome.",
            "topic": None,
        }
    )
    correct = FakeClient(proposal(outcome="conversation"))
    reviewer = FakeClient(review())
    kernel = ReviewedConversationKernel(proposing=pool(wrong, correct), reviewing=pool(reviewer))

    decision, attempts = kernel.interpret(text="Thanks.", context=context())

    assert decision.outcome == "conversation"
    assert [item.outcome for item in attempts] == ["rejected", "accepted"]
    assert len(reviewer.calls) == 1


def test_discarded_branch_cannot_hide_internal_routing_selection():
    bad = proposal(outcome="clarify")
    bad["information_needs"] = [
        {
            "target_kind": "endpoint",
            "target_source": "literal",
            "target_reference": "customer",
            "target_entity_ref": None,
            "need": "clarify target",
            "authority": "observe",
            "temporal_scope": "current",
            "completeness": "sufficient",
            "relationship": None,
            "capability_name": "internal.example",
        }
    ]
    first = FakeClient(bad)
    second = FakeClient(proposal(outcome="clarify"))
    reviewer = FakeClient(review())
    kernel = ReviewedConversationKernel(proposing=pool(first, second), reviewing=pool(reviewer))

    decision, attempts = kernel.interpret(text="Check that customer.", context=context())

    assert decision.outcome == "clarify"
    assert [item.outcome for item in attempts] == ["rejected", "accepted"]
    assert len(reviewer.calls) == 1
