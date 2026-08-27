from __future__ import annotations

from orchestrator.conversation_kernel import (
    InformationNeed,
    InformationTarget,
    ReasoningBackend,
    ValidatedReasoningPool,
)
from orchestrator.information_fulfillment import (
    FulfillmentCapability,
    FulfillmentStep,
)
from orchestrator.information_need_intent import (
    InformationNeedIntentBuilder,
    PlannedInformationNeed,
)
from orchestrator.teams_conversation_flow import (
    ConversationIntent,
    ConversationIntentPlan,
)


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


def capability(*, selectors=("hostname", "name")):
    return FulfillmentCapability(
        capability_name="endpoint.device.search",
        resource_types=("endpoint",),
        operation="search",
        selector_keys=selectors,
        role="primary",
        permission_mode="observe",
        risk="low",
        description="Locate one managed endpoint from a grounded discovery selector.",
    )


def planned(
    *,
    reference="NODE-77",
    information_need="arbitrary endpoint state",
    cap=None,
):
    selected = cap or capability()
    need = InformationNeed(
        target=InformationTarget(
            kind="endpoint",
            source="literal",
            reference=reference,
        ),
        need=information_need,
        authority="observe",
    )
    step = FulfillmentStep(
        capability_name=selected.capability_name,
        target_reference=reference,
        target_source="literal",
        information_need=information_need,
        authority="observe",
    )
    return PlannedInformationNeed(
        need=need,
        step=step,
        capability=selected,
    )


def pool(*clients):
    return ValidatedReasoningPool(
        backends=tuple(
            ReasoningBackend(name=f"model-{index}", client=client)
            for index, client in enumerate(clients, start=1)
        )
    )


def test_single_selector_capability_needs_no_model_call():
    client = FakeClient()
    cap = capability(selectors=("resource_id",))
    builder = InformationNeedIntentBuilder(reasoning=pool(client))

    intent = builder.build(
        human_text="Inspect NODE-77.",
        planned=(planned(cap=cap),),
    )

    assert isinstance(intent, ConversationIntent)
    assert intent.capability_name == "endpoint.device.search"
    assert intent.arguments == {
        "resource_id": "NODE-77",
        "requested_facts": ["Inspect NODE-77."],
    }
    assert client.calls == []


def test_multiple_selector_names_use_model_only_for_argument_name_not_target_value():
    client = FakeClient({"argument": "hostname"})
    builder = InformationNeedIntentBuilder(reasoning=pool(client))

    intent = builder.build(
        human_text="Inspect NODE-77.",
        planned=(planned(),),
    )

    assert isinstance(intent, ConversationIntent)
    assert intent.arguments["hostname"] == "NODE-77"
    assert intent.arguments["requested_facts"] == ["Inspect NODE-77."]
    assert len(client.calls) == 1
    call = client.calls[0]
    assert "NODE-77" not in call["user"]
    assert "target_reference" not in call["user"]
    assert set(call["schema"]["properties"]["argument"]["enum"]) == {
        "hostname",
        "name",
    }


def test_invalid_selector_name_is_rejected_and_next_backend_can_repair():
    bad = FakeClient({"argument": "provider_id"})
    good = FakeClient({"argument": "name"})
    builder = InformationNeedIntentBuilder(reasoning=pool(bad, good))

    intent = builder.build(
        human_text="Inspect NODE-77.",
        planned=(planned(),),
    )

    assert intent.arguments["name"] == "NODE-77"
    assert len(bad.calls) == 1
    assert len(good.calls) == 1


def test_same_target_and_capability_are_coalesced_into_one_governed_read():
    client = FakeClient({"argument": "hostname"})
    builder = InformationNeedIntentBuilder(reasoning=pool(client))

    intent = builder.build(
        human_text="Give me the owner and current state of NODE-77.",
        planned=(
            planned(information_need="resource owner"),
            planned(information_need="current resource state"),
        ),
    )

    assert isinstance(intent, ConversationIntent)
    assert intent.arguments["hostname"] == "NODE-77"
    assert len(client.calls) == 1


def test_independent_targets_remain_independent_governed_intents():
    client = FakeClient(
        {"argument": "hostname"},
        {"argument": "hostname"},
    )
    builder = InformationNeedIntentBuilder(reasoning=pool(client))

    intent = builder.build(
        human_text="Compare NODE-77 and NODE-88.",
        planned=(
            planned(reference="NODE-77"),
            planned(reference="NODE-88"),
        ),
    )

    assert isinstance(intent, ConversationIntentPlan)
    assert [item.arguments["hostname"] for item in intent.intents] == [
        "NODE-77",
        "NODE-88",
    ]


def test_model_cannot_change_selected_capability_or_grounded_target_value():
    client = FakeClient({"argument": "hostname"})
    builder = InformationNeedIntentBuilder(reasoning=pool(client))
    item = planned(reference="NODE-77")

    intent = builder.build(
        human_text="Inspect NODE-77.",
        planned=(item,),
    )

    assert intent.capability_name == item.capability.capability_name
    assert intent.arguments["hostname"] == item.need.target.reference


def test_literal_target_cannot_be_bound_to_unverified_resource_id():
    client = FakeClient({"argument": "name"})
    cap = capability(
        selectors=("hostname", "name", "resource_id")
    )
    builder = InformationNeedIntentBuilder(
        reasoning=pool(client)
    )

    intent = builder.build(
        human_text="Inspect NODE-77.",
        planned=(planned(cap=cap),),
    )

    assert intent.arguments["name"] == "NODE-77"
    assert "resource_id" not in intent.arguments

    call = client.calls[0]
    assert set(
        call["schema"]["properties"]["argument"]["enum"]
    ) == {
        "hostname",
        "name",
    }


def test_verified_entity_prefers_resource_id_without_model_call():
    client = FakeClient()
    cap = capability(
        selectors=("hostname", "name", "resource_id")
    )

    item = planned(
        reference="durable-resource-77",
        cap=cap,
    )

    verified_need = InformationNeed(
        target=InformationTarget(
            kind="endpoint",
            source="verified_entity",
            reference="durable-resource-77",
        ),
        need=item.need.need,
        authority="observe",
    )

    verified_step = FulfillmentStep(
        capability_name=cap.capability_name,
        target_reference="durable-resource-77",
        target_source="verified_entity",
        information_need=item.need.need,
        authority="observe",
    )

    verified = PlannedInformationNeed(
        need=verified_need,
        step=verified_step,
        capability=cap,
    )

    builder = InformationNeedIntentBuilder(
        reasoning=pool(client)
    )

    intent = builder.build(
        human_text="Inspect this verified endpoint.",
        planned=(verified,),
    )

    assert intent.arguments["resource_id"] == (
        "durable-resource-77"
    )

    assert client.calls == []
