from __future__ import annotations

import pytest

from orchestrator.conversation_kernel import (
    ConversationKernelError,
    ReasoningBackend,
    ValidatedReasoningPool,
)

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
            "evidence_paths": [
                "/resource/requestedValue"
            ],
        }
    )

    reviewer = FakeClient(
        direct_review()
    )

    reasoner = ValidatedConversationEvidenceReasoner(
        selecting=pool(selector),
        reviewing=pool(reviewer),
    )

    reasoner.select(
        question="requested value",
        sanitized_data=evidence(),
    )

    schema = selector.calls[0][2]

    items = (
        schema["properties"]
        ["evidence_paths"]
        ["items"]
    )

    # Provider-derived paths must not be embedded in the
    # structured-output schema. They are validated
    # deterministically after generation instead.
    assert items == {
        "type": "string"
    }

def test_selector_schema_does_not_embed_provider_derived_paths():
    from orchestrator.conversation_evidence_reasoning import (
        _selection_schema,
    )

    path = "/provider_data/example/' Write-Host \""

    schema = _selection_schema(
        (path,)
    )

    assert (
        schema["properties"]
        ["evidence_paths"]
        ["items"]
        == {"type": "string"}
    )

    assert path not in str(schema)


def test_contradictory_direct_and_unavailable_review_is_rejected_and_can_retry():
    selector = FakeClient(
        {
            "answer_type": "direct",
            "evidence_paths": ["/resource/requestedValue"],
        }
    )

    contradictory = FakeClient(
        {
            "approved": True,
            "directly_supports_request": True,
            "unavailable_is_justified": True,
            "uses_adjacent_or_correlated_evidence": False,
            "unsupported_claim_risk": False,
        }
    )

    valid = FakeClient(
        direct_review()
    )

    reasoner = ValidatedConversationEvidenceReasoner(
        selecting=pool(selector),
        reviewing=pool(
            contradictory,
            valid,
        ),
    )

    selected = reasoner.select(
        question="requested value",
        sanitized_data=evidence(),
    )

    assert selected.answer_type == "direct"
    assert selected.evidence_paths == (
        "/resource/requestedValue",
    )
    assert len(contradictory.calls) == 1
    assert len(valid.calls) == 1


def test_exhausted_evidence_validation_fails_closed_as_unavailable():
    selector = FakeClient(
        {
            "answer_type": "direct",
            "evidence_paths": ["/resource/adjacent"],
        }
    )

    reviewer = FakeClient(
        {
            "approved": False,
            "directly_supports_request": False,
            "unavailable_is_justified": False,
            "uses_adjacent_or_correlated_evidence": True,
            "unsupported_claim_risk": True,
        }
    )

    reasoner = ValidatedConversationEvidenceReasoner(
        selecting=pool(selector),
        reviewing=pool(reviewer),
    )

    selection = reasoner.select(
        question="requested fact",
        sanitized_data={
            "resource": {
                "adjacent": "not the requested fact",
            }
        },
    )

    assert selection.answer_type == "unavailable"
    assert selection.evidence_paths == ()


def test_non_evidence_reasoning_pool_failure_is_not_converted_to_unavailable():
    class BrokenClient:
        model = "broken"

        def complete(
            self,
            *,
            system,
            user,
            schema,
            max_output_tokens=160,
        ):
            raise RuntimeError("transport exploded")

    reasoner = ValidatedConversationEvidenceReasoner(
        selecting=ValidatedReasoningPool(
            backends=(
                ReasoningBackend(
                    name="broken",
                    client=BrokenClient(),
                ),
            )
        ),
        reviewing=pool(
            FakeClient(
                {
                    "approved": True,
                    "directly_supports_request": True,
                    "unavailable_is_justified": False,
                    "uses_adjacent_or_correlated_evidence": False,
                    "unsupported_claim_risk": False,
                }
            )
        ),
    )

    with pytest.raises(
        ConversationKernelError,
    ):
        reasoner.select(
            question="requested fact",
            sanitized_data={
                "resource": {
                    "value": "present",
                }
            },
        )


def test_nested_evidence_reasoning_exhaustion_fails_closed_as_unavailable():
    from orchestrator.conversation_evidence_reasoning import (
        ConversationEvidenceReasoningError,
    )

    class NestedEvidenceFailurePool:
        def complete_validated(self, **kwargs):
            try:
                try:
                    raise ConversationEvidenceReasoningError(
                        "evidence support review cannot be both direct and unavailable"
                    )
                except ConversationEvidenceReasoningError as error:
                    raise ConversationKernelError(
                        "inner bounded validation exhausted"
                    ) from error
            except ConversationKernelError as error:
                raise ConversationKernelError(
                    "outer bounded validation exhausted"
                ) from error

    reasoner = ValidatedConversationEvidenceReasoner(
        selecting=NestedEvidenceFailurePool(),
        reviewing=NestedEvidenceFailurePool(),
    )

    selection = reasoner.select(
        question="Does this endpoint require a restart?",
        sanitized_data={
            "endpoint": {
                "maintenance_state": {
                    "reboot_required": True,
                }
            }
        },
    )

    assert selection.answer_type == "unavailable"
    assert selection.evidence_paths == ()


def test_nested_non_evidence_failure_is_not_converted_to_unavailable():
    class NestedRuntimeFailurePool:
        def complete_validated(self, **kwargs):
            try:
                raise RuntimeError(
                    "transport exploded"
                )
            except RuntimeError as error:
                raise ConversationKernelError(
                    "bounded reasoning backend failed"
                ) from error

    reasoner = ValidatedConversationEvidenceReasoner(
        selecting=NestedRuntimeFailurePool(),
        reviewing=NestedRuntimeFailurePool(),
    )

    with pytest.raises(ConversationKernelError):
        reasoner.select(
            question="What is the governed value?",
            sanitized_data={
                "resource": {
                    "value": "present",
                }
            },
        )
