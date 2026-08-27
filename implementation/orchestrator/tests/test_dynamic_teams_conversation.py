from __future__ import annotations

from types import SimpleNamespace

from orchestrator.dynamic_conversation_kernel import (
    DynamicConversationContext,
    DynamicConversationPlan,
    DynamicCapabilityRequirement,
)
from orchestrator.dynamic_teams_conversation import DynamicTeamsConversationCoordinator
from orchestrator.teams_conversation_flow import (
    BoundConversationPrincipal,
    ConversationGuidanceRequiredError,
    ConversationIntent,
    TeamsConversationPrincipalEvidence,
)


class MemoryStore:
    def __init__(self):
        self.items = {}

    def get(self, *, organization_id, principal_id, conversation_id):
        return self.items.get((organization_id, principal_id, conversation_id))

    def put(self, context):
        self.items[(context.organization_id, context.principal_id, context.conversation_id)] = context
        return context


class ContinuationStore:
    def __init__(self, state=None):
        self.state = state
        self.calls = []

    def get(self, *, organization_id, principal_id, conversation_id):
        self.calls.append((organization_id, principal_id, conversation_id))
        return self.state


class Catalog:
    def __init__(self, capabilities):
        self.capabilities = tuple(capabilities)

    def list_offered(self):
        return self.capabilities


class Resolver:
    def __init__(self, plan):
        self.plan = plan
        self.calls = []

    def resolve(self, *, text, context, capabilities):
        self.calls.append((text, context, tuple(capabilities)))
        return self.plan


class Builder:
    def __init__(self, result=None):
        self.result = result or ConversationIntent(
            capability_name="endpoint.device.search",
            arguments={"hostname": "AOT-50107", "requested_facts": ["who is logged in"]},
        )
        self.calls = []

    def build(self, *, text, context, plan, capabilities):
        self.calls.append((text, context, plan, tuple(capabilities)))
        return self.result


class Observer:
    def __init__(self, updated):
        self.updated = updated
        self.calls = []

    def observe(self, *, context, response_text, provenance):
        self.calls.append((context, response_text, provenance))
        return self.updated


def principal():
    return BoundConversationPrincipal(
        principal_id="person-al",
        organization_id="aot",
    )


def identity(message_id="m1"):
    return TeamsConversationPrincipalEvidence(
        microsoft_tenant_id="tenant",
        microsoft_object_id="object",
        authentication_assurance="mfa",
        conversation_id="conv-1",
        message_id=message_id,
    )


def test_dynamic_coordinator_keys_context_to_authenticated_teams_conversation():
    plan = DynamicConversationPlan(
        outcome="plan",
        requirements=(
            DynamicCapabilityRequirement(
                capability_id="endpoint.device.search",
                purpose="read the requested endpoint information",
            ),
        ),
        topic="endpoint investigation",
    )
    store = MemoryStore()
    resolver = Resolver(plan)
    builder = Builder()
    coordinator = DynamicTeamsConversationCoordinator(
        context_store=store,
        capability_catalog=Catalog(()),
        resolver=resolver,
        intent_builder=builder,
    )

    result = coordinator.resolve_turn(
        text="Who is logged into AOT-50107?",
        principal=principal(),
        identity=identity(),
    )

    assert isinstance(result, ConversationIntent)
    saved = store.get(
        organization_id="aot",
        principal_id="person-al",
        conversation_id="conv-1",
    )
    assert saved is not None
    assert saved.active_topic == "endpoint investigation"
    assert resolver.calls[0][1].conversation_id == "conv-1"


def test_dynamic_clarification_never_builds_or_executes_an_intent():
    plan = DynamicConversationPlan(
        outcome="clarify",
        clarification_question="Which workstation do you mean?",
    )
    builder = Builder()
    coordinator = DynamicTeamsConversationCoordinator(
        context_store=MemoryStore(),
        capability_catalog=Catalog(()),
        resolver=Resolver(plan),
        intent_builder=builder,
    )

    try:
        coordinator.resolve_turn(
            text="Check it.",
            principal=principal(),
            identity=identity(),
        )
    except ConversationGuidanceRequiredError as error:
        assert error.guidance_text == "Which workstation do you mean?"
    else:
        raise AssertionError("clarification must stop before governed intent construction")

    assert builder.calls == []


def test_governed_continuation_selector_is_available_to_next_turn_without_observer():
    continuation = ContinuationStore(
        SimpleNamespace(
            response_kind="result",
            resource_selector={"resource_label": "NODE-77"},
            last_message_id="previous-message",
        )
    )
    resolver = Resolver(
        DynamicConversationPlan(
            outcome="conversation",
            conversation_response="I can check that. Which system should I use?",
        )
    )
    coordinator = DynamicTeamsConversationCoordinator(
        context_store=MemoryStore(),
        capability_catalog=Catalog(()),
        resolver=resolver,
        intent_builder=Builder(),
        observer=None,
        continuation_store=continuation,
    )

    try:
        coordinator.resolve_turn(
            text="Check it again.",
            principal=principal(),
            identity=identity("next-message"),
        )
    except ConversationGuidanceRequiredError as error:
        assert error.reason_code == "dynamic_conversation_response"
        assert error.guidance_text == "I can check that. Which system should I use?"
    else:
        raise AssertionError("conversation-only turn must return its bounded response")
    context = resolver.calls[0][1]
    assert len(context.entities) == 1
    entity = context.entities[0]
    assert entity.kind == "selector.resource_label"
    assert entity.canonical_id == "NODE-77"
    assert entity.display_name == "NODE-77"
    assert context.active_entity_refs[entity.kind] == entity.ref
    assert "previous-message" in entity.provenance


def test_verified_response_observation_remains_available_as_optional_compatibility_path():
    store = MemoryStore()
    initial = DynamicConversationContext(
        conversation_id="conv-1",
        principal_id="person-al",
        organization_id="aot",
    )
    store.put(initial)
    updated = DynamicConversationContext(
        conversation_id="conv-1",
        principal_id="person-al",
        organization_id="aot",
        entities=(),
        active_topic="identity investigation",
    )
    observer = Observer(updated)
    coordinator = DynamicTeamsConversationCoordinator(
        context_store=store,
        capability_catalog=Catalog(()),
        resolver=Resolver(DynamicConversationPlan(outcome="conversation")),
        intent_builder=Builder(),
        observer=observer,
    )

    result = coordinator.observe_verified_response(
        principal=principal(),
        identity=identity("m2"),
        response_text="NODE-77 is online.",
    )

    assert result.active_topic == "identity investigation"
    assert store.get(
        organization_id="aot",
        principal_id="person-al",
        conversation_id="conv-1",
    ) is result
    assert observer.calls[0][2] == "verified Jason Teams response:m2"


def test_context_isolated_between_two_teams_conversations_for_same_person():
    store = MemoryStore()
    one = DynamicConversationContext(
        conversation_id="conv-1",
        principal_id="person-al",
        organization_id="aot",
        active_topic="endpoint one",
    )
    two = DynamicConversationContext(
        conversation_id="conv-2",
        principal_id="person-al",
        organization_id="aot",
        active_topic="endpoint two",
    )
    store.put(one)
    store.put(two)

    assert store.get(
        organization_id="aot",
        principal_id="person-al",
        conversation_id="conv-1",
    ).active_topic == "endpoint one"
    assert store.get(
        organization_id="aot",
        principal_id="person-al",
        conversation_id="conv-2",
    ).active_topic == "endpoint two"
