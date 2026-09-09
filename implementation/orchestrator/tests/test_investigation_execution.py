from dataclasses import dataclass
from datetime import datetime, timezone

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
from orchestrator.dynamic_conversation_intent import (
    GroundedConversationIntentBuilder,
)
from orchestrator.dynamic_conversation_kernel import (
    ConversationEntity,
    DynamicConversationContext,
)
from orchestrator.integration_broker import (
    IntegrationBroker,
    broker_model_context,
)
from orchestrator.investigation_decision import (
    InvestigationDecision,
    InvestigationDecisionKind,
)
from orchestrator.investigation_execution import (
    GovernedInvestigationExecutor,
    InvestigationEvidenceWorkspace,
    InvestigationExecutionError,
)
from orchestrator.resource_capability_catalog import (
    register_endpoint_resource_foundation,
)


class BindingClient:
    def __init__(self, result):
        self.result = result

    def complete(self, **kwargs):
        return self.result


@dataclass
class Result:
    status: str = "succeeded"
    provider_id: str = "datto_rmm"
    capability_name: str = "endpoint.device.search"
    execution_id: str = "exec-1"
    correlation_id: str = "corr-1"
    output: dict | None = None

    def __post_init__(self):
        if self.output is None:
            self.output = {
                "provider": "datto_rmm",
                "data": {
                    "resource_matches": [
                        {
                            "resource_id": "durable-77",
                            "hostname": "LAB-WEST-17",
                        }
                    ],
                    "resolved_resource_id": "durable-77",
                    "provider_data": {
                        "operatingSystem": "Windows",
                    },
                },
                "evidence_ids": ("ev-1",),
                "warnings": (),
            }


class Executor:
    def __init__(self, result=None):
        self.result = result or Result()
        self.intents = []

    def execute(self, intent):
        self.intents.append(intent)
        return self.result


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


def operation_ref(broker, *, resource_type, kind):
    context = broker_model_context(broker)

    resource = next(
        item
        for item in context["resources"]
        if item["resource_type"] == resource_type
    )

    return next(
        item["operation_ref"]
        for item in resource["operations"]
        if item["kind"] == kind
    )


def test_literal_selector_executes_existing_governed_capability():
    broker = build_broker()

    selected = operation_ref(
        broker,
        resource_type="endpoint",
        kind="search",
    )

    bridge = GovernedInvestigationExecutor(
        broker=broker,
        grounding=GroundedConversationIntentBuilder(
            client=BindingClient(
                {
                    "bindings": [
                        {
                            "argument": "hostname",
                            "source_type": "literal",
                            "source_id": None,
                            "literal": "LAB-WEST-17",
                        }
                    ]
                }
            )
        ),
    )

    executor = Executor()
    workspace = InvestigationEvidenceWorkspace()

    evidence = bridge.execute(
        decision=InvestigationDecision(
            kind=InvestigationDecisionKind.INSPECT,
            operation_ref=selected,
            information_goal="Identify the managed endpoint.",
        ),
        human_text="Tell me about LAB-WEST-17",
        context=DynamicConversationContext(
            conversation_id="conv-1",
            principal_id="person-1",
            organization_id="aot",
        ),
        executor=executor,
        workspace=workspace,
    )

    assert len(executor.intents) == 1

    intent = executor.intents[0]

    assert intent.capability_name == "endpoint.device.search"
    assert intent.permission_mode == "observe"
    assert intent.arguments["hostname"] == "LAB-WEST-17"

    assert evidence.data["resolved_resource_id"] == "durable-77"
    assert workspace.entries() == (evidence,)


def test_verified_identity_can_drive_exact_read_without_model_inventing_id():
    broker = build_broker()

    context = broker_model_context(broker)

    endpoint = next(
        item
        for item in context["resources"]
        if item["resource_type"] == "endpoint"
    )

    selected = next(
        item["operation_ref"]
        for item in endpoint["operations"]
        if (
            item["kind"] == "read"
            and item["selector_names"] == ["resource_id"]
        )
    )

    verified = ConversationEntity(
        ref="entity-endpoint-1",
        kind="endpoint",
        canonical_id="durable-77",
        display_name="LAB-WEST-17",
        provenance="verified provider evidence",
    )

    bridge = GovernedInvestigationExecutor(
        broker=broker,
        grounding=GroundedConversationIntentBuilder(
            client=BindingClient(
                {
                    "bindings": [
                        {
                            "argument": "resource_id",
                            "source_type": "entity",
                            "source_id": (
                                "entity-endpoint-1:canonical_id"
                            ),
                            "literal": None,
                        }
                    ]
                }
            )
        ),
    )

    executor = Executor(
        Result(
            capability_name="endpoint.device.read",
        )
    )

    workspace = InvestigationEvidenceWorkspace()

    bridge.execute(
        decision=InvestigationDecision(
            kind=InvestigationDecisionKind.INSPECT,
            operation_ref=selected,
            information_goal="Inspect the verified endpoint record.",
        ),
        human_text="What else can you tell me about it?",
        context=DynamicConversationContext(
            conversation_id="conv-1",
            principal_id="person-1",
            organization_id="aot",
            entities=(verified,),
            active_entity_refs={
                "endpoint": "entity-endpoint-1",
            },
        ),
        executor=executor,
        workspace=workspace,
    )

    assert executor.intents[0].capability_name == "endpoint.device.read"
    assert executor.intents[0].arguments["resource_id"] == "durable-77"


def test_selector_only_operation_fails_closed_without_grounding():
    broker = build_broker()

    selected = operation_ref(
        broker,
        resource_type="endpoint",
        kind="read",
    )

    bridge = GovernedInvestigationExecutor(
        broker=broker,
        grounding=GroundedConversationIntentBuilder(
            client=BindingClient(
                {
                    "bindings": [],
                }
            )
        ),
    )

    with pytest.raises(
        InvestigationExecutionError,
        match="grounded selector|no grounded selector",
    ):
        bridge.execute(
            decision=InvestigationDecision(
                kind=InvestigationDecisionKind.INSPECT,
                operation_ref=selected,
                information_goal="Read a specific endpoint.",
            ),
            human_text="Tell me about it",
            context=DynamicConversationContext(
                conversation_id="conv-1",
                principal_id="person-1",
                organization_id="aot",
            ),
            executor=Executor(),
            workspace=InvestigationEvidenceWorkspace(),
        )


def test_workspace_model_view_hides_provider_and_capability_routing():
    broker = build_broker()

    selected = operation_ref(
        broker,
        resource_type="endpoint",
        kind="search",
    )

    bridge = GovernedInvestigationExecutor(
        broker=broker,
        grounding=GroundedConversationIntentBuilder(
            client=BindingClient(
                {
                    "bindings": [
                        {
                            "argument": "hostname",
                            "source_type": "literal",
                            "source_id": None,
                            "literal": "LAB-WEST-17",
                        }
                    ]
                }
            )
        ),
    )

    workspace = InvestigationEvidenceWorkspace()

    bridge.execute(
        decision=InvestigationDecision(
            kind=InvestigationDecisionKind.INSPECT,
            operation_ref=selected,
            information_goal="Identify the endpoint.",
        ),
        human_text="Inspect LAB-WEST-17",
        context=DynamicConversationContext(
            conversation_id="conv-1",
            principal_id="person-1",
            organization_id="aot",
        ),
        executor=Executor(),
        workspace=workspace,
    )

    rendered = repr(
        workspace.model_evidence()
    )

    assert "datto_rmm" not in rendered
    assert "endpoint.device.search" not in rendered
    assert "provider_id" not in rendered
    assert "capability_name" not in rendered


def test_result_provider_mismatch_fails_closed():
    broker = build_broker()

    selected = operation_ref(
        broker,
        resource_type="endpoint",
        kind="search",
    )

    bridge = GovernedInvestigationExecutor(
        broker=broker,
        grounding=GroundedConversationIntentBuilder(
            client=BindingClient(
                {
                    "bindings": [
                        {
                            "argument": "hostname",
                            "source_type": "literal",
                            "source_id": None,
                            "literal": "LAB-WEST-17",
                        }
                    ]
                }
            )
        ),
    )

    with pytest.raises(
        InvestigationExecutionError,
        match="provider",
    ):
        bridge.execute(
            decision=InvestigationDecision(
                kind=InvestigationDecisionKind.INSPECT,
                operation_ref=selected,
                information_goal="Identify endpoint.",
            ),
            human_text="Inspect LAB-WEST-17",
            context=DynamicConversationContext(
                conversation_id="conv-1",
                principal_id="person-1",
                organization_id="aot",
            ),
            executor=Executor(
                Result(
                    provider_id="wrong-provider",
                )
            ),
            workspace=InvestigationEvidenceWorkspace(),
        )


def test_unrelated_grounded_argument_cannot_satisfy_selector_requirement():
    broker = build_broker()

    selected = operation_ref(
        broker,
        resource_type="endpoint",
        kind="read",
    )

    bridge = GovernedInvestigationExecutor(
        broker=broker,
        grounding=GroundedConversationIntentBuilder(
            client=BindingClient(
                {
                    "bindings": [
                        {
                            "argument": "not_a_selector",
                            "source_type": "literal",
                            "source_id": None,
                            "literal": "LAB-WEST-17",
                        }
                    ]
                }
            )
        ),
    )

    executor = Executor()

    with pytest.raises(
        (
            InvestigationExecutionError,
            Exception,
        ),
    ):
        bridge.execute(
            decision=InvestigationDecision(
                kind=InvestigationDecisionKind.INSPECT,
                operation_ref=selected,
                information_goal="Read a specific endpoint.",
            ),
            human_text="Inspect LAB-WEST-17",
            context=DynamicConversationContext(
                conversation_id="conv-1",
                principal_id="person-1",
                organization_id="aot",
            ),
            executor=executor,
            workspace=InvestigationEvidenceWorkspace(),
        )

    assert executor.intents == []


def test_real_enum_style_status_is_accepted():
    from enum import Enum

    class Status(str, Enum):
        SUCCEEDED = "succeeded"

    broker = build_broker()

    selected = operation_ref(
        broker,
        resource_type="endpoint",
        kind="search",
    )

    bridge = GovernedInvestigationExecutor(
        broker=broker,
        grounding=GroundedConversationIntentBuilder(
            client=BindingClient(
                {
                    "bindings": [
                        {
                            "argument": "hostname",
                            "source_type": "literal",
                            "source_id": None,
                            "literal": "LAB-WEST-17",
                        }
                    ]
                }
            )
        ),
    )

    result = Result()
    result.status = Status.SUCCEEDED

    evidence = bridge.execute(
        decision=InvestigationDecision(
            kind=InvestigationDecisionKind.INSPECT,
            operation_ref=selected,
            information_goal="Inspect endpoint.",
        ),
        human_text="Inspect LAB-WEST-17",
        context=DynamicConversationContext(
            conversation_id="conv-enum",
            principal_id="person-1",
            organization_id="aot",
        ),
        executor=Executor(result=result),
        workspace=InvestigationEvidenceWorkspace(),
    )

    assert evidence.execution_id == "exec-1"


def test_investigation_model_view_bounds_large_provider_collection():
    from orchestrator.investigation_execution import (
        InvestigationEvidence,
    )

    evidence = InvestigationEvidence(
        operation_ref="operation-test",
        resource_type="endpoint",
        information_goal="resolve endpoint",
        execution_id="exec-test",
        correlation_id="corr-test",
        provider_id="example",
        capability_name="endpoint.device.search",
        data={
            "resolved_resource_id": "device-77",
            "resource_matches": [
                {
                    "resource_id": "device-77",
                    "hostname": "LAB-WEST-17",
                }
            ],
            "provider_data": {
                "pages": [
                    {
                        "devices": [
                            {
                                "uid": f"device-{index}",
                                "hostname": f"DEVICE-{index}",
                                "description": "x" * 2000,
                            }
                            for index in range(500)
                        ]
                    }
                    for _ in range(10)
                ]
            },
        },
    )

    view = evidence.model_view()

    import json

    rendered = json.dumps(
        view,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    assert len(rendered) < 60000

    # Deterministic identity evidence remains available to reasoning.
    assert (
        view["data"]["resolved_resource_id"]
        == "device-77"
    )

    assert (
        view["data"]["resource_matches"][0][
            "resource_id"
        ]
        == "device-77"
    )

    # The giant provider collection is bounded rather than copied wholesale.
    assert len(
        view["data"]["provider_data"]["pages"]
    ) < 10


def test_investigation_model_view_redacts_before_bounding():
    from orchestrator.investigation_execution import (
        InvestigationEvidence,
    )

    secret = "this-value-must-never-reach-the-model"

    evidence = InvestigationEvidence(
        operation_ref="operation-test",
        resource_type="endpoint",
        information_goal="inspect endpoint",
        execution_id="exec-test",
        correlation_id="corr-test",
        provider_id="example",
        capability_name="endpoint.device.read",
        data={
            "api_token": secret,
            "nested": {
                "name": "client_secret",
                "value": secret,
            },
        },
    )

    import json

    rendered = json.dumps(
        evidence.model_view(),
        ensure_ascii=False,
    )

    assert secret not in rendered
    assert "[REDACTED]" in rendered


def test_investigation_full_evidence_remains_unmodified():
    from orchestrator.investigation_execution import (
        InvestigationEvidence,
    )

    original = {
        "provider_data": {
            "records": [
                {
                    "value": index,
                }
                for index in range(100)
            ]
        }
    }

    evidence = InvestigationEvidence(
        operation_ref="operation-test",
        resource_type="endpoint",
        information_goal="inspect endpoint",
        execution_id="exec-test",
        correlation_id="corr-test",
        provider_id="example",
        capability_name="endpoint.device.read",
        data=original,
    )

    evidence.model_view()

    assert len(
        evidence.data["provider_data"]["records"]
    ) == 100
