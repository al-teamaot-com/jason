#!/usr/bin/env bash
set -euo pipefail

cd /home/al/projects/jason

printf '%s\n' '========== START GOVERNED CONTEXT CATALOG TO PLANNING LOOP REPAIR =========='
printf '%s\n' '========== SECTION 1: PRECONDITIONS =========='
printf 'HEAD: '; git rev-parse --short HEAD
git status --short

PY="/home/al/projects/jason/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "ERROR: project Python not found at $PY"
  exit 20
fi

printf '%s\n' '========== SECTION 2: ADD CONTRACT ADAPTER WITHOUT CHANGING PLANNING LOOP =========='
cat > implementation/orchestrator/planning_context_reader.py <<'PY'
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .planning_context_views import (
    GovernedPlanningContextCatalog,
    PlanningContextRequest as CatalogPlanningContextRequest,
)
from .semantic_intent_planning_loop import PlanningContextRequest


_VIEW_NAME_MAP = {
    "semantic_knowledge": "semantic_knowledge",
    "capability_registry": "capabilities",
    "system_registry": "system_state",
    "evidence_catalog": "evidence_catalog",
    "derivation_registry": "derivations",
}


@dataclass(frozen=True, slots=True)
class GovernedPlanningContextReaderAdapter:
    """Adapt the governed context catalog to the planning-loop read contract.

    This adapter has no provider, connector, tool, agent, credential, or execution
    authority. It only translates between two provider-neutral governed contracts.
    """

    catalog: GovernedPlanningContextCatalog
    default_limit: int = 32

    def __post_init__(self) -> None:
        if self.default_limit < 1 or self.default_limit > 128:
            raise ValueError("default planning context limit is invalid")

    def read(
        self,
        *,
        request: PlanningContextRequest,
        intent: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        del intent  # authorization/intent remain owned by the orchestrator contract.

        catalog_view_name = _VIEW_NAME_MAP.get(request.view)
        if catalog_view_name is None:
            raise PermissionError(f"planning context view is not governed: {request.view}")

        query = self._query_text(request.query)
        view = self.catalog.read(
            CatalogPlanningContextRequest(
                view_name=catalog_view_name,
                query=query,
                limit=self.default_limit,
            )
        )

        result: dict[str, Any] = {
            "view_name": request.view,
            "items": tuple(dict(item) for item in view.items),
            "authoritative": bool(view.authoritative),
            "truncated": bool(view.truncated),
        }
        if request.view == "capability_registry":
            result["capability_names"] = tuple(
                str(item.get("capability_name", "")).strip()
                for item in view.items
                if str(item.get("capability_name", "")).strip()
            )
        return result

    @staticmethod
    def _query_text(query: Mapping[str, Any]) -> str:
        preferred = (
            "concept",
            "concept_id",
            "fact",
            "resource_type",
            "capability_name",
            "relationship_type",
            "query",
        )
        for key in preferred:
            value = query.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        scalar_values = [
            str(value).strip()
            for value in query.values()
            if isinstance(value, (str, int, float)) and str(value).strip()
        ]
        return " ".join(scalar_values[:4])
PY
printf '%s\n' 'WROTE: implementation/orchestrator/planning_context_reader.py'

printf '%s\n' '========== SECTION 3: ADD INTEGRATION REGRESSION COVERAGE =========='
cat > implementation/orchestrator/tests/test_planning_context_reader.py <<'PY'
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
PY
printf '%s\n' 'WROTE: implementation/orchestrator/tests/test_planning_context_reader.py'

printf '%s\n' '========== SECTION 4: STATIC VALIDATION =========='
git diff --check

printf '%s\n' '========== SECTION 5: FOCUSED TESTS =========='
"$PY" -m pytest -q \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_planning_context_views.py \
  implementation/orchestrator/tests/test_planning_context_reader.py \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_semantic_knowledge_registry.py

printf '%s\n' '========== SECTION 6: CHANGE STATE =========='
git status --short

printf '%s\n' '========== RESULT =========='
printf '%s\n' 'Governed planning context catalog is adapted to the existing bounded planning-loop contract.'
printf '%s\n' 'The planning loop itself was not rewritten or weakened.'
printf '%s\n' 'The local reasoner receives only bounded provider-neutral governed context snapshots.'
printf '%s\n' 'NO RUNTIME WIRING PERFORMED.'
printf '%s\n' 'NO DEPLOYMENT PERFORMED.'
printf '%s\n' 'NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED.'
printf '%s\n' '========== END GOVERNED CONTEXT CATALOG TO PLANNING LOOP REPAIR =========='
