from __future__ import annotations

from dataclasses import dataclass

from orchestrator.planning_context_reader import GovernedPlanningContextReaderAdapter
from orchestrator.planning_context_views import (
    GovernedPlanningContextCatalog,
    StaticPlanningContextProvider,
)
from orchestrator.semantic_intent_planning_loop import (
    BoundedSemanticIntentPlanningLoop,
    FulfillmentPlanCandidate,
    FulfillmentPlanStepCandidate,
    IntentPlanningBudget,
    PlanningContextRequest,
    PlanningTurn,
)


def catalog():
    return GovernedPlanningContextCatalog(
        providers={
            "semantic_knowledge": StaticPlanningContextProvider(
                view_name="semantic_knowledge",
                records=(
                    {"concept_id": "endpoint.hostname", "canonical_label": "endpoint hostname"},
                ),
            ),
            "capabilities": StaticPlanningContextProvider(
                view_name="capabilities",
                records=(
                    {"capability_name": "endpoint.device.search", "resource_type": "endpoint"},
                ),
            ),
        }
    )


def test_adapter_translates_semantic_knowledge_view():
    reader = GovernedPlanningContextReaderAdapter(catalog())
    snapshot = reader.read(
        request=PlanningContextRequest(
            view="semantic_knowledge",
            query={"concept": "endpoint.hostname"},
            purpose="understand requested fact",
        ),
        intent={"requested_facts": ["endpoint hostname"]},
    )
    assert snapshot["view_name"] == "semantic_knowledge"
    assert snapshot["authoritative"] is True
    assert snapshot["items"][0]["concept_id"] == "endpoint.hostname"


def test_adapter_exposes_only_governed_capability_names_for_plan_validation():
    reader = GovernedPlanningContextReaderAdapter(catalog())
    snapshot = reader.read(
        request=PlanningContextRequest(
            view="capability_registry",
            query={"resource_type": "endpoint"},
            purpose="discover governed fulfillment capabilities",
        ),
        intent={"resource_type": "endpoint"},
    )
    assert snapshot["capability_names"] == ("endpoint.device.search",)


@dataclass
class IterativeReasoner:
    turns: int = 0

    def next_turn(self, *, intent, context, history):
        self.turns += 1
        if self.turns == 1:
            return PlanningTurn(
                status="request_context",
                context_request=PlanningContextRequest(
                    view="semantic_knowledge",
                    query={"concept": "endpoint.hostname"},
                    purpose="resolve requested semantic concept",
                ),
            )
        if self.turns == 2:
            return PlanningTurn(
                status="request_context",
                context_request=PlanningContextRequest(
                    view="capability_registry",
                    query={"resource_type": "endpoint"},
                    purpose="discover governed fulfillment capability",
                ),
            )
        return PlanningTurn(
            status="propose_plan",
            plan=FulfillmentPlanCandidate(
                steps=(
                    FulfillmentPlanStepCandidate(
                        capability_name="endpoint.device.search",
                        purpose="retrieve the requested endpoint fact",
                        required_facts=("endpoint hostname",),
                    ),
                ),
                rationale_summary="Use the registered endpoint read capability.",
            ),
        )


def test_bounded_loop_iterates_only_through_governed_catalog_adapter():
    loop = BoundedSemanticIntentPlanningLoop(
        reasoner=IterativeReasoner(),
        context_reader=GovernedPlanningContextReaderAdapter(catalog()),
        budget=IntentPlanningBudget(max_iterations=4, max_context_requests=3),
    )
    outcome = loop.plan(
        intent={
            "resource_type": "endpoint",
            "requested_facts": ("endpoint hostname",),
        }
    )
    assert outcome.status == "planned"
    assert outcome.iterations_used == 3
    assert outcome.context_requests_used == 2
    assert outcome.plan is not None
    assert outcome.plan.steps[0].capability_name == "endpoint.device.search"
