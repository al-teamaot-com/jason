#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

PY="/home/al/projects/jason/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "ERROR: project Python not found at $PY"
  exit 20
fi

echo "========== START GOVERNED SEMANTIC PLANNER BOOTSTRAP CONTEXT =========="
echo "========== SECTION 1: PRECONDITIONS =========="
git rev-parse --short HEAD
git status --short

echo "========== SECTION 2: ADD PROVIDER-NEUTRAL INTENT BOOTSTRAPPER =========="
cat > implementation/orchestrator/semantic_planning_bootstrap.py <<'PY'
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .semantic_intent_planning_loop import PlanningContextRequest


@dataclass(frozen=True, slots=True)
class ProviderNeutralIntentContextBootstrapper:
    """Derive bounded governed context prerequisites from provider-neutral intent.

    The bootstrapper does not select providers, connectors, agents, tools, or execution
    routes. It only ensures the reasoner begins with semantic meaning and registered
    capability context instead of spending reasoning turns rediscovering those basics.
    """

    def requests_for(self, *, intent: Mapping[str, Any]) -> tuple[PlanningContextRequest, ...]:
        requested_facts = intent.get("requested_facts", ())
        if isinstance(requested_facts, str):
            facts = (requested_facts.strip(),) if requested_facts.strip() else ()
        elif isinstance(requested_facts, (list, tuple, set, frozenset)):
            facts = tuple(str(item).strip() for item in requested_facts if str(item).strip())
        else:
            facts = ()

        resource_type = str(intent.get("resource_type", "")).strip()
        human_text = str(intent.get("human_text", "")).strip()

        semantic_query = " ".join(facts[:3]).strip() or human_text[:160].strip()
        capability_query = resource_type or " ".join(facts[:2]).strip() or human_text[:120].strip()

        requests: list[PlanningContextRequest] = []
        if semantic_query:
            requests.append(
                PlanningContextRequest(
                    view="semantic_knowledge",
                    query={"query": semantic_query},
                    purpose="establish governed meaning for the requested fact or relationship",
                )
            )
        if capability_query:
            requests.append(
                PlanningContextRequest(
                    view="capability_registry",
                    query={"query": capability_query},
                    purpose="establish governed provider-neutral capabilities relevant to the intent",
                )
            )
        return tuple(requests)
PY

echo "WROTE: implementation/orchestrator/semantic_planning_bootstrap.py"

echo "========== SECTION 3: WIRE OPTIONAL BOOTSTRAP INTO BOUNDED LOOP =========="
"$PY" - <<'PY'
from pathlib import Path

path = Path("implementation/orchestrator/semantic_intent_planning_loop.py")
text = path.read_text()

old = '''class GovernedPlanningContextReader(Protocol):\n    def read(\n        self,\n        *,\n        request: PlanningContextRequest,\n        intent: Mapping[str, Any],\n    ) -> Mapping[str, Any]: ...\n\n\n@dataclass(frozen=True, slots=True)\nclass BoundedSemanticIntentPlanningLoop:\n    reasoner: SemanticIntentPlanningReasoner\n    context_reader: GovernedPlanningContextReader\n    budget: IntentPlanningBudget = IntentPlanningBudget()\n'''
new = '''class GovernedPlanningContextReader(Protocol):\n    def read(\n        self,\n        *,\n        request: PlanningContextRequest,\n        intent: Mapping[str, Any],\n    ) -> Mapping[str, Any]: ...\n\n\nclass IntentPlanningContextBootstrapper(Protocol):\n    def requests_for(\n        self,\n        *,\n        intent: Mapping[str, Any],\n    ) -> Sequence[PlanningContextRequest]: ...\n\n\n@dataclass(frozen=True, slots=True)\nclass BoundedSemanticIntentPlanningLoop:\n    reasoner: SemanticIntentPlanningReasoner\n    context_reader: GovernedPlanningContextReader\n    budget: IntentPlanningBudget = IntentPlanningBudget()\n    context_bootstrapper: IntentPlanningContextBootstrapper | None = None\n'''
if old not in text:
    raise SystemExit("planning loop protocol/dataclass marker not found")
text = text.replace(old, new, 1)

old = '''        context: dict[str, Any] = {}\n        trace: list[PlanningTraceEntry] = []\n        context_requests = 0\n        satisfied_requests: set[tuple[str, str]] = set()\n\n        for iteration in range(1, self.budget.max_iterations + 1):\n'''
new = '''        context: dict[str, Any] = {}\n        trace: list[PlanningTraceEntry] = []\n        context_requests = 0\n        satisfied_requests: set[tuple[str, str]] = set()\n\n        if self.context_bootstrapper is not None:\n            bootstrap_requests = tuple(self.context_bootstrapper.requests_for(intent=dict(intent)))\n            if len(bootstrap_requests) > 5:\n                raise ValueError("planning bootstrap context request limit exceeded")\n            for request in bootstrap_requests:\n                snapshot = self.context_reader.read(request=request, intent=dict(intent))\n                _reject_forbidden_keys(snapshot)\n                request_signature = (\n                    request.view,\n                    repr(sorted((str(key), repr(value)) for key, value in request.query.items())),\n                )\n                satisfied_requests.add(request_signature)\n                context[request.view] = dict(snapshot)\n\n        for iteration in range(1, self.budget.max_iterations + 1):\n'''
if old not in text:
    raise SystemExit("planning loop initialization marker not found")
text = text.replace(old, new, 1)
path.write_text(text)
print(f"UPDATED: {path}")
PY

echo "========== SECTION 4: ADD GENERALIZED REGRESSION COVERAGE =========="
cat >> implementation/orchestrator/tests/test_semantic_intent_planning_loop.py <<'PY'


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
PY

cat > implementation/orchestrator/tests/test_semantic_planning_bootstrap.py <<'PY'
from orchestrator.semantic_planning_bootstrap import ProviderNeutralIntentContextBootstrapper


def test_bootstrapper_requests_semantic_and_capability_context_from_intent():
    requests = ProviderNeutralIntentContextBootstrapper().requests_for(
        intent={
            "human_text": "What CPU does AOT-EXAMPLE have?",
            "resource_type": "endpoint",
            "requested_facts": ("processor model",),
            "permission_mode": "observe",
        }
    )
    assert [item.view for item in requests] == ["semantic_knowledge", "capability_registry"]
    assert requests[0].query == {"query": "processor model"}
    assert requests[1].query == {"query": "endpoint"}


def test_bootstrapper_never_adds_provider_or_execution_fields():
    requests = ProviderNeutralIntentContextBootstrapper().requests_for(
        intent={
            "resource_type": "endpoint",
            "requested_facts": ("total memory",),
        }
    )
    rendered = repr(requests).casefold()
    for forbidden in ("provider_name", "connector_name", "tool_name", "credential", "command"):
        assert forbidden not in rendered
PY

echo "WROTE: implementation/orchestrator/tests/test_semantic_planning_bootstrap.py"

echo "========== SECTION 5: ENABLE BOOTSTRAP IN OBSERVE-ONLY LIVE PROBE =========="
"$PY" - <<'PY'
from pathlib import Path

path = Path("scripts/run-live-observe-only-semantic-planner-intent-probe.sh")
text = path.read_text()
import_line = "from orchestrator.semantic_intent_planning_loop import BoundedSemanticIntentPlanningLoop, IntentPlanningBudget\n"
replacement = import_line + "from orchestrator.semantic_planning_bootstrap import ProviderNeutralIntentContextBootstrapper\n"
if replacement not in text:
    if import_line not in text:
        raise SystemExit("live probe planning-loop import marker not found")
    text = text.replace(import_line, replacement, 1)
old = '''planner = BoundedSemanticIntentPlanningLoop(\n    reasoner=OllamaSemanticIntentPlanningReasoner(client=client),\n    context_reader=GovernedPlanningContextReaderAdapter(catalog=catalog, default_limit=48),\n    budget=IntentPlanningBudget(max_iterations=8, max_context_requests=7),\n)\n'''
new = '''planner = BoundedSemanticIntentPlanningLoop(\n    reasoner=OllamaSemanticIntentPlanningReasoner(client=client),\n    context_reader=GovernedPlanningContextReaderAdapter(catalog=catalog, default_limit=48),\n    budget=IntentPlanningBudget(max_iterations=8, max_context_requests=7),\n    context_bootstrapper=ProviderNeutralIntentContextBootstrapper(),\n)\n'''
if old not in text:
    raise SystemExit("live probe planner construction marker not found")
text = text.replace(old, new, 1)
path.write_text(text)
print(f"UPDATED: {path}")
PY

echo "========== SECTION 6: STATIC VALIDATION ==========" 
git diff --check

echo "========== SECTION 7: FOCUSED TESTS ==========" 
"$PY" -m pytest -q \
  implementation/orchestrator/tests/test_semantic_planning_bootstrap.py \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py \
  implementation/orchestrator/tests/test_planning_context_reader.py \
  implementation/runtime_service/tests/test_semantic_planner_observe_only_probe.py

echo "========== SECTION 8: CHANGE STATE ==========" 
git status --short

echo "========== RESULT ==========" 
echo "Governed semantic planning now supports provider-neutral bootstrap context before the first local-LLM reasoning turn."
echo "The bootstrap supplies semantic meaning and registered capability context only; it grants no provider, connector, tool, agent, credential, or execution authority."
echo "NO RUNTIME ACTIVATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END GOVERNED SEMANTIC PLANNER BOOTSTRAP CONTEXT =========="
