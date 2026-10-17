"""Inert ADR-009 callback handoff; no direct Teams endpoint or provider mutation."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import json

import pytest

from jason_runtime.universal_interaction import (
    Action, ActionType, Condition, Field, FieldType, Interaction, InteractionKind,
    InteractionRejected, Option, VisualIntent, OrchestrationResponseJournal,
    UniversalResponseHandoff, VerifiedReply,
)
from orchestrator.event_store import SQLiteOrchestrationEventStore

NOW = datetime.now(timezone.utc).replace(microsecond=0)


def questionnaire():
    return Interaction(
        interaction_id="ui.response.po", workflow="procurement",
        correlation_id="po.corr", organization_id="aot",
        requester_identity_id="svc-procurement", kind=InteractionKind.QUESTIONNAIRE,
        title="Invoice / PO questions", summary="Complete required fields",
        visual_intent=VisualIntent.ACTION_REQUIRED,
        fields=(
            Field("price", "Unit price", FieldType.CURRENCY, True,
                  currency="USD", minimum="0.01"),
            Field("raise_quote", "Create quote", FieldType.BOOLEAN),
            Field("contact", "Contact", FieldType.TEXT, True,
                  show_when=Condition("raise_quote", True)),
            Field("ticket", "Ticket", FieldType.SELECT, True,
                  options=(Option("none", "No ticket"), Option("T20261017.0001", "Ticket 1"))),
        ),
        actions=(Action("submit", "Submit", ActionType.SUBMIT),),
        expires_at=NOW + timedelta(hours=1),
    )


def approval():
    return Interaction(
        interaction_id="ui.response.approval", workflow="sample_release",
        correlation_id="release.corr", organization_id="aot",
        requester_identity_id="svc-jason-release-manager",
        kind=InteractionKind.APPROVAL, title="Harmless release example",
        summary="No execution", visual_intent=VisualIntent.ACTION_REQUIRED,
        approval_id="persisted.test.release",
        expires_at=NOW + timedelta(hours=1),
        actions=(Action("yes", "Approve", ActionType.APPROVE),
                 Action("no", "Deny", ActionType.DENY)),
    )


def reply(spec, *, action_key=None, answers=None, **updates):
    if action_key is None:
        action_key = "submit" if spec.kind is InteractionKind.QUESTIONNAIRE else "yes"
    args = dict(
        interaction_id=spec.interaction_id, response_id="signed-message-1",
        actor_identity_id="owner-al", organization_id="aot",
        client_id=None, action_key=action_key, answers=answers or {},
        evidence_ref="trusted-gateway-audit-ref", received_at=NOW,
    )
    args.update(updates)
    return VerifiedReply(**args)


@pytest.fixture
def fixture(tmp_path):
    events = SQLiteOrchestrationEventStore(tmp_path / "original-orchestrator-audit.db")
    sink_calls, approval_calls = [], []
    trusted = SimpleNamespace(verify=lambda **kwargs: fixture_response[0])
    policy = SimpleNamespace(may_respond=lambda spec, verified: verified.actor_identity_id=="owner-al")
    approvals = SimpleNamespace(
        accept_from_existing_signed_ingress=lambda **kwargs: approval_calls.append(kwargs) or "approved"
    )
    sink = SimpleNamespace(
        accept_validated_answers=lambda **kwargs: sink_calls.append(kwargs)
    )
    fixture_response = [reply(questionnaire())]
    handoff = UniversalResponseHandoff(
        trusted_ingress=trusted, responder_authority=policy,
        existing_approvals=approvals, workflow_answers=sink,
        journal=OrchestrationResponseJournal(events), callback_enabled=False,
    )
    yield SimpleNamespace(events=events, handoff=handoff, replies=fixture_response,
                          sink_calls=sink_calls, approval_calls=approval_calls)
    events.close()


def test_production_integration_is_disabled_by_default(fixture):
    with pytest.raises(InteractionRejected, match="not activated"):
        fixture.handoff.accept(questionnaire(), "signed-event")
    assert fixture.sink_calls == []


def test_registered_questionnaire_callback_delivers_schema_answers_only(fixture):
    fixture.handoff.callback_enabled = True
    fixture.replies[0] = reply(
        questionnaire(), answers={
            "price": "105.60", "raise_quote": True, "contact": "Cindy", "ticket": "none",
        })
    receipt = fixture.handoff.accept(questionnaire(), "opaque-existing-gateway-event")
    assert receipt.status == "recorded"
    assert receipt.evidence_ref == "trusted-gateway-audit-ref"
    assert fixture.sink_calls[0]["answers"]["price"] == "105.60"
    assert fixture.approval_calls == []
    events = fixture.events.list_by_execution("ui.response.po")
    assert [e.stage for e in events] == ["response_claim", "response_recorded"]
    assert "105.60" not in json.dumps(dict(events[0].payload))  # no invoice data leaked


def test_duplicate_signed_or_new_response_id_does_not_repeat_business_callback(fixture):
    fixture.handoff.callback_enabled = True
    fixture.replies[0] = reply(questionnaire(), answers={
        "price":"1.00","ticket":"none",
    })
    fixture.handoff.accept(questionnaire(), "signed-event")
    fixture.replies[0] = replace(fixture.replies[0], response_id="different-message")
    with pytest.raises(InteractionRejected, match="already claimed"):
        fixture.handoff.accept(questionnaire(), "different-valid-signed-event")
    assert len(fixture.sink_calls) == 1


@pytest.mark.parametrize("bad", [
    {"organization_id":"other"}, {"client_id":"foreign"},
    {"interaction_id":"different"}, {"evidence_ref":""},
    {"actor_identity_id":"unapproved"}, {"received_at":datetime(2026,10,17)},
])
def test_verified_actor_or_scope_fails_closed_before_claim(fixture, bad):
    fixture.handoff.callback_enabled = True
    fixture.replies[0] = replace(reply(questionnaire()), **bad)
    with pytest.raises(InteractionRejected):
        fixture.handoff.accept(questionnaire(), "signed-event")
    assert fixture.events.list_by_execution("ui.response.po") == ()


def test_questionnaire_missing_conditional_answer_is_rejected_before_business(fixture):
    fixture.handoff.callback_enabled = True
    fixture.replies[0] = reply(questionnaire(), answers={
        "price":"15.50","raise_quote":True,"ticket":"none",
    })
    with pytest.raises(ValueError, match="required"):
        fixture.handoff.accept(questionnaire(), "signed-event")
    assert fixture.sink_calls == []
    assert fixture.events.list_by_execution("ui.response.po") == ()


def test_questionnaire_rejects_unregistered_form_action(fixture):
    fixture.handoff.callback_enabled = True
    fixture.replies[0] = reply(questionnaire(), action_key="approve",
                               answers={"price":"15", "ticket":"none"})
    with pytest.raises(InteractionRejected, match="unregistered action"):
        fixture.handoff.accept(questionnaire(), "signed-event")


def test_existing_approval_is_only_decision_taker_in_controlled_test(fixture):
    fixture.handoff.callback_enabled = True
    fixture.replies[0] = reply(approval(), action_key="yes")
    receipt = fixture.handoff.accept(approval(), "existing-verified-signed-event")
    assert receipt.existing_approval_result == "approved"
    assert len(fixture.approval_calls) == 1
    assert fixture.approval_calls[0]["spec"].approval_id == "persisted.test.release"
    assert fixture.sink_calls == []


def test_existing_approval_cannot_modify_immutable_scope(fixture):
    fixture.handoff.callback_enabled = True
    fixture.replies[0] = reply(approval(), action_key="yes",
                               answers={"risk":"low"})
    with pytest.raises(InteractionRejected, match="cannot alter"):
        fixture.handoff.accept(approval(), "signed-event")
    assert fixture.approval_calls == []


def test_expiry_is_evaluated_using_server_clock_not_claimed_callback_time(fixture):
    fixture.handoff.callback_enabled = True
    fixture.replies[0] = reply(questionnaire(), answers={"price":"1","ticket":"none"})
    fixture.handoff.clock = lambda: NOW + timedelta(days=1)
    with pytest.raises(InteractionRejected, match="expired"):
        fixture.handoff.accept(questionnaire(), "signed-event")
    assert fixture.sink_calls == []


def test_uncertain_business_callback_stays_claimed_not_blindly_replayed(fixture):
    fixture.handoff.callback_enabled = True
    fixture.replies[0] = reply(questionnaire(), answers={"price":"1","ticket":"none"})
    def maybe_wrote(**kwargs):
        fixture.sink_calls.append(kwargs)
        raise TimeoutError("business result unknown")
    fixture.handoff.workflow_answers = SimpleNamespace(accept_validated_answers=maybe_wrote)
    with pytest.raises(TimeoutError):
        fixture.handoff.accept(questionnaire(), "signed-event")
    with pytest.raises(InteractionRejected, match="already claimed"):
        fixture.handoff.accept(questionnaire(), "second-message")
    assert len(fixture.sink_calls) == 1
    events = fixture.events.list_by_execution("ui.response.po")
    assert [e.stage for e in events] == ["response_claim", "response_uncertain"]
