from __future__ import annotations

from orchestrator.conversation_answer import (
    ConversationAnswerInput,
    ConversationSupport,
    GroundedConversationAnswerer,
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


def test_malformed_boolean_review_is_rejected_and_stronger_reviewer_can_accept():
    draft = FakeClient(
        {
            "text": "The value is Example Value.",
            "support_ids": ["support-1"],
        }
    )
    malformed = FakeClient(
        {
            "approved": "true",
            "answers_request": True,
            "supported": True,
            "natural": True,
            "exposes_internal_plumbing": False,
            "unsupported_claims": [],
        }
    )
    stronger = FakeClient(
        {
            "approved": True,
            "answers_request": True,
            "supported": True,
            "natural": True,
            "exposes_internal_plumbing": False,
            "unsupported_claims": [],
        }
    )
    answerer = GroundedConversationAnswerer(
        drafting=pool(draft),
        reviewing=pool(malformed, stronger),
    )
    request = ConversationAnswerInput(
        question="What is the value?",
        supports=(
            ConversationSupport(
                support_id="support-1",
                information_need="requested value",
                target_reference="NODE-77",
                value="Example Value",
                evidence_reference="internal://support/1",
            ),
        ),
    )

    answer = answerer.answer(request)

    assert answer.text == "The value is Example Value."
    assert len(malformed.calls) == 1
    assert len(stronger.calls) == 1
