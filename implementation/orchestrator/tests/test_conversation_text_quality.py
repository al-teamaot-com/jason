from __future__ import annotations

from orchestrator.conversation_kernel import ReasoningBackend, ValidatedReasoningPool
from orchestrator.conversation_text_quality import ConversationTextQualityGate


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


def review(*, approved=True, preserves=True, natural=True, plumbing=False, claims=False):
    return {
        "approved": approved,
        "preserves_meaning": preserves,
        "natural": natural,
        "exposes_internal_plumbing": plumbing,
        "adds_unsupported_operational_claims": claims,
    }


def test_already_good_candidate_is_reviewed_and_returned_without_rewrite_cost():
    rewriting = FakeClient()
    reviewing = FakeClient(review())
    gate = ConversationTextQualityGate(
        rewriting=pool(rewriting),
        reviewing=pool(reviewing),
    )

    text = gate.finalize(
        human_text="Thanks.",
        kind="conversation",
        candidate="You're welcome.",
    )

    assert text == "You're welcome."
    assert rewriting.calls == []
    assert len(reviewing.calls) == 1


def test_rejected_candidate_is_rewritten_without_changing_decided_meaning():
    rewriting = FakeClient({"text": "Which customer environment do you mean?"})
    reviewing = FakeClient(
        review(approved=False, natural=False),
        review(),
    )
    gate = ConversationTextQualityGate(
        rewriting=pool(rewriting),
        reviewing=pool(reviewing),
    )

    text = gate.finalize(
        human_text="Check that customer.",
        kind="clarification",
        candidate="Please provide additional clarification regarding customer context.",
    )

    assert text == "Which customer environment do you mean?"
    assert len(rewriting.calls) == 1
    assert len(reviewing.calls) == 2


def test_internal_identifier_forces_rewrite_before_human_delivery():
    rewriting = FakeClient({"text": "Which environment do you mean?"})
    reviewing = FakeClient(review())
    gate = ConversationTextQualityGate(
        rewriting=pool(rewriting),
        reviewing=pool(reviewing),
    )

    text = gate.finalize(
        human_text="Check that environment.",
        kind="clarification",
        candidate="Which system.registry.search environment do you mean?",
        internal_identifiers=("system.registry.search",),
    )

    assert text == "Which environment do you mean?"
    # The original internal candidate is never sent to the reviewer because the
    # deterministic guard already rejects it.
    assert len(reviewing.calls) == 1


def test_bad_cheap_rewrite_can_fall_back_to_stronger_rewriter():
    cheap = FakeClient({"text": "provider_id?"})
    stronger = FakeClient({"text": "Which environment do you mean?"})
    reviewing = FakeClient(
        review(approved=False, natural=False),
        review(),
    )
    gate = ConversationTextQualityGate(
        rewriting=pool(cheap, stronger),
        reviewing=pool(reviewing),
    )

    text = gate.finalize(
        human_text="Check that environment.",
        kind="clarification",
        candidate="Please elaborate.",
        internal_identifiers=("provider_id",),
    )

    assert text == "Which environment do you mean?"
    assert len(cheap.calls) == 1
    assert len(stronger.calls) == 1


def test_reviewer_boolean_contract_is_deterministically_validated():
    rewriting = FakeClient()
    malformed_reviewer = FakeClient(
        {
            "approved": "true",
            "preserves_meaning": True,
            "natural": True,
            "exposes_internal_plumbing": False,
            "adds_unsupported_operational_claims": False,
        }
    )
    stronger_reviewer = FakeClient(review())
    gate = ConversationTextQualityGate(
        rewriting=pool(rewriting),
        reviewing=pool(malformed_reviewer, stronger_reviewer),
    )

    text = gate.finalize(
        human_text="Thanks.",
        kind="conversation",
        candidate="You're welcome.",
    )

    assert text == "You're welcome."
    assert rewriting.calls == []
    assert len(malformed_reviewer.calls) == 1
    assert len(stronger_reviewer.calls) == 1
