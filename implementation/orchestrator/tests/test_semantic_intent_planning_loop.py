import pytest

from orchestrator.semantic_intent_planning_loop import (
    BoundedSemanticIntentPlanningLoop,
    FulfillmentPlanCandidate,
    FulfillmentPlanStepCandidate,
    IntentPlanningBudget,
    PlanningContextRequest,
    PlanningTurn,
)


class ContextReader:
    def __init__(self):
        self.calls = []

    def read(self, *, request, intent):
        self.calls.append((request, intent))
        if request.view == "capability_registry":
            return {"capability_names": ["endpoint.device.search", "endpoint.audit.read"]}
        if request.view == "semantic_knowledge":
            return {"concepts": ["operating_system.windows.display_version"]}
        return {}


class SequencedReasoner:
    def __init__(self, turns):
        self.turns = list(turns)
        self.calls = 0

    def next_turn(self, **kwargs):
        turn = self.turns[self.calls]
        self.calls += 1
        return turn


def test_loop_can_inspect_governed_context_then_propose_registered_capability_plan():
    reasoner = SequencedReasoner([
        PlanningTurn(
            status="request_context",
            context_request=PlanningContextRequest(
                view="semantic_knowledge",
                query={"concept": "operating_system.windows.display_version"},
                purpose="understand requested concept",
            ),
        ),
        PlanningTurn(
            status="request_context",
            context_request=PlanningContextRequest(
                view="capability_registry",
                query={"resource_type": "endpoint"},
                purpose="discover governed fulfillment capabilities",
            ),
        ),
        PlanningTurn(
            status="propose_plan",
            plan=FulfillmentPlanCandidate(
                steps=(FulfillmentPlanStepCandidate(
                    capability_name="endpoint.device.search",
                    purpose="acquire governed endpoint evidence",
                    required_facts=("operating system display version",),
                ),),
                rationale_summary="use a registered endpoint read capability",
            ),
        ),
    ])
    outcome = BoundedSemanticIntentPlanningLoop(
        reasoner=reasoner,
        context_reader=ContextReader(),
    ).plan(intent={"resource_type": "endpoint", "requested_facts": ["operating system display version"]})
    assert outcome.status == "planned"
    assert outcome.iterations_used == 3
    assert outcome.context_requests_used == 2
    assert outcome.plan is not None
    assert outcome.plan.steps[0].capability_name == "endpoint.device.search"


def test_loop_rejects_reasoner_capability_not_present_in_governed_registry():
    reasoner = SequencedReasoner([
        PlanningTurn(
            status="request_context",
            context_request=PlanningContextRequest(view="capability_registry"),
        ),
        PlanningTurn(
            status="propose_plan",
            plan=FulfillmentPlanCandidate(
                steps=(FulfillmentPlanStepCandidate(
                    capability_name="invented.provider.direct.call",
                    purpose="bad direct route",
                ),),
                rationale_summary="invalid",
            ),
        ),
    ])
    with pytest.raises(PermissionError, match="outside governed registry"):
        BoundedSemanticIntentPlanningLoop(
            reasoner=reasoner,
            context_reader=ContextReader(),
        ).plan(intent={"resource_type": "endpoint"})


def test_loop_rejects_direct_provider_or_agent_routing_fields():
    with pytest.raises(PermissionError, match="prohibited direct-routing field"):
        BoundedSemanticIntentPlanningLoop(
            reasoner=SequencedReasoner([]),
            context_reader=ContextReader(),
        ).plan(intent={"provider": "datto_rmm"})
    with pytest.raises(PermissionError, match="not governed"):
        PlanningContextRequest(view="direct_agent")


def test_loop_stops_when_context_request_budget_is_exhausted():
    repeated = PlanningTurn(
        status="request_context",
        context_request=PlanningContextRequest(view="semantic_knowledge"),
    )
    outcome = BoundedSemanticIntentPlanningLoop(
        reasoner=SequencedReasoner([repeated, repeated, repeated]),
        context_reader=ContextReader(),
        budget=IntentPlanningBudget(max_iterations=3, max_context_requests=1),
    ).plan(intent={"resource_type": "endpoint"})
    assert outcome.status == "budget_exhausted"
    assert outcome.context_requests_used == 1


def test_loop_can_declare_structured_knowledge_gap_without_inventing_plan():
    outcome = BoundedSemanticIntentPlanningLoop(
        reasoner=SequencedReasoner([
            PlanningTurn(
                status="declare_gap",
                gap_summary="no governed fulfillment path is currently known",
            )
        ]),
        context_reader=ContextReader(),
    ).plan(intent={"resource_type": "invoice", "requested_facts": ["purchase order"]})
    assert outcome.status == "knowledge_gap"
    assert outcome.plan is None
    assert "no governed fulfillment path" in str(outcome.gap_summary)
