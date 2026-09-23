from decimal import Decimal

from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from orchestrator.contracts import (
    ExecutionStage,
    OrchestrationMode,
    OrchestrationRequest,
    OrchestrationResult,
    OrchestrationStatus,
)
from orchestrator.teams_conversation_flow import (
    BoundConversationPrincipal,
    ConversationIntent,
    TeamsConversationPrincipalEvidence,
    TeamsConversationRequest,
)
from orchestrator.dynamic_teams_flow_bridge import DynamicTeamsFlowBridge


class Binder:
    def bind(self, evidence):
        return BoundConversationPrincipal(
            principal_id="person-al",
            organization_id="aot",
            client_id=None,
        )


class Coordinator:
    def __init__(self):
        self.resolve_calls = []
        self.observed = []

    def resolve_turn(self, *, text, principal, identity):
        self.resolve_calls.append((text, principal, identity))
        return ConversationIntent(
            capability_name="endpoint.device.search",
            arguments={"resource_label": "NODE-77", "requested_facts": [text]},
            permission_mode="observe",
            risk="low",
        )

    def observe_verified_response(self, *, principal, identity, response_text):
        self.observed.append((principal, identity, response_text))


class Factory:
    def new_correlation_id(self):
        return "corr-1"

    def build(self, *, principal, intent, identity, correlation_id):
        return OrchestrationRequest(
            execution_id="exec-1",
            correlation_id=correlation_id,
            principal_id=principal.principal_id,
            organization_id=principal.organization_id,
            client_id=principal.client_id,
            capability_name=intent.capability_name,
            capability_version=None,
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
            policy_ids=("teams-conversation-v1",),
        )


class Orchestrator:
    def __init__(self):
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return OrchestrationResult(
            execution_id=request.execution_id,
            correlation_id=request.correlation_id,
            capability_name=request.capability_name,
            status=OrchestrationStatus.SUCCEEDED,
            stage=ExecutionStage.COMPLETED,
            reason_codes=("capability_completed",),
            resolution=None,
            output={"provider": "synthetic", "data": {"resource_label": "NODE-77"}},
            attempts=1,
            provider_id="synthetic",
        )


class Renderer:
    def render(self, result, intent):
        return "NODE-77 is online. Source: synthetic."


class Transport:
    def __init__(self):
        self.sent = []

    def send(self, *, conversation_id, text, correlation_id):
        self.sent.append((conversation_id, text, correlation_id))
        return "teams-msg-2"


def identity():
    return TeamsConversationPrincipalEvidence(
        microsoft_tenant_id="tenant-1",
        microsoft_object_id="object-1",
        authentication_assurance="botframework-authenticated",
        conversation_id="conv-1",
        message_id="teams-msg-1",
    )


def test_dynamic_bridge_preserves_governed_flow_without_post_response_observation():
    coordinator = Coordinator()
    orchestrator = Orchestrator()
    transport = Transport()
    bridge = DynamicTeamsFlowBridge(
        identity_binder=Binder(),
        coordinator=coordinator,
        request_factory=Factory(),
        orchestrator=orchestrator,
        response_renderer=Renderer(),
        transport=transport,
    )

    result = bridge.handle(
        TeamsConversationRequest(
            text="Is NODE-77 online?",
            identity=identity(),
        )
    )

    assert result.transport_message_id == "teams-msg-2"
    assert len(orchestrator.requests) == 1
    assert orchestrator.requests[0].capability_name == "endpoint.device.search"
    assert orchestrator.requests[0].principal_id == "person-al"
    assert orchestrator.requests[0].organization_id == "aot"
    assert transport.sent == [
        ("conv-1", "NODE-77 is online. Source: synthetic.", "corr-1")
    ]
    assert coordinator.observed == []


def test_unknown_identity_fails_before_dynamic_resolution_or_orchestration():
    class UnknownBinder:
        def bind(self, evidence):
            return None

    coordinator = Coordinator()
    orchestrator = Orchestrator()
    bridge = DynamicTeamsFlowBridge(
        identity_binder=UnknownBinder(),
        coordinator=coordinator,
        request_factory=Factory(),
        orchestrator=orchestrator,
        response_renderer=Renderer(),
        transport=Transport(),
    )

    try:
        bridge.handle(TeamsConversationRequest(text="Check it", identity=identity()))
    except PermissionError as error:
        assert "not bound" in str(error)
    else:
        raise AssertionError("unknown identity did not fail closed")

    assert coordinator.resolve_calls == []
    assert orchestrator.requests == []
