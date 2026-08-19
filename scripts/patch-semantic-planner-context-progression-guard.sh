#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC PLANNER CONTEXT PROGRESSION GUARD =========="
echo "========== SECTION 1: PRECONDITIONS =========="
git rev-parse --short HEAD
git status --short

PY="/home/al/projects/jason/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "ERROR: project Python not found at $PY"
  exit 20
fi

echo "========== SECTION 2: PREVENT REPEATED SATISFIED CONTEXT REQUESTS =========="
"$PY" - <<'PY'
from pathlib import Path

path = Path('implementation/orchestrator/semantic_intent_planning_loop.py')
text = path.read_text()

old = '''        context: dict[str, Any] = {}\n        trace: list[PlanningTraceEntry] = []\n        context_requests = 0\n'''
new = '''        context: dict[str, Any] = {}\n        trace: list[PlanningTraceEntry] = []\n        context_requests = 0\n        satisfied_requests: set[tuple[str, str]] = set()\n'''
if old not in text:
    raise SystemExit('planning loop initialization marker not found')
text = text.replace(old, new, 1)

old = '''                request = turn.context_request\n                snapshot = self.context_reader.read(request=request, intent=dict(intent))\n                _reject_forbidden_keys(snapshot)\n                context_requests += 1\n                context[request.view] = dict(snapshot)\n                trace.append(PlanningTraceEntry(iteration, turn.status, request.view))\n                continue\n'''
new = '''                request = turn.context_request\n                request_signature = (\n                    request.view,\n                    repr(sorted((str(key), repr(value)) for key, value in request.query.items())),\n                )\n                if request_signature in satisfied_requests:\n                    return IntentPlanningOutcome(\n                        status="knowledge_gap",\n                        plan=None,\n                        gap_summary=(\n                            "planning reasoner repeated an already-satisfied governed context request "\n                            "without progressing the fulfillment plan"\n                        ),\n                        trace=tuple(trace),\n                        iterations_used=iteration,\n                        context_requests_used=context_requests,\n                    )\n                snapshot = self.context_reader.read(request=request, intent=dict(intent))\n                _reject_forbidden_keys(snapshot)\n                satisfied_requests.add(request_signature)\n                context_requests += 1\n                context[request.view] = dict(snapshot)\n                trace.append(PlanningTraceEntry(iteration, turn.status, request.view))\n                continue\n'''
if old not in text:
    raise SystemExit('planning loop request handling marker not found')
text = text.replace(old, new, 1)
path.write_text(text)
print(f'UPDATED: {path}')
PY

echo "========== SECTION 3: GUIDE REASONER TOWARD CONTEXT PROGRESSION =========="
"$PY" - <<'PY'
from pathlib import Path

path = Path('implementation/orchestrator/ollama_semantic_intent_planning.py')
text = path.read_text()
old = '''                "needed. A proposed plan may reference only capability names present in governed capability "\n                "registry context. Prefer direct authoritative evidence; otherwise consider alternate governed "\n                "capabilities or approved derivations represented in context. If no governed fulfillment path "\n                "is established, declare a knowledge gap. Keep reasoning concise and structured."\n'''
new = '''                "needed. Never request the exact same context view and query twice. Treat a returned governed "\n                "context snapshot as satisfied and progress to a different information need, a plan, or a gap. "\n                "For a normal information request, prefer semantic knowledge and capability-registry context "\n                "before system-state context unless system availability is specifically unresolved. A proposed "\n                "plan may reference only capability names present in governed capability registry context. "\n                "Prefer direct authoritative evidence; otherwise consider alternate governed capabilities or "\n                "approved derivations represented in context. If no governed fulfillment path is established, "\n                "declare a knowledge gap. Keep reasoning concise and structured."\n'''
if old not in text:
    raise SystemExit('reasoner prompt marker not found')
text = text.replace(old, new, 1)
path.write_text(text)
print(f'UPDATED: {path}')
PY

echo "========== SECTION 4: ADD GENERALIZED REGRESSION COVERAGE =========="
cat >> implementation/orchestrator/tests/test_semantic_intent_planning_loop.py <<'PY'


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
    assert outcome.iterations_used == 2
    assert reader.calls == 1
    assert "already-satisfied" in str(outcome.gap_summary)
PY

echo "UPDATED: implementation/orchestrator/tests/test_semantic_intent_planning_loop.py"

echo "========== SECTION 5: STATIC VALIDATION =========="ngit diff --check

echo "========== SECTION 6: FOCUSED TESTS =========="n"$PY" -m pytest -q \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py \
  implementation/orchestrator/tests/test_planning_context_reader.py \
  implementation/runtime_service/tests/test_semantic_planner_observe_only_probe.py

echo "========== SECTION 7: CHANGE STATE =========="ngit status --short

echo "========== RESULT =========="necho "Bounded semantic planning now requires forward context progression and fails closed on exact repeated requests."
echo "The Ollama reasoner is instructed to consume satisfied governed context instead of polling the same view repeatedly."
echo "This is provider-neutral and does not special-case Windows, Datto, or the current acceptance question."
echo "NO RUNTIME ACTIVATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC PLANNER CONTEXT PROGRESSION GUARD =========="
