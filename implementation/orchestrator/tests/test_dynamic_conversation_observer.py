from __future__ import annotations

import json

import pytest

from orchestrator.dynamic_conversation_kernel import DynamicConversationContext
from orchestrator.dynamic_conversation_observer import (
    DynamicConversationEntityObserver,
    DynamicConversationObservationError,
)


class FakeClient:
    def __init__(self, response):
        self.response = response
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
        return dict(self.response)


def context():
    return DynamicConversationContext(
        conversation_id="conv-1",
        principal_id="person-al",
        organization_id="aot",
    )


def test_observer_creates_provider_independent_entities_from_verified_response_only():
    client = FakeClient(
        {
            "entities": [
                {
                    "kind": "device",
                    "canonical_literal": "AOT-50107",
                    "display_literal": "AOT-50107",
                    "make_active": True,
                },
                {
                    "kind": "person",
                    "canonical_literal": "AzureAD\\ArnoldHeath",
                    "display_literal": "AzureAD\\ArnoldHeath",
                    "make_active": True,
                },
            ]
        }
    )

    updated = DynamicConversationEntityObserver(client=client).observe(
        context=context(),
        response_text=(
            "AOT-50107 — last logged in user: AzureAD\\ArnoldHeath. "
            "Source: governed provider evidence."
        ),
        provenance="verified Teams response:m1",
    )

    assert updated.entity(updated.active_entity_refs["device"]).canonical_id == "AOT-50107"
    assert (
        updated.entity(updated.active_entity_refs["person"]).canonical_id
        == "AzureAD\\ArnoldHeath"
    )
    model_input = json.loads(client.calls[0]["user"])
    assert "provider" not in model_input
    assert "question_to_field" not in client.calls[0]["system"]


def test_observer_rejects_value_not_present_in_verified_response():
    client = FakeClient(
        {
            "entities": [
                {
                    "kind": "person",
                    "canonical_literal": "Invented Person",
                    "display_literal": "Invented Person",
                    "make_active": True,
                }
            ]
        }
    )

    with pytest.raises(DynamicConversationObservationError, match="grounded verbatim"):
        DynamicConversationEntityObserver(client=client).observe(
            context=context(),
            response_text="AOT-50107 is online.",
            provenance="verified Teams response:m1",
        )


def test_observer_does_not_send_secret_shaped_response_value_to_model():
    client = FakeClient({"entities": []})
    token = "Bearer abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    DynamicConversationEntityObserver(client=client).observe(
        context=context(),
        response_text=token,
        provenance="verified Teams response:m1",
    )

    assert client.calls == []


def test_observer_rejects_two_active_entities_of_same_kind():
    client = FakeClient(
        {
            "entities": [
                {
                    "kind": "device",
                    "canonical_literal": "AOT-50107",
                    "display_literal": "AOT-50107",
                    "make_active": True,
                },
                {
                    "kind": "device",
                    "canonical_literal": "AOT-50282",
                    "display_literal": "AOT-50282",
                    "make_active": True,
                },
            ]
        }
    )

    with pytest.raises(DynamicConversationObservationError, match="multiple observed entities"):
        DynamicConversationEntityObserver(client=client).observe(
            context=context(),
            response_text="AOT-50107 and AOT-50282 are both in scope.",
            provenance="verified Teams response:m1",
        )
