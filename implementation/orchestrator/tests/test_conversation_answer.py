from __future__ import annotations

import json

from orchestrator.conversation_answer import (
    ConversationAnswerInput,
    ConversationLimitation,
    ConversationSupport,
    GroundedConversationAnswerer,
)
from orchestrator.conversation_kernel import ReasoningBackend, ValidatedReasoningPool


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


def review(*, approved=True, unsupported_claims=()):
    return {
        "approved": approved,
        "answers_request": approved,
        "supported": approved,
        "natural": approved,
        "exposes_internal_plumbing": False,
        "unsupported_claims": list(unsupported_claims),
    }


def request():
    return ConversationAnswerInput(
        question="What is the current value for NODE-77?",
        supports=(
            ConversationSupport(
                support_id="support-1",
                information_need="current requested value",
                target_reference="NODE-77",
                value="Example Value",
                evidence_reference="internal://result/1/path/2",
            ),
        ),
        internal_identifiers=(
            "endpoint.device.search",
            "datto_rmm",
        ),
    )


def test_first_acceptable_natural_answer_is_returned_only_after_quality_review():
    draft = FakeClient(
        {
            "text": "The current value for NODE-77 is Example Value.",
            "support_ids": ["support-1"],
        }
    )
    reviewer = FakeClient(review())
    answerer = GroundedConversationAnswerer(
        drafting=pool(draft),
        reviewing=pool(reviewer),
    )

    answer = answerer.answer(request())

    assert answer.text == "The current value for NODE-77 is Example Value."
    assert answer.support_ids == ("support-1",)
    assert len(reviewer.calls) == 1


def test_bad_cheap_draft_is_rejected_by_review_and_stronger_draft_can_replace_it():
    cheap = FakeClient(
        {
            "text": "NODE-77 is definitely perfect and the value is Example Value.",
            "support_ids": ["support-1"],
        }
    )
    stronger = FakeClient(
        {
            "text": "The current value for NODE-77 is Example Value.",
            "support_ids": ["support-1"],
        }
    )
    reviewer = FakeClient(
        review(approved=False, unsupported_claims=("definitely perfect",)),
        review(),
    )
    answerer = GroundedConversationAnswerer(
        drafting=pool(cheap, stronger),
        reviewing=pool(reviewer),
    )

    answer = answerer.answer(request())

    assert answer.text == "The current value for NODE-77 is Example Value."
    assert len(cheap.calls) == 1
    assert len(stronger.calls) == 1
    assert len(reviewer.calls) == 2


def test_internal_implementation_identifier_never_reaches_human_even_if_draft_uses_it():
    cheap = FakeClient(
        {
            "text": "datto_rmm says the current value is Example Value.",
            "support_ids": ["support-1"],
        }
    )
    stronger = FakeClient(
        {
            "text": "The current value is Example Value.",
            "support_ids": ["support-1"],
        }
    )
    reviewer = FakeClient(review())
    answerer = GroundedConversationAnswerer(
        drafting=pool(cheap, stronger),
        reviewing=pool(reviewer),
    )

    answer = answerer.answer(request())

    assert answer.text == "The current value is Example Value."
    assert "datto_rmm" not in answer.text
    assert len(reviewer.calls) == 1


def test_unknown_support_reference_is_rejected_before_quality_review():
    bad = FakeClient(
        {
            "text": "The value is invented.",
            "support_ids": ["support-does-not-exist"],
        }
    )
    good = FakeClient(
        {
            "text": "The value is Example Value.",
            "support_ids": ["support-1"],
        }
    )
    reviewer = FakeClient(review())
    answerer = GroundedConversationAnswerer(
        drafting=pool(bad, good),
        reviewing=pool(reviewer),
    )

    answer = answerer.answer(request())

    assert answer.text == "The value is Example Value."
    assert len(reviewer.calls) == 1


def test_evidence_reference_and_internal_identifiers_are_not_exposed_to_language_prompts():
    draft = FakeClient(
        {
            "text": "The current value is Example Value.",
            "support_ids": ["support-1"],
        }
    )
    reviewer = FakeClient(review())
    answerer = GroundedConversationAnswerer(
        drafting=pool(draft),
        reviewing=pool(reviewer),
    )

    answerer.answer(request())

    draft_payload = json.loads(draft.calls[0]["user"])
    review_payload = json.loads(reviewer.calls[0]["user"])
    serialized = json.dumps((draft_payload, review_payload))
    assert "internal://result/1/path/2" not in serialized
    assert "endpoint.device.search" not in serialized
    assert "datto_rmm" not in serialized


def test_bounded_limitation_can_be_answered_naturally_without_fake_support():
    draft = FakeClient(
        {
            "text": "I couldn't establish that from the information currently available.",
            "support_ids": [],
        }
    )
    reviewer = FakeClient(review())
    answerer = GroundedConversationAnswerer(
        drafting=pool(draft),
        reviewing=pool(reviewer),
    )
    limited = ConversationAnswerInput(
        question="What is the requested value?",
        limitations=(
            ConversationLimitation(
                information_need="requested value",
                reason="the governed evidence did not establish the requested value",
            ),
        ),
    )

    answer = answerer.answer(limited)

    assert "couldn't establish" in answer.text
    assert answer.support_ids == ()
