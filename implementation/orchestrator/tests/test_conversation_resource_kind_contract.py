from __future__ import annotations

import json

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


def proposal(kind):
    return {
        "outcome": "information",
        "information_needs": [
            {
                "target_kind": kind,
                "target_source": "literal",
                "target_reference": "NODE-77",
                "target_entity_ref": None,
                "need": "current requested value",
                "authority": "observe",
                "temporal_scope": "current",
                "completeness": "sufficient",
                "relationship": None,
            }
        ],
        "clarification_question": None,
        "conversational_response": None,
        "topic": "resource state",
    }


def approved_review():
    return {
        "approved": True,
        "captures_human_request": True,
        "targets_are_relevant": True,
        "complete_bounded_request": True,
        "clarification_policy_ok": True,
        "no_internal_routing": True,
        "unsupported_operational_claim_risk": False,
    }


def test_unregistered_kind_is_rejected_before_review_and_next_backend_can_use_runtime_kind():
    cheap = FakeClient(proposal("computer"))
    stronger = FakeClient(proposal("endpoint"))
    reviewer = FakeClient(approved_review())
    kernel = ReviewedConversationKernel(
        proposing=pool(cheap, stronger),
        reviewing=pool(reviewer),
        resource_kinds=lambda: ("endpoint", "printer"),
    )

    decision, attempts = kernel.interpret(
        text="What is the current requested value for NODE-77?",
        context=context(),
    )

    assert decision.information_needs[0].target.kind == "endpoint"
    assert [item.outcome for item in attempts] == ["rejected", "accepted"]
    # The invalid resource vocabulary never reaches the semantic reviewer.
    assert len(reviewer.calls) == 1


def test_runtime_resource_kinds_are_visible_without_capability_or_provider_ids():
    proposer = FakeClient(proposal("printer"))
    reviewer = FakeClient(approved_review())
    kernel = ReviewedConversationKernel(
        proposing=pool(proposer),
        reviewing=pool(reviewer),
        resource_kinds=lambda: ("printer",),
    )

    kernel.interpret(
        text="What is the current requested value for NODE-77?",
        context=context(),
    )

    payload = json.loads(proposer.calls[0][1])
    schema = proposer.calls[0][2]
    assert payload["available_resource_kinds"] == ["printer"]
    assert schema["properties"]["information_needs"]["items"]["properties"][
        "target_kind"
    ]["enum"] == ["printer"]
    serialized = json.dumps(payload)
    assert "capability_name" not in serialized
    assert "provider_id" not in serialized
    assert "connector_id" not in serialized


def test_resource_kind_registry_is_read_each_turn_so_future_resources_require_no_prompt_patch():
    kinds = ["endpoint"]
    proposer = FakeClient(proposal("endpoint"), proposal("printer"))
    reviewer = FakeClient(approved_review(), approved_review())
    kernel = ReviewedConversationKernel(
        proposing=pool(proposer),
        reviewing=pool(reviewer),
        resource_kinds=lambda: tuple(kinds),
    )

    first, _ = kernel.interpret(
        text="Inspect NODE-77.",
        context=context(),
    )
    kinds.append("printer")
    second, _ = kernel.interpret(
        text="Inspect NODE-77 as a printer resource.",
        context=context(),
    )

    assert first.information_needs[0].target.kind == "endpoint"
    assert second.information_needs[0].target.kind == "printer"
