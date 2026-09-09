from __future__ import annotations

from types import SimpleNamespace

import pytest

from kernel.capabilities import CapabilityLifecycle
from orchestrator.conversation_experience import (
    ConversationActionFulfillmentRequired,
    ConversationExperienceCoordinator,
)
from orchestrator.conversation_kernel import (
    ConversationKernelDecision,
    InformationNeed,
    InformationTarget,
    ReasoningAttempt,
    ReasoningBackend,
    ValidatedReasoningPool,
)
from orchestrator.dynamic_conversation_kernel import DynamicConversationContext
from orchestrator.information_fulfillment import (
    GovernedInitialFulfillmentPlanner,
    RegistryBackedFulfillmentCatalog,
)
from orchestrator.information_need_intent import InformationNeedIntentBuilder
from orchestrator.teams_conversation_flow import ConversationIntent


class FixedKernel:
    def __init__(self, decision):
        self.decision = decision
        self.calls = []

    def interpret(self, *, text, context):
        self.calls.append((text, context))
        return self.decision, (
            ReasoningAttempt(
                backend="test-model",
                attempt=1,
                outcome="accepted",
            ),
        )


class FakeBindingClient:
    def __init__(self, argument="hostname"):
        self.argument = argument
        self.calls = []

    def complete(self, *, system, user, schema, max_output_tokens=160):
        self.calls.append((system, user, schema, max_output_tokens))
        return {"argument": self.argument}


class FakeRegistry:
    def __init__(self, items):
        self.items = tuple(items)

    def list_all(self):
        return self.items


def capability(
    name,
    *,
    resource_types,
    operation,
    selector_keys,
    role,
):
    return SimpleNamespace(
        capability_name=name,
        lifecycle_status=CapabilityLifecycle.ACTIVE,
        metadata={
            "provider_neutral": "true",
            "read_only": "true",
            "resource_types": resource_types,
            "operation": operation,
            "selector_keys": selector_keys,
            "resource_role": role,
            # Deliberately misleading legacy semantic data. It must be irrelevant.
            "fact_hints": "totally unrelated semantic phrase",
            "canonical_facts": "legacy fact",
        },
        risk_level=SimpleNamespace(value="low"),
        display_name=name,
        business_purpose="generic governed resource operation",
    )


def context():
    return DynamicConversationContext(
        conversation_id="conv-1",
        principal_id="person-al",
        organization_id="aot",
    )


def information_decision(*needs):
    return ConversationKernelDecision(
        outcome="information",
        information_needs=tuple(needs),
        topic="resource question",
    )


def endpoint_need(
    description="arbitrary endpoint information",
    *,
    authority="observe",
):
    return InformationNeed(
        target=InformationTarget(
            kind="endpoint",
            source="literal",
            reference="NODE-77",
        ),
        need=description,
        authority=authority,
    )


def coordinator(decision, *, registry_items=None, binding_argument="hostname"):
    items = registry_items or (
        capability(
            "endpoint.device.search",
            resource_types="endpoint",
            operation="search",
            selector_keys="hostname,name,resource_id",
            role="primary",
        ),
        capability(
            "endpoint.device.read",
            resource_types="endpoint",
            operation="read",
            selector_keys="resource_id",
            role="primary",
        ),
        capability(
            "endpoint.alert.history.search",
            resource_types="endpoint_alert,alert,endpoint",
            operation="search",
            selector_keys="hostname,name,resource_id",
            role="specialized",
        ),
    )
    catalog = RegistryBackedFulfillmentCatalog(registry=FakeRegistry(items))
    binding_client = FakeBindingClient(binding_argument)
    reasoning = ValidatedReasoningPool(
        backends=(ReasoningBackend(name="binding-model", client=binding_client),)
    )
    return (
        ConversationExperienceCoordinator(
            kernel=FixedKernel(decision),
            fulfillment=GovernedInitialFulfillmentPlanner(catalog=catalog),
            catalog=catalog,
            intent_builder=InformationNeedIntentBuilder(reasoning=reasoning),
        ),
        binding_client,
    )


def test_information_turn_selects_one_primary_backend_resource_not_specialized_fanout():
    service, _ = coordinator(information_decision(endpoint_need()))

    resolved = service.resolve(
        text="Tell me the arbitrary endpoint information for NODE-77.",
        context=context(),
    )

    assert isinstance(resolved.intent, ConversationIntent)
    assert resolved.intent.capability_name == "endpoint.device.search"
    assert len(resolved.planned_information) == 1
    assert resolved.context.active_topic == "resource question"


def test_multiple_needs_for_same_target_coalesce_into_one_primary_read_intent():
    service, binding = coordinator(
        information_decision(
            endpoint_need("first independent information need"),
            endpoint_need("second independent information need"),
        )
    )

    resolved = service.resolve(
        text="Give me two independent facts about NODE-77.",
        context=context(),
    )

    assert isinstance(resolved.intent, ConversationIntent)
    assert resolved.intent.capability_name == "endpoint.device.search"
    assert len(resolved.planned_information) == 2
    assert len(binding.calls) == 1


def test_clarification_stops_before_fulfillment_or_execution_state_exists():
    decision = ConversationKernelDecision(
        outcome="clarify",
        clarification_question="Which customer environment do you mean?",
        topic="customer environment",
    )
    service, binding = coordinator(decision)

    resolved = service.resolve(text="Check that one.", context=context())

    assert resolved.decision.outcome == "clarify"
    assert resolved.intent is None
    assert resolved.planned_information == ()
    assert binding.calls == []


def test_conversation_only_turn_stays_non_executable():
    decision = ConversationKernelDecision(
        outcome="conversation",
        conversational_response="I can help with that.",
        topic="general conversation",
    )
    service, binding = coordinator(decision)

    resolved = service.resolve(text="Thanks.", context=context())

    assert resolved.decision.outcome == "conversation"
    assert resolved.intent is None
    assert binding.calls == []


def test_non_observe_need_never_leaks_into_read_fulfillment_path():
    service, binding = coordinator(
        information_decision(endpoint_need(authority="execute"))
    )

    with pytest.raises(
        ConversationActionFulfillmentRequired,
        match="governed action fulfillment",
    ):
        service.resolve(text="Change NODE-77.", context=context())

    assert binding.calls == []


def test_unrelated_future_resource_uses_same_structural_fulfillment_rule():
    future_items = (
        capability(
            "printer.asset.search",
            resource_types="printer",
            operation="search",
            selector_keys="name",
            role="primary",
        ),
        capability(
            "printer.supplies.search",
            resource_types="printer_supply,printer",
            operation="search",
            selector_keys="name",
            role="specialized",
        ),
    )
    future_need = InformationNeed(
        target=InformationTarget(
            kind="printer",
            source="literal",
            reference="PRINT-12",
        ),
        need="arbitrary printer information",
        authority="observe",
    )
    service, binding = coordinator(
        information_decision(future_need),
        registry_items=future_items,
    )

    resolved = service.resolve(
        text="Tell me something about PRINT-12.",
        context=context(),
    )

    assert isinstance(resolved.intent, ConversationIntent)
    assert resolved.intent.capability_name == "printer.asset.search"
    assert resolved.intent.arguments["name"] == "PRINT-12"
    assert binding.calls == []
