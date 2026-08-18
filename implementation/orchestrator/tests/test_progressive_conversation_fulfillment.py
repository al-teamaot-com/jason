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
    ConversationIntentPlan,
    ConversationRenderDecision,
    TeamsConversationFlow,
    TeamsConversationPrincipalEvidence,
    TeamsConversationRequest,
)


class Binder:
    def bind(self, evidence):
        return BoundConversationPrincipal(
            principal_id="person-1",
            organization_id="org-1",
        )


class Resolver:
    def __init__(self, intents):
        self.intents = intents

    def resolve(self, *, text, principal):
        return ConversationIntentPlan(intents=self.intents)


class Factory:
    def new_correlation_id(self):
        return "corr-progressive"

    def build(self, *, principal, intent, identity, correlation_id):
        return OrchestrationRequest(
            execution_id=f"exec-{intent.capability_name}",
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
            policy_ids=("progressive-test",),
        )


class Orchestrator:
    def __init__(self):
        self.calls = []

    def execute(self, request):
        self.calls.append(request.capability_name)
        return OrchestrationResult(
            execution_id=request.execution_id,
            correlation_id=request.correlation_id,
            capability_name=request.capability_name,
            status=OrchestrationStatus.SUCCEEDED,
            stage=ExecutionStage.COMPLETED,
            reason_codes=("completed",),
            resolution=None,
            output={"provider": "synthetic", "data": {"value": request.capability_name}},
            attempts=1,
            provider_id="synthetic",
        )


class DecisionRenderer:
    def __init__(self, satisfied_by):
        self.satisfied_by = satisfied_by
        self.calls = []

    def render_decision(self, result, intent):
        self.calls.append(intent.capability_name)
        satisfied = intent.capability_name == self.satisfied_by
        return ConversationRenderDecision(
            text=(
                f"answer from {intent.capability_name}"
                if satisfied
                else f"no answer from {intent.capability_name}"
            ),
            satisfies_request=satisfied,
        )

    def render(self, result, intent):
        raise AssertionError("decision-aware flow should use render_decision")


class LegacyRenderer:
    def __init__(self):
        self.calls = []

    def render(self, result, intent):
        self.calls.append(intent.capability_name)
        return f"legacy {intent.capability_name}"


class Transport:
    def __init__(self):
        self.sent = []

    def send(self, *, conversation_id, text, correlation_id):
        self.sent.append(text)
        return "message-2"


def identity():
    return TeamsConversationPrincipalEvidence(
        microsoft_tenant_id="tenant",
        microsoft_object_id="object",
        authentication_assurance="mfa",
        conversation_id="conversation",
        message_id="message-1",
    )


def intents():
    return (
        ConversationIntent(
            capability_name="synthetic.resource.read",
            arguments={"resource_id": "NODE-77", "requested_facts": ("current state",)},
            permission_mode="observe",
        ),
        ConversationIntent(
            capability_name="synthetic.history.search",
            arguments={"resource_id": "NODE-77", "requested_facts": ("current state",)},
            permission_mode="observe",
        ),
    )


def build(renderer):
    orchestrator = Orchestrator()
    transport = Transport()
    flow = TeamsConversationFlow(
        identity_binder=Binder(),
        intent_resolver=Resolver(intents()),
        request_factory=Factory(),
        orchestrator=orchestrator,
        response_renderer=renderer,
        transport=transport,
    )
    return flow, orchestrator, transport


def test_plan_stops_before_later_capability_when_first_evidence_satisfies_request():
    renderer = DecisionRenderer("synthetic.resource.read")
    flow, orchestrator, transport = build(renderer)

    result = flow.handle(
        TeamsConversationRequest(text="What is NODE-77's current state?", identity=identity())
    )

    assert orchestrator.calls == ["synthetic.resource.read"]
    assert renderer.calls == ["synthetic.resource.read"]
    assert len(result.orchestrations) == 1
    assert transport.sent == ["answer from synthetic.resource.read"]


def test_plan_continues_until_later_evidence_satisfies_request_and_hides_failed_probe_text():
    renderer = DecisionRenderer("synthetic.history.search")
    flow, orchestrator, transport = build(renderer)

    result = flow.handle(
        TeamsConversationRequest(text="What is NODE-77's current state?", identity=identity())
    )

    assert orchestrator.calls == ["synthetic.resource.read", "synthetic.history.search"]
    assert renderer.calls == ["synthetic.resource.read", "synthetic.history.search"]
    assert len(result.orchestrations) == 2
    assert transport.sent == ["answer from synthetic.history.search"]


def test_renderer_without_fulfillment_surface_keeps_legacy_execute_all_behavior():
    renderer = LegacyRenderer()
    flow, orchestrator, transport = build(renderer)

    result = flow.handle(
        TeamsConversationRequest(text="What is NODE-77's current state?", identity=identity())
    )

    assert orchestrator.calls == ["synthetic.resource.read", "synthetic.history.search"]
    assert renderer.calls == ["synthetic.resource.read", "synthetic.history.search"]
    assert len(result.orchestrations) == 2
    assert transport.sent == [
        "legacy synthetic.resource.read\nlegacy synthetic.history.search"
    ]
