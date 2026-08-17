from __future__ import annotations

from types import SimpleNamespace

import pytest

from orchestrator.conversation_answer import ConversationAnswer
from orchestrator.conversation_experience import ConversationExperienceResolution
from orchestrator.conversation_kernel import (
    ConversationKernelDecision,
    InformationNeed,
    InformationTarget,
    ReasoningAttempt,
)
from orchestrator.contracts import (
    ExecutionStage,
    OrchestrationResult,
    OrchestrationStatus,
)
from orchestrator.dynamic_conversation_kernel import DynamicConversationContext
from orchestrator.information_fulfillment import FulfillmentCapability, FulfillmentStep
from orchestrator.information_need_intent import PlannedInformationNeed
from orchestrator.teams_conversation_experience import TeamsConversationExperienceFlow
from orchestrator.teams_conversation_flow import (
    BoundConversationPrincipal,
    ConversationIntent,
    TeamsConversationPrincipalEvidence,
    TeamsConversationRequest,
)


class FakeIdentityBinder:
    def __init__(self, principal):
        self.principal = principal
        self.calls = []

    def bind(self, evidence):
        self.calls.append(evidence)
        return self.principal


class FakeContextStore:
    def __init__(self, existing=None):
        self.existing = existing
        self.puts = []

    def get(self, **kwargs):
        return self.existing

    def put(self, context):
        self.puts.append(context)
        self.existing = context
        return context


class FakeCatalog:
    def list_available(self):
        return ()


class FakeExperience:
    def __init__(self, resolution):
        self.resolution = resolution
        self.catalog = FakeCatalog()
        self.calls = []

    def resolve(self, *, text, context):
        self.calls.append((text, context))
        return self.resolution


class FakeRequestFactory:
    def __init__(self, *, changed_principal=None):
        self.changed_principal = changed_principal
        self.builds = []

    def new_correlation_id(self):
        return "corr-turn"

    def build(self, *, principal, intent, identity, correlation_id):
        self.builds.append(
            {
                "principal": principal,
                "intent": intent,
                "identity": identity,
                "correlation_id": correlation_id,
            }
        )
        return SimpleNamespace(
            execution_id=f"exec-{len(self.builds)}",
            correlation_id=correlation_id,
            principal_id=self.changed_principal or principal.principal_id,
            organization_id=principal.organization_id,
            client_id=principal.client_id,
            capability_name=intent.capability_name,
            requested_mode=intent.execution_mode,
            permission_mode=intent.permission_mode,
            requester_kind="human",
        )


class FakeOrchestrator:
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
            reason_codes=("test",),
            resolution=None,
            output={"provider": "provider-one", "data": {"value": "Example"}},
            attempts=1,
            provider_id="provider-one",
        )


class FakeProgressiveReads:
    def __init__(self, *, execute_twice=False):
        self.execute_twice = execute_twice
        self.calls = []

    def fulfill(self, *, question, resolution, executor):
        self.calls.append((question, resolution))
        primary = (
            resolution.intent.intents[0]
            if hasattr(resolution.intent, "intents")
            else resolution.intent
        )
        executor.execute(primary)
        if self.execute_twice:
            executor.execute(
                ConversationIntent(
                    capability_name="endpoint.specialized.search",
                    arguments={"name": "NODE-77", "requested_facts": [question]},
                    permission_mode="observe",
                    risk="low",
                )
            )
        return ConversationAnswer(
            text="Here is the natural governed answer.",
            support_ids=("support-1",),
        )


class FakeTextQuality:
    def __init__(self):
        self.calls = []

    def finalize(self, **kwargs):
        self.calls.append(kwargs)
        return kwargs["candidate"].strip()


class FakeTransport:
    def __init__(self):
        self.sends = []

    def send(self, *, conversation_id, text, correlation_id):
        self.sends.append((conversation_id, text, correlation_id))
        return "teams-message-1"


def principal():
    return BoundConversationPrincipal(
        principal_id="person-al",
        organization_id="aot",
    )


def identity():
    return TeamsConversationPrincipalEvidence(
        microsoft_tenant_id="tenant-1",
        microsoft_object_id="object-1",
        authentication_assurance="verified",
        conversation_id="conversation-1",
        message_id="message-1",
    )


def info_resolution():
    target = InformationTarget(
        kind="endpoint",
        source="literal",
        reference="NODE-77",
    )
    need = InformationNeed(
        target=target,
        need="requested endpoint information",
        authority="observe",
    )
    cap = FulfillmentCapability(
        capability_name="endpoint.device.search",
        resource_types=("endpoint",),
        operation="search",
        selector_keys=("name",),
        role="primary",
        permission_mode="observe",
        risk="low",
        description="general endpoint read",
    )
    planned = PlannedInformationNeed(
        need=need,
        step=FulfillmentStep(
            capability_name=cap.capability_name,
            target_reference=target.reference,
            target_source=target.source,
            information_need=need.need,
            authority=need.authority,
        ),
        capability=cap,
    )
    return ConversationExperienceResolution(
        decision=ConversationKernelDecision(
            outcome="information",
            information_needs=(need,),
            topic="endpoint question",
        ),
        context=DynamicConversationContext(
            conversation_id="conversation-1",
            principal_id="person-al",
            organization_id="aot",
            active_topic="endpoint question",
        ),
        reasoning_attempts=(
            ReasoningAttempt(
                backend="conversation-model",
                attempt=1,
                outcome="accepted",
            ),
        ),
        planned_information=(planned,),
        intent=ConversationIntent(
            capability_name=cap.capability_name,
            arguments={
                "name": "NODE-77",
                "requested_facts": ["human question"],
            },
            permission_mode="observe",
            risk="low",
        ),
    )


def non_info_resolution(kind):
    if kind == "clarify":
        decision = ConversationKernelDecision(
            outcome="clarify",
            clarification_question="Which customer environment do you mean?",
            topic="customer environment",
        )
    else:
        decision = ConversationKernelDecision(
            outcome="conversation",
            conversational_response="You're welcome.",
            topic="general conversation",
        )
    return ConversationExperienceResolution(
        decision=decision,
        context=DynamicConversationContext(
            conversation_id="conversation-1",
            principal_id="person-al",
            organization_id="aot",
            active_topic=decision.topic,
        ),
        reasoning_attempts=(),
    )


def make_flow(
    resolution,
    *,
    binder_principal=None,
    request_factory=None,
    progressive=None,
):
    binder = FakeIdentityBinder(
        principal() if binder_principal is None else binder_principal
    )
    store = FakeContextStore()
    experience = FakeExperience(resolution)
    factory = request_factory or FakeRequestFactory()
    orchestrator = FakeOrchestrator()
    reads = progressive or FakeProgressiveReads()
    quality = FakeTextQuality()
    transport = FakeTransport()
    flow = TeamsConversationExperienceFlow(
        identity_binder=binder,
        context_store=store,
        experience=experience,
        progressive_reads=reads,
        request_factory=factory,
        orchestrator=orchestrator,
        text_quality=quality,
        transport=transport,
    )
    return flow, store, factory, orchestrator, reads, quality, transport


def test_information_turn_crosses_orchestrator_and_sends_exactly_one_final_teams_message():
    flow, store, factory, orchestrator, reads, quality, transport = make_flow(
        info_resolution()
    )

    result = flow.handle(
        TeamsConversationRequest(
            text="Tell me about NODE-77.",
            identity=identity(),
        )
    )

    assert len(orchestrator.requests) == 1
    assert len(transport.sends) == 1
    assert transport.sends[0][1] == "Here is the natural governed answer."
    assert result.response_text == "Here is the natural governed answer."
    assert result.correlation_id == "corr-turn"
    assert len(result.orchestrations) == 1
    assert quality.calls == []
    assert store.puts


def test_progressive_backend_reads_share_one_turn_correlation_identity():
    progressive = FakeProgressiveReads(execute_twice=True)
    flow, _, factory, orchestrator, _, _, transport = make_flow(
        info_resolution(),
        progressive=progressive,
    )

    result = flow.handle(
        TeamsConversationRequest(
            text="Tell me about NODE-77.",
            identity=identity(),
        )
    )

    assert len(orchestrator.requests) == 2
    assert {item["correlation_id"] for item in factory.builds} == {"corr-turn"}
    assert {item.correlation_id for item in result.orchestrations} == {"corr-turn"}
    assert len(transport.sends) == 1


def test_clarification_is_quality_gated_and_never_executes_a_provider():
    flow, _, _, orchestrator, reads, quality, transport = make_flow(
        non_info_resolution("clarify")
    )

    result = flow.handle(
        TeamsConversationRequest(
            text="Check that customer.",
            identity=identity(),
        )
    )

    assert orchestrator.requests == []
    assert reads.calls == []
    assert quality.calls[0]["kind"] == "clarification"
    assert len(transport.sends) == 1
    assert result.response_text == "Which customer environment do you mean?"


def test_conversation_only_turn_is_quality_gated_without_orchestration():
    flow, _, _, orchestrator, reads, quality, transport = make_flow(
        non_info_resolution("conversation")
    )

    result = flow.handle(
        TeamsConversationRequest(text="Thanks.", identity=identity())
    )

    assert orchestrator.requests == []
    assert reads.calls == []
    assert quality.calls[0]["kind"] == "conversation"
    assert len(transport.sends) == 1
    assert result.response_text == "You're welcome."


def test_unbound_identity_stops_before_conversation_reasoning_or_transport():
    resolution = non_info_resolution("conversation")
    flow, _, _, orchestrator, reads, quality, transport = make_flow(
        resolution,
        binder_principal=False,
    )
    # Fake binder returns False, which is not None; construct an explicit binder for
    # the actual unbound contract instead.
    flow = TeamsConversationExperienceFlow(
        identity_binder=FakeIdentityBinder(None),
        context_store=FakeContextStore(),
        experience=FakeExperience(resolution),
        progressive_reads=reads,
        request_factory=FakeRequestFactory(),
        orchestrator=orchestrator,
        text_quality=quality,
        transport=transport,
    )

    with pytest.raises(PermissionError, match="identity is not bound"):
        flow.handle(TeamsConversationRequest(text="Thanks.", identity=identity()))

    assert orchestrator.requests == []
    assert transport.sends == []


def test_request_factory_cannot_change_bound_principal_before_orchestrator():
    bad_factory = FakeRequestFactory(changed_principal="someone-else")
    flow, _, _, orchestrator, _, _, transport = make_flow(
        info_resolution(),
        request_factory=bad_factory,
    )

    with pytest.raises(PermissionError, match="bound Teams principal"):
        flow.handle(
            TeamsConversationRequest(
                text="Tell me about NODE-77.",
                identity=identity(),
            )
        )

    assert orchestrator.requests == []
    assert transport.sends == []
