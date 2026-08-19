from decimal import Decimal

import pytest

from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from orchestrator.contracts import (
    ExecutionStage,
    OrchestrationMode,
    OrchestrationRequest,
    OrchestrationResult,
    OrchestrationStatus,
)
from orchestrator.conversation_resource_intent import (
    GovernedResourceConversationIntentResolver,
)
from orchestrator.resource_inquiry import (
    ResourceInquiry,
    ResourceInquiryPlan,
    ResourcePlanStep,
)
from orchestrator.teams_conversation_flow import (
    BoundConversationPrincipal,
    ConversationIntent,
    ConversationIntentPlan,
    TeamsConversationFlow,
    TeamsConversationPrincipalEvidence,
    TeamsConversationRequest,
)


class Interpreter:
    def interpret(self, *, text, principal):
        return ResourceInquiry(
            resource_type="endpoint",
            resource_selector={"hostname": "AOT-50282"},
            requested_facts=("last logged in user", "alerts"),
        )


class Planner:
    def plan(self, inquiry):
        return ResourceInquiryPlan(
            steps=(
                ResourcePlanStep(
                    capability_name="endpoint.device.search",
                    arguments={
                        "hostname": "AOT-50282",
                        "requested_facts": ("last logged in user",),
                    },
                ),
                ResourcePlanStep(
                    capability_name="endpoint.alert.search",
                    arguments={
                        "hostname": "AOT-50282",
                        "requested_facts": ("alerts",),
                    },
                ),
            ),
            requested_facts=inquiry.requested_facts,
        )


def principal():
    return BoundConversationPrincipal(
        principal_id="person-al",
        organization_id="aot",
        client_id=None,
    )


def identity():
    return TeamsConversationPrincipalEvidence(
        microsoft_tenant_id="tenant-1",
        microsoft_object_id="object-1",
        authentication_assurance="botframework-authenticated",
        conversation_id="conversation-1",
        message_id="message-1",
    )


def test_resource_resolver_returns_bounded_multi_step_read_plan():
    resolved = GovernedResourceConversationIntentResolver(
        interpreter=Interpreter(),
        planner=Planner(),
    ).resolve(
        text="Who is logged into AOT-50282 and what alerts does it have?",
        principal=principal(),
    )

    assert isinstance(resolved, ConversationIntentPlan)
    assert [intent.capability_name for intent in resolved.intents] == [
        "endpoint.device.search",
        "endpoint.alert.search",
    ]
    assert resolved.intents[0].arguments["requested_facts"] == (
        "last logged in user",
    )
    assert resolved.intents[1].arguments["requested_facts"] == ("alerts",)
    assert all(intent.permission_mode == "observe" for intent in resolved.intents)


def test_multi_step_plan_rejects_mutating_authority():
    with pytest.raises(PermissionError, match="read-only"):
        ConversationIntentPlan(
            intents=(
                ConversationIntent(
                    capability_name="endpoint.device.search",
                    permission_mode="observe",
                ),
                ConversationIntent(
                    capability_name="endpoint.device.change",
                    permission_mode="execute",
                ),
            )
        )


class Binder:
    def bind(self, evidence):
        return principal()


class Resolver:
    def resolve(self, *, text, principal):
        return ConversationIntentPlan(
            intents=(
                ConversationIntent(
                    capability_name="endpoint.device.search",
                    arguments={
                        "hostname": "AOT-50282",
                        "requested_facts": ("last logged in user",),
                    },
                ),
                ConversationIntent(
                    capability_name="endpoint.alert.search",
                    arguments={
                        "hostname": "AOT-50282",
                        "requested_facts": ("alerts",),
                    },
                ),
            )
        )


class RequestFactory:
    def __init__(self):
        self.calls = 0

    def new_correlation_id(self):
        return "corr-1"

    def build(
        self,
        *,
        principal,
        intent,
        identity,
        correlation_id,
    ):
        self.calls += 1
        return OrchestrationRequest(
            execution_id=f"exec-{self.calls}",
            correlation_id=correlation_id,
            principal_id=principal.principal_id,
            organization_id=principal.organization_id,
            client_id=principal.client_id,
            capability_name=intent.capability_name,
            capability_version=intent.capability_version,
            requested_mode=intent.execution_mode,
            permission_mode=intent.permission_mode,
            orchestration_mode=OrchestrationMode.EXECUTE,
            authority_allowed=True,
            approval_present=False,
            risk=intent.risk,
            data_handling=DataHandlingPolicy(
                classification="internal",
                hosted_processing_allowed=False,
            ),
            budget=ExecutionBudget(maximum_estimated_cost=Decimal("0")),
            arguments=dict(intent.arguments),
            requester_kind="human",
            policy_ids=("teams-read-policy-v1",),
        )


class Orchestrator:
    def __init__(self):
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        fact = request.arguments["requested_facts"][0]
        output = (
            {"fact": fact, "value": "AOT\\example.user", "provider": "datto_rmm"}
            if fact == "last logged in user"
            else {"fact": fact, "value": ["Disk Space"], "provider": "datto_rmm"}
        )
        return OrchestrationResult(
            execution_id=request.execution_id,
            correlation_id=request.correlation_id,
            capability_name=request.capability_name,
            status=OrchestrationStatus.SUCCEEDED,
            stage=ExecutionStage.COMPLETED,
            reason_codes=("capability_completed",),
            resolution=None,
            output=output,
            attempts=1,
            provider_id="datto_rmm",
        )


class Renderer:
    def render(self, result, intent):
        fact = result.output["fact"]
        return f"{fact}: {result.output['value']} (source: {result.provider_id})"


class Transport:
    def __init__(self):
        self.sent = []

    def send(self, *, conversation_id, text, correlation_id):
        self.sent.append((conversation_id, text, correlation_id))
        return "teams-message-2"


def test_teams_flow_executes_every_read_step_through_central_orchestrator_and_sends_one_answer():
    orchestrator = Orchestrator()
    transport = Transport()
    flow = TeamsConversationFlow(
        identity_binder=Binder(),
        intent_resolver=Resolver(),
        request_factory=RequestFactory(),
        orchestrator=orchestrator,
        response_renderer=Renderer(),
        transport=transport,
    )

    result = flow.handle(
        TeamsConversationRequest(
            text="Who is logged into AOT-50282 and what alerts does it have?",
            identity=identity(),
        )
    )

    assert len(orchestrator.requests) == 2
    assert [request.capability_name for request in orchestrator.requests] == [
        "endpoint.device.search",
        "endpoint.alert.search",
    ]
    assert len(result.orchestrations) == 2
    assert result.orchestration is result.orchestrations[0]
    assert transport.sent == [
        (
            "conversation-1",
            "last logged in user: AOT\\example.user (source: datto_rmm)\n"
            "alerts: ['Disk Space'] (source: datto_rmm)",
            "corr-1",
        )
    ]


def test_multi_step_flow_fails_closed_when_request_factory_splits_correlation_identity():
    class SplitCorrelationFactory(RequestFactory):
        def build(
            self,
            *,
            principal,
            intent,
            identity,
            correlation_id,
        ):
            request = super().build(
                principal=principal,
                intent=intent,
                identity=identity,
                correlation_id=correlation_id,
            )
            return OrchestrationRequest(
                execution_id=request.execution_id,
                correlation_id=f"corr-{self.calls}",
                principal_id=request.principal_id,
                organization_id=request.organization_id,
                client_id=request.client_id,
                capability_name=request.capability_name,
                capability_version=request.capability_version,
                requested_mode=request.requested_mode,
                permission_mode=request.permission_mode,
                orchestration_mode=request.orchestration_mode,
                authority_allowed=request.authority_allowed,
                approval_present=request.approval_present,
                risk=request.risk,
                data_handling=request.data_handling,
                budget=request.budget,
                arguments=request.arguments,
                requester_kind=request.requester_kind,
                policy_ids=request.policy_ids,
            )

    orchestrator = Orchestrator()
    transport = Transport()
    flow = TeamsConversationFlow(
        identity_binder=Binder(),
        intent_resolver=Resolver(),
        request_factory=SplitCorrelationFactory(),
        orchestrator=orchestrator,
        response_renderer=Renderer(),
        transport=transport,
    )

    with pytest.raises(PermissionError, match="turn correlation identity"):
        flow.handle(
            TeamsConversationRequest(
                text="Who is logged into AOT-50282 and what alerts does it have?",
                identity=identity(),
            )
        )

    assert orchestrator.requests == []
    assert transport.sent == []
