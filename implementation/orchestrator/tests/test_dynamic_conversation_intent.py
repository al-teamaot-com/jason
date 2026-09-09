from __future__ import annotations

import json

import pytest

from orchestrator.dynamic_conversation_intent import (
    DynamicIntentBindingError,
    GroundedConversationIntentBuilder,
)
from orchestrator.dynamic_conversation_kernel import (
    ConversationEntity,
    DynamicCapabilityRequirement,
    DynamicConversationContext,
    DynamicConversationPlan,
    OfferedConversationCapability,
)
from orchestrator.teams_conversation_flow import ConversationIntent, ConversationIntentPlan


class FakeStructuredClient:
    def __init__(self, responses):
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
        return dict(self.responses.pop(0))


def context() -> DynamicConversationContext:
    return DynamicConversationContext(
        conversation_id="conv-1",
        principal_id="person-al",
        organization_id="aot",
        entities=(
            ConversationEntity(
                ref="device-1",
                kind="device",
                canonical_id="AOT-50107",
                display_name="AOT-50107",
                provenance="verified endpoint evidence",
            ),
            ConversationEntity(
                ref="person-1",
                kind="person",
                canonical_id="person-arnold",
                display_name="Arnold Heath",
                provenance="verified identity correlation",
            ),
        ),
        active_entity_refs={"device": "device-1", "person": "person-1"},
    )


def endpoint_capability() -> OfferedConversationCapability:
    return OfferedConversationCapability(
        capability_id="endpoint.device.search",
        description="Locate and read a governed endpoint using runtime selectors.",
        input_schema={
            "$ref": "schema://endpoint-device-search",
            "selector_keys": ["hostname", "resource_id", "user_identity"],
        },
        permission_mode="observe",
        risk="low",
    )


def identity_capability() -> OfferedConversationCapability:
    return OfferedConversationCapability(
        capability_id="identity.signin.search",
        description="Read governed cloud identity sign-in observations.",
        input_schema={
            "$ref": "schema://identity-signin-search",
            "selector_keys": ["user", "identity_id"],
        },
        permission_mode="observe",
        risk="low",
    )


def test_literal_hostname_is_grounded_verbatim_without_static_fact_mapping():
    client = FakeStructuredClient(
        [
            {
                "bindings": [
                    {
                        "argument": "hostname",
                        "source_type": "literal",
                        "source_id": None,
                        "literal": "AOT-50107",
                    }
                ]
            }
        ]
    )
    plan = DynamicConversationPlan(
        outcome="plan",
        requirements=(
            DynamicCapabilityRequirement(
                capability_id="endpoint.device.search",
                purpose="Answer the endpoint question.",
            ),
        ),
    )

    intent = GroundedConversationIntentBuilder(client=client).build(
        text="Who is logged into AOT-50107?",
        context=context(),
        plan=plan,
        capabilities=(endpoint_capability(),),
    )

    assert isinstance(intent, ConversationIntent)
    assert intent.arguments["hostname"] == "AOT-50107"
    assert intent.arguments["requested_facts"] == ["Who is logged into AOT-50107?"]
    model_input = json.loads(client.calls[0]["user"])
    assert model_input["allowed_argument_names"] == ["hostname", "resource_id", "user_identity"]
    assert "lastLoggedInUser" not in client.calls[0]["system"]


def test_verified_person_context_can_ground_cross_platform_identity_selector():
    client = FakeStructuredClient(
        [
            {
                "bindings": [
                    {
                        "argument": "user",
                        "source_type": "entity",
                        "source_id": "person-1:display_name",
                        "literal": None,
                    }
                ]
            }
        ]
    )
    plan = DynamicConversationPlan(
        outcome="plan",
        requirements=(
            DynamicCapabilityRequirement(
                capability_id="identity.signin.search",
                purpose="Check suspicious cloud sign-ins.",
                entity_refs=("person-1",),
            ),
        ),
    )

    intent = GroundedConversationIntentBuilder(client=client).build(
        text="Does it have any suspicious Office 365 logins?",
        context=context(),
        plan=plan,
        capabilities=(identity_capability(),),
    )

    assert isinstance(intent, ConversationIntent)
    assert intent.arguments["user"] == "Arnold Heath"
    assert intent.capability_name == "identity.signin.search"


def test_model_cannot_invent_literal_identifier():
    client = FakeStructuredClient(
        [
            {
                "bindings": [
                    {
                        "argument": "hostname",
                        "source_type": "literal",
                        "source_id": None,
                        "literal": "AOT-99999",
                    }
                ]
            }
        ]
    )
    plan = DynamicConversationPlan(
        outcome="plan",
        requirements=(
            DynamicCapabilityRequirement(
                capability_id="endpoint.device.search",
                purpose="Read endpoint.",
            ),
        ),
    )

    with pytest.raises(DynamicIntentBindingError, match="not grounded verbatim"):
        GroundedConversationIntentBuilder(client=client).build(
            text="Read AOT-50107.",
            context=context(),
            plan=plan,
            capabilities=(endpoint_capability(),),
        )


def test_model_cannot_invent_argument_name():
    client = FakeStructuredClient(
        [
            {
                "bindings": [
                    {
                        "argument": "magic_field",
                        "source_type": "literal",
                        "source_id": None,
                        "literal": "AOT-50107",
                    }
                ]
            }
        ]
    )
    plan = DynamicConversationPlan(
        outcome="plan",
        requirements=(
            DynamicCapabilityRequirement(
                capability_id="endpoint.device.search",
                purpose="Read endpoint.",
            ),
        ),
    )

    with pytest.raises(DynamicIntentBindingError, match="not exposed"):
        GroundedConversationIntentBuilder(client=client).build(
            text="Read AOT-50107.",
            context=context(),
            plan=plan,
            capabilities=(endpoint_capability(),),
        )


def test_multi_provider_plan_becomes_existing_read_only_intent_plan():
    client = FakeStructuredClient(
        [
            {
                "bindings": [
                    {
                        "argument": "resource_id",
                        "source_type": "entity",
                        "source_id": "device-1:canonical_id",
                        "literal": None,
                    }
                ]
            },
            {
                "bindings": [
                    {
                        "argument": "user",
                        "source_type": "entity",
                        "source_id": "person-1:display_name",
                        "literal": None,
                    }
                ]
            },
        ]
    )
    plan = DynamicConversationPlan(
        outcome="plan",
        requirements=(
            DynamicCapabilityRequirement(
                capability_id="endpoint.device.search",
                purpose="Read endpoint observations.",
                entity_refs=("device-1",),
            ),
            DynamicCapabilityRequirement(
                capability_id="identity.signin.search",
                purpose="Read identity sign-in observations.",
                entity_refs=("person-1",),
            ),
        ),
    )

    result = GroundedConversationIntentBuilder(client=client).build(
        text="Check the machine and the user's cloud sign-ins.",
        context=context(),
        plan=plan,
        capabilities=(endpoint_capability(), identity_capability()),
    )

    assert isinstance(result, ConversationIntentPlan)
    assert [item.capability_name for item in result.intents] == [
        "endpoint.device.search",
        "identity.signin.search",
    ]
    assert all(item.permission_mode == "observe" for item in result.intents)


def test_non_plan_outcomes_never_create_orchestration_intents():
    builder = GroundedConversationIntentBuilder(client=FakeStructuredClient([]))
    plan = DynamicConversationPlan(
        outcome="clarify",
        clarification_question="Which workstation do you mean?",
    )
    assert builder.build(
        text="Check it.",
        context=context(),
        plan=plan,
        capabilities=(endpoint_capability(),),
    ) is None
