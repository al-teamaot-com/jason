from datetime import datetime, timezone
import json

import pytest

from connectors.datto_rmm.capability_manifest import (
    build_datto_rmm_manifest,
)
from kernel.capabilities import (
    CapabilityRegistryService,
    InMemoryCapabilityRegistry,
)
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
)
from orchestrator.integration_broker import (
    IntegrationBroker,
    broker_model_context,
    broker_operation_targets,
    resolve_operation_ref,
)
from orchestrator.investigation_decision import (
    InvestigationDecisionEngine,
    InvestigationDecisionKind,
)
from orchestrator.resource_capability_catalog import (
    register_endpoint_resource_foundation,
)


class FakeClient:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def complete(
        self,
        *,
        system,
        user,
        schema,
        max_output_tokens=160,
    ):
        self.calls.append(
            {
                "system": system,
                "user": user,
                "schema": schema,
                "max_output_tokens": max_output_tokens,
            }
        )
        return dict(self.result)


def build_broker():
    capabilities = CapabilityRegistryService(
        registry=InMemoryCapabilityRegistry()
    )
    providers = ExecutionProviderRegistryService(
        registry=InMemoryExecutionProviderRegistry()
    )

    register_endpoint_resource_foundation(
        capabilities=capabilities,
        providers=providers,
        now=datetime.now(timezone.utc),
    )

    broker = IntegrationBroker(
        capabilities=capabilities,
        providers=providers,
    )

    broker.register(
        build_datto_rmm_manifest()
    )

    return broker


def endpoint_operation_ref(broker, operation_kind):
    context = broker_model_context(broker)

    endpoint = next(
        resource
        for resource in context["resources"]
        if resource["resource_type"] == "endpoint"
    )

    return next(
        operation["operation_ref"]
        for operation in endpoint["operations"]
        if operation["kind"] == operation_kind
    )


def test_inspection_selects_compiled_current_operation_reference():
    broker = build_broker()

    operation_ref = endpoint_operation_ref(
        broker,
        "search",
    )

    client = FakeClient(
        {
            "decision": "inspect",
            "operation_ref": operation_ref,
            "information_goal": (
                "Establish which managed endpoint the technician means."
            ),
        }
    )

    engine = InvestigationDecisionEngine(
        client=client
    )

    decision = engine.decide(
        human_text=(
            "A technician reports an unfamiliar workstation "
            "named LAB-WEST-17 and wants to know what we know about it."
        ),
        broker=broker,
    )

    assert decision.kind is InvestigationDecisionKind.INSPECT
    assert decision.operation_ref == operation_ref

    target = resolve_operation_ref(
        broker,
        decision.operation_ref,
    )

    assert target.resource.resource_type == "endpoint"
    assert target.operation.kind.value == "search"


def test_model_cannot_select_internal_provider_or_capability_identifier():
    broker = build_broker()

    operation_ref = endpoint_operation_ref(
        broker,
        "search",
    )

    client = FakeClient(
        {
            "decision": "inspect",
            "operation_ref": operation_ref,
            "information_goal": "Establish the matching endpoint.",
        }
    )

    InvestigationDecisionEngine(
        client=client
    ).decide(
        human_text="Find workstation LAB-WEST-17.",
        broker=broker,
    )

    payload = json.loads(
        client.calls[0]["user"]
    )

    serialized = json.dumps(
        payload,
        sort_keys=True,
    )

    assert "datto_rmm" not in serialized
    assert "capability_name" not in serialized
    assert "endpoint.device.search" not in serialized


def test_unknown_operation_reference_fails_deterministically():
    broker = build_broker()

    client = FakeClient(
        {
            "decision": "inspect",
            "operation_ref": "operation_not_real",
            "information_goal": "Inspect something.",
        }
    )

    with pytest.raises(
        ValueError,
    ):
        InvestigationDecisionEngine(
            client=client
        ).decide(
            human_text="Inspect this workstation.",
            broker=broker,
        )


def test_answer_decision_cannot_smuggle_an_operation():
    broker = build_broker()

    operation_ref = endpoint_operation_ref(
        broker,
        "search",
    )

    client = FakeClient(
        {
            "decision": "answer",
            "operation_ref": operation_ref,
            "information_goal": None,
        }
    )

    with pytest.raises(
        ValueError,
        match="non-inspect",
    ):
        InvestigationDecisionEngine(
            client=client
        ).decide(
            human_text="What did we establish?",
            broker=broker,
            evidence=(
                {
                    "statement": "Verified endpoint evidence exists.",
                },
            ),
        )


def test_answer_decision_requires_no_execution_target():
    broker = build_broker()

    client = FakeClient(
        {
            "decision": "answer",
            "operation_ref": None,
            "information_goal": None,
        }
    )

    decision = InvestigationDecisionEngine(
        client=client
    ).decide(
        human_text="What did we establish?",
        broker=broker,
        evidence=(
            {
                "statement": "Verified evidence already answers the request.",
            },
        ),
    )

    assert decision.kind is InvestigationDecisionKind.ANSWER
    assert decision.operation_ref is None


def test_cannot_establish_requires_no_execution_target():
    broker = build_broker()

    client = FakeClient(
        {
            "decision": "cannot_establish",
            "operation_ref": None,
            "information_goal": None,
        }
    )

    decision = InvestigationDecisionEngine(
        client=client
    ).decide(
        human_text=(
            "Tell me something unavailable from the currently "
            "connected operational resources."
        ),
        broker=broker,
    )

    assert (
        decision.kind
        is InvestigationDecisionKind.CANNOT_ESTABLISH
    )


def test_every_model_operation_ref_is_a_complete_runtime_binding():
    broker = build_broker()

    context = broker_model_context(broker)

    refs = {
        operation["operation_ref"]
        for resource in context["resources"]
        for operation in resource["operations"]
    }

    assert refs

    for operation_ref in refs:
        target = resolve_operation_ref(
            broker,
            operation_ref,
        )

        assert target.integration.operational is True
        assert target.resource.resource_type
        assert target.operation.capability_name
        assert target.operation.operation_id


def test_schema_bounds_operation_refs_to_current_broker_catalog():
    broker = build_broker()

    operation_ref = endpoint_operation_ref(
        broker,
        "search",
    )

    client = FakeClient(
        {
            "decision": "inspect",
            "operation_ref": operation_ref,
            "information_goal": "Resolve the endpoint.",
        }
    )

    InvestigationDecisionEngine(
        client=client
    ).decide(
        human_text="Locate LAB-WEST-17.",
        broker=broker,
    )

    schema = client.calls[0]["schema"]

    ref_branches = (
        schema["properties"]["operation_ref"]["anyOf"]
    )

    enum_values = next(
        branch["enum"]
        for branch in ref_branches
        if "enum" in branch
    )

    from orchestrator.investigation_decision import (
        _eligible_operation_targets,
    )

    eligible_refs = {
        target.operation_ref
        for target in _eligible_operation_targets(
            broker=broker,
            context=None,
        )
    }

    assert set(enum_values) == eligible_refs

    # The decision schema must remain bounded to the broker catalog even when
    # current grounding feasibility hides some registered operations.
    runtime_refs = {
        target.operation_ref
        for target in broker_operation_targets(broker)
    }

    assert set(enum_values) <= runtime_refs


def test_verified_identity_only_operation_is_hidden_without_verified_context():
    from orchestrator.dynamic_conversation_kernel import DynamicConversationContext
    from orchestrator.investigation_decision import InvestigationDecisionEngine

    broker = build_broker()
    client = FakeClient(
        {
            "decision": "cannot_establish",
            "operation_ref": None,
            "information_goal": None,
        }
    )

    InvestigationDecisionEngine(client=client).decide(
        human_text="Inspect the relevant resource.",
        broker=broker,
        context=DynamicConversationContext(
            conversation_id="conv-no-identity",
            principal_id="person-1",
            organization_id="aot",
        ),
    )

    schema = client.calls[0]["schema"]
    user = __import__("json").loads(client.calls[0]["user"])

    allowed = set()

    operation_schema = schema["properties"]["operation_ref"]

    for branch in operation_schema.get("anyOf", ()):
        allowed.update(branch.get("enum", ()))

    visible = {
        operation["operation_ref"]
        for resource in user["available_resources"]
        for operation in resource.get("operations", ())
    }

    assert visible == allowed


def test_decision_context_parameter_preserves_existing_behavior():
    from orchestrator.dynamic_conversation_kernel import DynamicConversationContext
    from orchestrator.investigation_decision import InvestigationDecisionEngine

    broker = build_broker()

    allowed_ref = next(
        target.operation_ref
        for target in broker_operation_targets(broker)
        if (
            target.operation.collection_supported
            or not target.operation.selector_names
            or any(
                not selector.verified_identity_required
                for selector in target.resource.selectors
                if selector.name in target.operation.selector_names
            )
        )
    )

    client = FakeClient(
        {
            "decision": "inspect",
            "operation_ref": allowed_ref,
            "information_goal": "Establish the requested information.",
        }
    )

    decision = InvestigationDecisionEngine(
        client=client
    ).decide(
        human_text="Find the relevant resource.",
        broker=broker,
        context=DynamicConversationContext(
            conversation_id="conv-search-first",
            principal_id="person-1",
            organization_id="aot",
        ),
    )

    assert decision.operation_ref == allowed_ref
