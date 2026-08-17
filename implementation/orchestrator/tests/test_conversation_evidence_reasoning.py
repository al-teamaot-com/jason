from __future__ import annotations

from orchestrator.conversation_evidence_reasoning import (
    ValidatedConversationEvidenceReasoner,
)
from orchestrator.conversation_kernel import ReasoningBackend, ValidatedReasoningPool


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


def direct_review(*, approved=True, adjacent=False, risk=False):
    return {
        "approved": approved,
        "directly_supports_request": approved and not adjacent and not risk,
        "unavailable_is_justified": False,
        "uses_adjacent_or_correlated_evidence": adjacent,
        "unsupported_claim_risk": risk,
    }


def unavailable_review(*, approved=True):
    return {
        "approved": approved,
        "directly_supports_request": False,
        "unavailable_is_justified": approved,
        "uses_adjacent_or_correlated_evidence": False,
        "unsupported_claim_risk": False,
    }


def evidence():
    return {
        "resource": {
            "requestedValue": "Correct Value",
            "nearbyValue": "Adjacent Value",
        }
    }


def test_review_rejects_adjacent_cheap_path_and_selection_escalates_to_stronger_backend():
    cheap_selector = FakeClient(
        {
            "answer_type": "direct",
            "evidence_paths": ["/resource/nearbyValue"],
        }
    )
    stronger_selector = FakeClient(
        {
            "answer_type": "direct",
            "evidence_paths": ["/resource/requestedValue"],
        }
    )
    reviewer = FakeClient(
        direct_review(approved=False, adjacent=True),
        direct_review(),
    )
    reasoner = ValidatedConversationEvidenceReasoner(
        selecting=pool(cheap_selector, stronger_selector),
        reviewing=pool(reviewer),
    )

    selected = reasoner.select(
        question="requested value",
        sanitized_data=evidence(),
    )

    assert selected.answer_type == "direct"
    assert selected.evidence_paths == ("/resource/requestedValue",)
    assert len(cheap_selector.calls) == 1
    assert len(stronger_selector.calls) == 1
    assert len(reviewer.calls) == 2


def test_unjustified_unavailable_decision_is_rejected_and_can_escalate_to_direct_support():
    cheap_selector = FakeClient(
        {
            "answer_type": "unavailable",
            "evidence_paths": [],
        }
    )
    stronger_selector = FakeClient(
        {
            "answer_type": "direct",
            "evidence_paths": ["/resource/requestedValue"],
        }
    )
    reviewer = FakeClient(
        {
            "approved": False,
            "directly_supports_request": True,
            "unavailable_is_justified": False,
            "uses_adjacent_or_correlated_evidence": False,
            "unsupported_claim_risk": False,
        },
        direct_review(),
    )
    reasoner = ValidatedConversationEvidenceReasoner(
        selecting=pool(cheap_selector, stronger_selector),
        reviewing=pool(reviewer),
    )

    selected = reasoner.select(
        question="requested value",
        sanitized_data=evidence(),
    )

    assert selected.evidence_paths == ("/resource/requestedValue",)


def test_genuine_unavailable_decision_can_pass_review_without_invented_path():
    selector = FakeClient(
        {
            "answer_type": "unavailable",
            "evidence_paths": [],
        }
    )
    reviewer = FakeClient(unavailable_review())
    reasoner = ValidatedConversationEvidenceReasoner(
        selecting=pool(selector),
        reviewing=pool(reviewer),
    )

    selected = reasoner.select(
        question="requested value",
        sanitized_data={"resource": {"other": "Not It"}},
    )

    assert selected.answer_type == "unavailable"
    assert selected.evidence_paths == ()


def test_invalid_review_boolean_can_fall_back_to_stronger_review_backend():
    selector = FakeClient(
        {
            "answer_type": "direct",
            "evidence_paths": ["/resource/requestedValue"],
        }
    )
    malformed = FakeClient(
        {
            "approved": "true",
            "directly_supports_request": True,
            "unavailable_is_justified": False,
            "uses_adjacent_or_correlated_evidence": False,
            "unsupported_claim_risk": False,
        }
    )
    stronger = FakeClient(direct_review())
    reasoner = ValidatedConversationEvidenceReasoner(
        selecting=pool(selector),
        reviewing=pool(malformed, stronger),
    )

    selected = reasoner.select(
        question="requested value",
        sanitized_data=evidence(),
    )

    assert selected.evidence_paths == ("/resource/requestedValue",)
    assert len(malformed.calls) == 1
    assert len(stronger.calls) == 1


def test_selector_schema_contains_only_existing_sanitized_paths():
    selector = FakeClient(
        {
            "answer_type": "direct",
            "evidence_paths": ["/resource/requestedValue"],
        }
    )
    reviewer = FakeClient(direct_review())
    reasoner = ValidatedConversationEvidenceReasoner(
        selecting=pool(selector),
        reviewing=pool(reviewer),
    )

    reasoner.select(
        question="requested value",
        sanitized_data=evidence(),
    )

    schema = selector.calls[0][2]
    offered = set(schema["properties"]["evidence_paths"]["items"]["enum"])
    assert offered == {
        "/resource/requestedValue",
        "/resource/nearbyValue",
    }
