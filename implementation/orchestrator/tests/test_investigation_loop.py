from dataclasses import dataclass
from datetime import datetime, timezone
import json

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
from orchestrator.contracts import OrchestrationStatus
from orchestrator.dynamic_conversation_kernel import (
    DynamicConversationContext,
)
from orchestrator.integration_broker import (
    IntegrationBroker,
    broker_model_context,
)
from orchestrator.investigation_decision import (
    InvestigationDecisionEngine,
)
from orchestrator.investigation_execution import (
    GovernedInvestigationExecutor,
)
from orchestrator.investigation_loop import (
    BoundedInvestigationLoop,
    InvestigationLoopStatus,
)
from orchestrator.resource_capability_catalog import (
    register_endpoint_resource_foundation,
)


class SequencedDecisionClient:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return self.results.pop(0)


class BindingClient:
    def complete(self, **kwargs):
        payload = json.loads(
            kwargs["user"]
        )

        text = payload.get(
            "human_text",
            payload.get("text", ""),
        )

        return {
            "bindings": [
                {
                    "argument": "hostname",
                    "source_type": "literal",
                    "source_id": None,
                    "literal": "LAB-WEST-17",
                }
            ]
        }


@dataclass
class Result:
    status: OrchestrationStatus = OrchestrationStatus.SUCCEEDED
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
                "evidence_ids": ("evidence-1",),
                "warnings": (),
            }


class Executor:
    def __init__(self):
        self.intents = []

    def execute(self, intent):
        self.intents.append(intent)
        return Result(
            capability_name=(
                intent.capability_name
            )
        )


def broker():
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

    item = IntegrationBroker(
        capabilities=capabilities,
        providers=providers,
    )

    item.register(
        build_datto_rmm_manifest()
    )

    return item


def endpoint_search_ref(item):
    context = broker_model_context(item)

    endpoint = next(
        resource
        for resource in context["resources"]
        if resource["resource_type"] == "endpoint"
    )

    return next(
        operation["operation_ref"]
        for operation in endpoint["operations"]
        if (
            operation["kind"] == "search"
            and "hostname"
            in operation["selector_names"]
        )
    )


def test_loop_reads_then_stops_when_evidence_is_sufficient():
    item = broker()

    operation_ref = endpoint_search_ref(
        item
    )

    decision_client = SequencedDecisionClient(
        [
            {
                "decision": "inspect",
                "operation_ref": operation_ref,
                "information_goal": (
                    "Establish the endpoint record."
                ),
            },
            {
                "decision": "answer",
                "operation_ref": None,
                "information_goal": None,
            },
        ]
    )

    executor = Executor()

    loop = BoundedInvestigationLoop(
        decisions=InvestigationDecisionEngine(
            client=decision_client
        ),
        execution=GovernedInvestigationExecutor(
            broker=item,
            grounding=GroundedConversationIntentBuilder(
                client=BindingClient()
            ),
        ),
        maximum_reads=4,
    )

    result = loop.run(
        human_text=(
            "What can you tell me about LAB-WEST-17?"
        ),
        context=DynamicConversationContext(
            conversation_id="conversation-1",
            principal_id="person-1",
            organization_id="aot",
        ),
        executor=executor,
    )

    assert result.status is InvestigationLoopStatus.ANSWER
    assert result.steps == 1
    assert len(executor.intents) == 1
    assert len(result.workspace.entries()) == 1

    second_payload = json.loads(
        decision_client.calls[1]["user"]
    )

    evidence = (
        second_payload[
            "established_evidence"
        ]
    )

    assert evidence
    assert (
        evidence[0]["data"][
            "resolved_resource_id"
        ]
        == "durable-77"
    )


def test_loop_stops_without_execution_when_unavailable():
    item = broker()

    client = SequencedDecisionClient(
        [
            {
                "decision": "cannot_establish",
                "operation_ref": None,
                "information_goal": None,
            }
        ]
    )

    executor = Executor()

    result = BoundedInvestigationLoop(
        decisions=InvestigationDecisionEngine(
            client=client
        ),
        execution=GovernedInvestigationExecutor(
            broker=item,
            grounding=GroundedConversationIntentBuilder(
                client=BindingClient()
            ),
        ),
    ).run(
        human_text=(
            "Establish information not observable "
            "through current integrations."
        ),
        context=DynamicConversationContext(
            conversation_id="conversation-1",
            principal_id="person-1",
            organization_id="aot",
        ),
        executor=executor,
    )

    assert (
        result.status
        is InvestigationLoopStatus.CANNOT_ESTABLISH
    )
    assert executor.intents == []


def test_loop_has_hard_provider_read_limit():
    item = broker()

    operation_ref = endpoint_search_ref(
        item
    )

    client = SequencedDecisionClient(
        [
            {
                "decision": "inspect",
                "operation_ref": operation_ref,
                "information_goal": "Inspect endpoint.",
            },
            {
                "decision": "inspect",
                "operation_ref": operation_ref,
                "information_goal": "Inspect again.",
            },
        ]
    )

    executor = Executor()

    result = BoundedInvestigationLoop(
        decisions=InvestigationDecisionEngine(
            client=client
        ),
        execution=GovernedInvestigationExecutor(
            broker=item,
            grounding=GroundedConversationIntentBuilder(
                client=BindingClient()
            ),
        ),
        maximum_reads=1,
    ).run(
        human_text="Inspect LAB-WEST-17",
        context=DynamicConversationContext(
            conversation_id="conversation-1",
            principal_id="person-1",
            organization_id="aot",
        ),
        executor=executor,
    )

    assert result.status is InvestigationLoopStatus.EXHAUSTED
    assert len(executor.intents) == 1


def test_sensitive_provider_evidence_is_redacted_before_next_model_decision():
    item = broker()

    operation_ref = endpoint_search_ref(
        item
    )

    client = SequencedDecisionClient(
        [
            {
                "decision": "inspect",
                "operation_ref": operation_ref,
                "information_goal": "Inspect endpoint.",
            },
            {
                "decision": "answer",
                "operation_ref": None,
                "information_goal": None,
            },
        ]
    )

    class SensitiveExecutor:
        def execute(self, intent):
            return Result(
                capability_name=intent.capability_name,
                output={
                    "provider": "datto_rmm",
                    "data": {
                        "hostname": "LAB-WEST-17",
                        "password": "do-not-send",
                        "variables": [
                            {
                                "name": "api_token",
                                "value": "also-do-not-send",
                            },
                            {
                                "name": "office",
                                "value": "Norfolk",
                            },
                        ],
                    },
                    "evidence_ids": (),
                    "warnings": (),
                },
            )

    BoundedInvestigationLoop(
        decisions=InvestigationDecisionEngine(
            client=client
        ),
        execution=GovernedInvestigationExecutor(
            broker=item,
            grounding=GroundedConversationIntentBuilder(
                client=BindingClient()
            ),
        ),
    ).run(
        human_text="Inspect LAB-WEST-17",
        context=DynamicConversationContext(
            conversation_id="conversation-1",
            principal_id="person-1",
            organization_id="aot",
        ),
        executor=SensitiveExecutor(),
    )

    payload = client.calls[1]["user"]

    assert "do-not-send" not in payload
    assert "also-do-not-send" not in payload
    assert "[REDACTED]" in payload
    assert "Norfolk" in payload


def test_investigation_search_promotes_verified_identity_for_next_decision():
    item = broker()

    model_context = broker_model_context(item)

    endpoint = next(
        resource
        for resource in model_context["resources"]
        if resource["resource_type"] == "endpoint"
    )

    search_ref = next(
        operation["operation_ref"]
        for operation in endpoint["operations"]
        if operation["kind"] == "search"
        and "hostname" in operation["selector_names"]
    )

    read_ref = next(
        operation["operation_ref"]
        for operation in endpoint["operations"]
        if operation["kind"] == "read"
        and "resource_id" in operation["selector_names"]
    )

    class ContextAwareDecisionClient:
        def __init__(self):
            self.calls = []

        def complete(
            self,
            *,
            system,
            user,
            schema,
            max_output_tokens=160,
        ):
            import json

            self.calls.append(
                {
                    "system": system,
                    "user": user,
                    "schema": schema,
                }
            )

            operation_schema = (
                schema["properties"]["operation_ref"]
            )

            allowed = []

            for branch in operation_schema.get(
                "anyOf",
                (),
            ):
                if not isinstance(branch, dict):
                    continue

                allowed.extend(
                    branch.get(
                        "enum",
                        (),
                    )
                )

            if len(self.calls) == 1:
                assert search_ref in allowed
                assert read_ref not in allowed

                return {
                    "decision": "inspect",
                    "operation_ref": search_ref,
                    "information_goal": (
                        "resolve the named managed endpoint"
                    ),
                }

            if len(self.calls) == 2:
                assert read_ref in allowed

                return {
                    "decision": "answer",
                    "operation_ref": None,
                    "information_goal": None,
                }

            raise AssertionError(
                "unexpected extra decision"
            )

    decision_client = ContextAwareDecisionClient()
    executor = Executor()

    loop = BoundedInvestigationLoop(
        decisions=InvestigationDecisionEngine(
            client=decision_client,
        ),
        execution=GovernedInvestigationExecutor(
            broker=item,
            grounding=GroundedConversationIntentBuilder(
                client=BindingClient(),
            ),
        ),
        maximum_reads=4,
    )

    result = loop.run(
        human_text="Tell me about LAB-WEST-17",
        context=DynamicConversationContext(
            conversation_id="conversation-identity-test",
            principal_id="person-1",
            organization_id="aot",
        ),
        executor=executor,
    )

    assert result.status is InvestigationLoopStatus.ANSWER
    assert result.steps == 1

    assert (
        "endpoint"
        in result.context.active_entity_refs
    )

    entity = result.context.entity(
        result.context.active_entity_refs[
            "endpoint"
        ]
    )

    assert entity.canonical_id == "durable-77"
    assert entity.display_name == "LAB-WEST-17"
    assert (
        result.context.recent_resolutions[-1]
        .entity_ref
        == entity.ref
    )
