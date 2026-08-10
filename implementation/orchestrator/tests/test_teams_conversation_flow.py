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
from orchestrator.teams_conversation_flow import (
    BoundConversationPrincipal,
    ConversationIntent,
    TeamsConversationFlow,
    TeamsConversationPrincipalEvidence,
    TeamsConversationRequest,
)


class Binder:
    def __init__(self, principal):
        self.principal = principal

    def bind(self, evidence):
        return self.principal


class IntentResolver:
    def __init__(self, intent):
        self.intent = intent

    def resolve(self, *, text, principal):
        return self.intent


class RequestFactory:
    def __init__(self, *, mutate_principal=False, mutate_organization=False, requester_kind="human"):
        self.mutate_principal = mutate_principal
        self.mutate_organization = mutate_organization
        self.requester_kind = requester_kind

    def build(self, *, principal, intent, identity):
        return OrchestrationRequest(
            execution_id="exec-1",
            correlation_id="corr-1",
            principal_id="other-principal" if self.mutate_principal else principal.principal_id,
            organization_id="other-org" if self.mutate_organization else principal.organization_id,
            client_id=principal.client_id,
            capability_name=intent.capability_name,
            capability_version=intent.capability_version,
            requested_mode=intent.requested_mode,
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
            requester_kind=self.requester_kind,
            policy_ids=("teams-read-policy-v1",),
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
            output={"hostname": "AOT-50282", "session_state": "available"},
            attempts=1,
            provider_id="datto_rmm",
        )


class Renderer:
    def render(self, result):
        return f"{result.output['hostname']}: {result.output['session_state']}"


class Transport:
    def __init__(self):
        self.sent = []

    def send(self, *, conversation_id, text, correlation_id):
        self.sent.append((conversation_id, text, correlation_id))
        return "teams-message-2"


def identity():
    return TeamsConversationPrincipalEvidence(
        microsoft_tenant_id="tenant-1",
        microsoft_object_id="object-1",
        authentication_assurance="botframework-authenticated",
        conversation_id="conversation-1",
        message_id="teams-message-1",
    )


def principal():
    return BoundConversationPrincipal(
        principal_id="jason-user-1",
        organization_id="aot",
        client_id=None,
    )


def intent():
    return ConversationIntent(
        capability_name="endpoint.session.read",
        arguments={"hostname": "AOT-50282"},
        requested_mode="observe",
        risk="low",
    )


def build_flow(*, bound_principal=None, resolved_intent=None, request_factory=None):
    orchestrator = Orchestrator()
    transport = Transport()
    flow = TeamsConversationFlow(
        identity_binder=Binder(principal() if bound_principal is None else bound_principal),
        intent_resolver=IntentResolver(intent() if resolved_intent is None else resolved_intent),
        request_factory=request_factory or RequestFactory(),
        orchestrator=orchestrator,
        response_renderer=Renderer(),
        transport=transport,
    )
    return flow, orchestrator, transport


def test_routes_authenticated_teams_request_through_named_capability_and_orchestrator():
    flow, orchestrator, transport = build_flow()

    result = flow.handle(TeamsConversationRequest(text="Who is logged into AOT-50282?", identity=identity()))

    assert result.transport_message_id == "teams-message-2"
    assert len(orchestrator.requests) == 1
    request = orchestrator.requests[0]
    assert request.capability_name == "endpoint.session.read"
    assert request.arguments == {"hostname": "AOT-50282"}
    assert request.requester_kind == "human"
    assert transport.sent == [("conversation-1", "AOT-50282: available", "corr-1")]


def test_unknown_teams_identity_fails_before_intent_or_orchestration():
    flow, orchestrator, transport = build_flow(bound_principal=False)
    flow = TeamsConversationFlow(
        identity_binder=Binder(None),
        intent_resolver=IntentResolver(intent()),
        request_factory=RequestFactory(),
        orchestrator=orchestrator,
        response_renderer=Renderer(),
        transport=transport,
    )

    with pytest.raises(PermissionError, match="not bound"):
        flow.handle(TeamsConversationRequest(text="Who is logged into AOT-50282?", identity=identity()))

    assert orchestrator.requests == []
    assert transport.sent == []


def test_unresolved_intent_fails_closed_without_provider_or_transport():
    orchestrator = Orchestrator()
    transport = Transport()
    flow = TeamsConversationFlow(
        identity_binder=Binder(principal()),
        intent_resolver=IntentResolver(None),
        request_factory=RequestFactory(),
        orchestrator=orchestrator,
        response_renderer=Renderer(),
        transport=transport,
    )

    with pytest.raises(LookupError, match="no governed Jason capability intent"):
        flow.handle(TeamsConversationRequest(text="Do something clever", identity=identity()))

    assert orchestrator.requests == []
    assert transport.sent == []


@pytest.mark.parametrize(
    "factory,error",
    [
        (RequestFactory(mutate_principal=True), "principal does not match"),
        (RequestFactory(mutate_organization=True), "organization does not match"),
        (RequestFactory(requester_kind="agent"), "must retain human requester identity"),
    ],
)
def test_request_factory_cannot_change_bound_identity_or_human_requester(factory, error):
    flow, orchestrator, transport = build_flow(request_factory=factory)

    with pytest.raises(PermissionError, match=error):
        flow.handle(TeamsConversationRequest(text="Who is logged into AOT-50282?", identity=identity()))

    assert orchestrator.requests == []
    assert transport.sent == []


def test_intent_rejects_direct_agent_invocation_arguments():
    with pytest.raises(ValueError, match="direct agent invocation is prohibited"):
        ConversationIntent(
            capability_name="endpoint.session.read",
            arguments={"target_agent": "datto-agent"},
        )
