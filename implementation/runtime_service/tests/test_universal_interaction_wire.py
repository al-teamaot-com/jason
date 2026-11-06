"""Cross-language schema contract and no authority claims in presentation wire."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jsonschema
import pytest

from jason_runtime.universal_interaction import (
    Action, ActionType, Condition, Field, FieldType, Interaction,
    InteractionKind, Option, VisualIntent,
)
from jason_runtime.universal_interaction.wire import to_wire
from jason_runtime.universal_interaction.service import ChannelFeatures

SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "interaction-v1.schema.json"


def spec(**changes):
    args = dict(
        interaction_id="univ.test.1", workflow="procurement",
        correlation_id="quote.correlation", organization_id="aot",
        requester_identity_id="svc-procurement",
        kind=InteractionKind.QUESTIONNAIRE,
        title="Quote request", summary="Supply details",
        visual_intent=VisualIntent.ACTION_REQUIRED,
        fields=(
            Field("quote", "Client quote", FieldType.BOOLEAN),
            Field("contact", "Contact", FieldType.TEXT,
                  show_when=Condition("quote", True)),
            Field("cost", "Cost", FieldType.CURRENCY, required=True,
                  currency="USD", minimum="0.01"),
            Field("ticket", "Ticket", FieldType.SELECT, required=True,
                  options=(Option("none", "No ticket"),)),
        ),
        actions=(Action("submit", "Continue", ActionType.SUBMIT),),
    )
    args.update(changes)
    return Interaction(**args)


@pytest.fixture
def validator():
    schema = json.loads(SCHEMA.read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())


def test_cross_language_v1_purchase_order_is_schema_valid(validator):
    wire = to_wire(spec())
    validator.validate(wire)
    assert wire["contract_version"] == "1.0"
    assert wire["fields"][2]["currency"] == "USD"
    assert wire["fields"][1]["show_when"] == {"depends_on": "quote", "equals": True}
    assert "recipient" not in wire and "aadObjectId" not in wire
    assert "access_token" not in wire


def test_nonexecuting_approval_json_must_reference_existing_request(validator):
    item = spec(
        kind=InteractionKind.APPROVAL, fields=(),
        actions=(Action("yes", "Approve", ActionType.APPROVE),
                 Action("no", "Deny", ActionType.DENY)),
        approval_id="already.persisted.1",
        expires_at=datetime.now(timezone.utc)+timedelta(minutes=15),
    )
    validator.validate(to_wire(item))


@pytest.mark.parametrize("bad", [
    {"principal_id":"fake-owner"},
    {"aadObjectId":"fake-ms-object"},
    {"channel":"teams"},
    {"token":"untrusted"},
    {"authorization_context":"fake"},
])
def test_wire_schema_rejects_untrusted_authority_channel_fields(validator, bad):
    wire = {**to_wire(spec()), **bad}
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(wire)


def test_unknown_contract_version_and_missing_approval_ref_rejected(validator):
    wire = to_wire(spec())
    wire["contract_version"] = "2.0"
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(wire)
    wire = to_wire(spec())
    wire["kind"] = "approval"
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(wire)


def test_notice_and_progress_have_no_approval_or_form_fields():
    with pytest.raises(ValueError):
        spec(kind=InteractionKind.NOTICE, fields=(), actions=(
            Action("yes", "Approve", ActionType.APPROVE),
        ))


def test_acknowledgement_actions_cannot_disappear_in_limited_channel():
    ack = spec(
        kind=InteractionKind.ACKNOWLEDGEMENT, fields=(),
        actions=(Action("gotit", "Got it", ActionType.ACKNOWLEDGE),),
    )
    assert ChannelFeatures(notices=True).supports(ack) is False
    assert ChannelFeatures(notices=True, authenticated_responses=True,
                           acknowledgement_controls=True).supports(ack) is True
