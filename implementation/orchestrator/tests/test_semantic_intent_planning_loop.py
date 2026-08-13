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


def test_repeated_identical_context_request_fails_closed_without_burning_budget():
    class RepeatingReasoner:
        def next_turn(self, *, intent, context, history):
            return PlanningTurn(
                status="request_context",
                context_request=PlanningContextRequest(
                    view="system_registry",
                    query={"query": "runtime availability"},
                    purpose="inspect governed system state",
                ),
            )

    class Reader:
        def __init__(self):
            self.calls = 0

        def read(self, *, request, intent):
            self.calls += 1
            return {"view_name": request.view, "items": ({"state": "available"},)}

    reader = Reader()
    outcome = BoundedSemanticIntentPlanningLoop(
        reasoner=RepeatingReasoner(),
        context_reader=reader,
        budget=IntentPlanningBudget(max_iterations=8, max_context_requests=7),
    ).plan(intent={"resource_type": "endpoint", "permission_mode": "observe"})

    assert outcome.status == "knowledge_gap"
    assert outcome.context_requests_used == 1
    assert outcome.iterations_used == 3
    assert reader.calls == 1
    assert tuple(item.status for item in outcome.trace) == (
        "request_context",
        "context_reconciled",
    )
    assert "already-satisfied" in str(outcome.gap_summary)


def test_bootstrap_context_is_supplied_before_first_reasoning_turn():
    class Bootstrapper:
        def requests_for(self, *, intent):
            return (
                PlanningContextRequest(
                    view="semantic_knowledge",
                    query={"query": "processor model"},
                    purpose="establish semantic meaning",
                ),
                PlanningContextRequest(
                    view="capability_registry",
                    query={"query": "endpoint"},
                    purpose="establish relevant capabilities",
                ),
            )

    class Reader:
        def read(self, *, request, intent):
            if request.view == "capability_registry":
                return {
                    "view_name": request.view,
                    "items": ({"capability_name": "endpoint.device.search"},),
                    "capability_names": ("endpoint.device.search",),
                }
            return {
                "view_name": request.view,
                "items": ({"concept_id": "processor.model"},),
            }

    class Reasoner:
        def next_turn(self, *, intent, context, history):
            assert "semantic_knowledge" in context
            assert "capability_registry" in context
            return PlanningTurn(
                status="propose_plan",
                plan=FulfillmentPlanCandidate(
                    steps=(
                        FulfillmentPlanStepCandidate(
                            capability_name="endpoint.device.search",
                            purpose="retrieve governed endpoint evidence",
                            required_facts=("processor model",),
                            expected_evidence=("processor model",),
                        ),
                    ),
                    rationale_summary="Governed semantic and capability context establish a valid read path.",
                ),
            )

    outcome = BoundedSemanticIntentPlanningLoop(
        reasoner=Reasoner(),
        context_reader=Reader(),
        context_bootstrapper=Bootstrapper(),
    ).plan(
        intent={
            "resource_type": "endpoint",
            "requested_facts": ("processor model",),
            "permission_mode": "observe",
        }
    )

    assert outcome.status == "planned"
    assert outcome.iterations_used == 1
    assert outcome.context_requests_used == 0


def test_insufficient_plan_is_returned_to_reasoner_for_revision():
    from orchestrator.semantic_plan_sufficiency import GovernedSemanticPlanSufficiencyValidator

    class Reasoner:
        def __init__(self):
            self.calls = 0

        def next_turn(self, *, intent, context, history):
            self.calls += 1
            if self.calls == 1:
                return PlanningTurn(
                    status="propose_plan",
                    plan=FulfillmentPlanCandidate(
                        steps=(
                            FulfillmentPlanStepCandidate(
                                capability_name="endpoint.device.search",
                                purpose="read endpoint",
                                expected_evidence=("special fact",),
                            ),
                        ),
                        rationale_summary="candidate plan",
                    ),
                )
            assert context["plan_validation"]["sufficient"] is False
            return PlanningTurn(status="declare_gap", gap_summary="no governed capability supports special fact")

    class Reader:
        def read(self, *, request, intent):
            return {
                "view_name": request.view,
                "items": (
                    {
                        "capability_name": "endpoint.device.search",
                        "fact_hints": "hostname,operating system",
                    },
                ),
                "capability_names": ("endpoint.device.search",),
                "authoritative": True,
                "truncated": False,
            }

    class Bootstrapper:
        def requests_for(self, *, intent):
            return (
                PlanningContextRequest(
                    view="capability_registry",
                    query={"query": "endpoint"},
                    purpose="bootstrap governed capabilities",
                ),
            )

    outcome = BoundedSemanticIntentPlanningLoop(
        reasoner=Reasoner(),
        context_reader=Reader(),
        context_bootstrapper=Bootstrapper(),
        plan_validator=GovernedSemanticPlanSufficiencyValidator(),
    ).plan(intent={"requested_facts": ("special fact",), "resource_type": "endpoint"})

    assert outcome.status == "knowledge_gap"
    assert outcome.iterations_used == 2
    assert [entry.status for entry in outcome.trace] == ["plan_rejected", "declare_gap"]


def test_already_satisfied_context_request_is_reconciled_once_before_gap():
    class Reasoner:
        def __init__(self):
            self.calls = 0

        def next_turn(self, *, intent, context, history):
            self.calls += 1
            if self.calls == 1:
                return PlanningTurn(
                    status="request_context",
                    context_request=PlanningContextRequest(
                        view="semantic_knowledge",
                        query={"query": "operating system display version"},
                        purpose="inspect semantic meaning",
                    ),
                )
            assert context["context_request_feedback"]["status"] == "already_satisfied"
            return PlanningTurn(status="declare_gap", gap_summary="no different governed path established")

    class Reader:
        def read(self, *, request, intent):
            return {"view_name": request.view, "items": ({"concept_id": "fact.example"},)}

    class Bootstrapper:
        def requests_for(self, *, intent):
            return (
                PlanningContextRequest(
                    view="semantic_knowledge",
                    query={"query": "operating system display version"},
                    purpose="bootstrap semantic meaning",
                ),
            )

    outcome = BoundedSemanticIntentPlanningLoop(
        reasoner=Reasoner(),
        context_reader=Reader(),
        context_bootstrapper=Bootstrapper(),
        budget=IntentPlanningBudget(max_iterations=4, max_context_requests=2),
    ).plan(intent={"requested_facts": ("operating system display version",)})

    assert outcome.status == "knowledge_gap"
    assert outcome.iterations_used == 2
    assert outcome.context_requests_used == 0
    assert outcome.trace[0].status == "context_reconciled"



def test_infeasible_fulfillment_stops_rejected_plan_retry_loop():
    from orchestrator.semantic_fulfillment_feasibility import GovernedSemanticFulfillmentFeasibilityGate
    from orchestrator.semantic_plan_sufficiency import GovernedSemanticPlanSufficiencyValidator

    class Reasoner:
        def next_turn(self, *, intent, context, history):
            return PlanningTurn(
                status="propose_plan",
                plan=FulfillmentPlanCandidate(
                    steps=(
                        FulfillmentPlanStepCandidate(
                            capability_name="endpoint.device.search",
                            purpose="attempt governed endpoint fact retrieval",
                            expected_evidence=("special fact",),
                        ),
                    ),
                    rationale_summary="candidate plan",
                ),
            )

    class Reader:
        def read(self, *, request, intent):
            if request.view == "capability_registry":
                return {
                    "items": ({"capability_name": "endpoint.device.search", "fact_hints": "hostname"},),
                    "capability_names": ("endpoint.device.search",),
                }
            if request.view == "evidence_catalog":
                return {"items": ({"fact_hints": "operating system"},)}
            if request.view == "derivation_registry":
                return {"items": ({"relationship_id": "endpoint.belongs_to.organization"},)}
            return {"items": ()}

    class Bootstrapper:
        def requests_for(self, *, intent):
            return (
                PlanningContextRequest(view="capability_registry"),
                PlanningContextRequest(view="evidence_catalog"),
                PlanningContextRequest(view="derivation_registry"),
            )

    outcome = BoundedSemanticIntentPlanningLoop(
        reasoner=Reasoner(),
        context_reader=Reader(),
        context_bootstrapper=Bootstrapper(),
        plan_validator=GovernedSemanticPlanSufficiencyValidator(),
        feasibility_gate=GovernedSemanticFulfillmentFeasibilityGate(),
    ).plan(intent={"requested_facts": ("special fact",), "resource_type": "endpoint"})

    assert outcome.status == "knowledge_gap"
    assert outcome.iterations_used == 1
    assert [entry.status for entry in outcome.trace] == ["fulfillment_infeasible"]
    assert "special fact" in str(outcome.gap_summary)



def test_fulfillment_infeasible_outcome_exposes_governed_capability_gap_details():
    from orchestrator.semantic_capability_gap import GovernedSemanticCapabilityGapAssessor
    from orchestrator.semantic_fulfillment_feasibility import GovernedSemanticFulfillmentFeasibilityGate

    class Reasoner:
        def next_turn(self, *, intent, context, history):
            return PlanningTurn(
                status="propose_plan",
                plan=FulfillmentPlanCandidate(
                    steps=(FulfillmentPlanStepCandidate(
                        capability_name="endpoint.device.search",
                        purpose="attempt governed read",
                    ),),
                    rationale_summary="candidate",
                ),
            )

    class Reader:
        def read(self, *, request, intent):
            if request.view == "capability_registry":
                return {
                    "view_name": request.view,
                    "items": ({"capability_name": "endpoint.device.search", "fact_hints": "hostname"},),
                    "capability_names": ("endpoint.device.search",),
                }
            return {"view_name": request.view, "items": ()}

    class Bootstrapper:
        def requests_for(self, *, intent):
            return (
                PlanningContextRequest(view="capability_registry"),
                PlanningContextRequest(view="evidence_catalog"),
                PlanningContextRequest(view="derivation_registry"),
            )

    class Validator:
        def validate(self, *, intent, plan, context):
            class Result:
                sufficient = False
                issues = ("unsupported",)
            return Result()

    outcome = BoundedSemanticIntentPlanningLoop(
        reasoner=Reasoner(),
        context_reader=Reader(),
        context_bootstrapper=Bootstrapper(),
        plan_validator=Validator(),
        feasibility_gate=GovernedSemanticFulfillmentFeasibilityGate(),
        capability_gap_assessor=GovernedSemanticCapabilityGapAssessor(),
    ).plan(intent={"resource_type": "endpoint", "requested_facts": ("special governed fact",)})

    assert outcome.status == "knowledge_gap"
    assert outcome.gap_details is not None
    assert outcome.gap_details["gap_type"] == "capability_registry_gap"
    assert outcome.gap_details["unsupported_facts"] == ("special governed fact",)



def test_fulfillment_infeasible_outcome_exposes_review_only_provider_discovery():
    from dataclasses import dataclass
    from datetime import datetime, timezone

    from kernel.execution_providers import (
        ExecutionProvider,
        ProviderApproval,
        ProviderFeatures,
        ProviderHealth,
        ProviderLifecycle,
        ProviderLimits,
        ProviderStewardship,
        ProviderType,
    )
    from orchestrator.provider_capability_discovery import GovernedProviderCapabilityDiscovery
    from orchestrator.semantic_capability_gap import GovernedSemanticCapabilityGapAssessor
    from orchestrator.semantic_fulfillment_feasibility import GovernedSemanticFulfillmentFeasibilityGate

    class Reasoner:
        def next_turn(self, *, intent, context, history):
            return PlanningTurn(
                status="propose_plan",
                plan=FulfillmentPlanCandidate(
                    steps=(FulfillmentPlanStepCandidate(
                        capability_name="endpoint.device.search",
                        purpose="attempt governed read",
                    ),),
                    rationale_summary="candidate",
                ),
            )

    class Reader:
        def read(self, *, request, intent):
            if request.view == "capability_registry":
                return {
                    "view_name": request.view,
                    "items": ({"capability_name": "endpoint.device.search", "fact_hints": "hostname"},),
                    "capability_names": ("endpoint.device.search",),
                }
            return {"view_name": request.view, "items": ()}

    class Bootstrapper:
        def requests_for(self, *, intent):
            return (
                PlanningContextRequest(view="capability_registry"),
                PlanningContextRequest(view="evidence_catalog"),
                PlanningContextRequest(view="derivation_registry"),
            )

    class Validator:
        def validate(self, *, intent, plan, context):
            @dataclass(frozen=True)
            class Result:
                sufficient: bool = False
                issues: tuple[str, ...] = ("unsupported",)
            return Result()

    now = datetime.now(timezone.utc)
    registered_provider = ExecutionProvider(
        provider_id="example_provider",
        display_name="Example Provider",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
        health_status=ProviderHealth.HEALTHY,
        approval_status=ProviderApproval.APPROVED,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset({"endpoint.device.search"}),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="test",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification="test",
            review_interval_days=90,
            last_reviewed_at=now,
            retirement_criteria=("retire",),
            vendor_change_sources=("Example Provider API documentation",),
        ),
        created_at=now,
        metadata={"resource_authority": "endpoint", "connector_id": "example"},
    )

    outcome = BoundedSemanticIntentPlanningLoop(
        reasoner=Reasoner(),
        context_reader=Reader(),
        context_bootstrapper=Bootstrapper(),
        plan_validator=Validator(),
        feasibility_gate=GovernedSemanticFulfillmentFeasibilityGate(),
        capability_gap_assessor=GovernedSemanticCapabilityGapAssessor(),
        provider_capability_discovery=GovernedProviderCapabilityDiscovery(),
        registered_providers=(registered_provider,),
    ).plan(intent={"resource_type": "endpoint", "requested_facts": ("special governed fact",)})

    assert outcome.status == "knowledge_gap"
    assert outcome.provider_discovery_details is not None
    assert outcome.provider_discovery_details["review_only"] is True
    candidates = outcome.provider_discovery_details["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["provider_id"] == "example_provider"
    assert candidates[0]["vendor_change_sources"] == ("Example Provider API documentation",)
