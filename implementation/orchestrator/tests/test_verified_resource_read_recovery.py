from orchestrator.conversation_experience import (
    _recover_verified_observe_read,
)
from orchestrator.dynamic_conversation_kernel import (
    ConversationEntity,
    DynamicConversationContext,
)


def context(*entities):
    active = {}
    for entity in entities:
        active[entity.kind] = entity.ref
    return DynamicConversationContext(
        conversation_id="conv-generic-recovery",
        principal_id="person-test",
        organization_id="aot",
        entities=tuple(entities),
        active_entity_refs=active,
    )


def entity(*, ref, kind, canonical_id, display_name):
    return ConversationEntity(
        ref=ref,
        kind=kind,
        canonical_id=canonical_id,
        display_name=display_name,
        provenance="verified provider evidence",
    )


def test_unseen_question_about_named_verified_future_resource_recovers_as_observe_only():
    printer = entity(
        ref="verified-printer-1",
        kind="printer",
        canonical_id="durable-printer-8472",
        display_name="PRINT-12",
    )

    human = "What is the arbitrary blue value for print-12?"

    decision = _recover_verified_observe_read(
        text=human,
        context=context(printer),
    )

    assert decision is not None
    assert decision.outcome == "information"
    assert len(decision.information_needs) == 1

    need = decision.information_needs[0]
    assert need.need == human
    assert need.authority == "observe"
    assert need.target.kind == "printer"
    assert need.target.source == "verified_entity"
    assert need.target.entity_ref == "verified-printer-1"
    assert need.target.reference == "durable-printer-8472"


def test_recovery_fails_closed_when_two_verified_resources_are_named():
    first = entity(
        ref="printer-1",
        kind="printer",
        canonical_id="durable-1",
        display_name="PRINT-12",
    )
    second = entity(
        ref="printer-2",
        kind="printer",
        canonical_id="durable-2",
        display_name="PRINT-13",
    )

    decision = _recover_verified_observe_read(
        text="Compare PRINT-12 with PRINT-13.",
        context=context(first, second),
    )

    assert decision is None


def test_recovery_does_not_use_active_context_when_human_names_no_verified_resource():
    printer = entity(
        ref="printer-1",
        kind="printer",
        canonical_id="durable-1",
        display_name="PRINT-12",
    )

    decision = _recover_verified_observe_read(
        text="Thanks.",
        context=context(printer),
    )

    assert decision is None
