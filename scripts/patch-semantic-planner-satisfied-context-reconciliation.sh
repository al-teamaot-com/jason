#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

PY="/home/al/projects/jason/.venv/bin/python"

echo "========== START SEMANTIC PLANNER SATISFIED CONTEXT RECONCILIATION =========="
echo "========== SECTION 1: PRECONDITIONS =========="
git rev-parse --short HEAD
git status --short

if [ ! -x "$PY" ]; then
  echo "ERROR: project Python not found at $PY"
  exit 20
fi

echo "========== SECTION 2: RECONCILE ALREADY-SATISFIED CONTEXT REQUESTS =========="
"$PY" - <<'PY'
from pathlib import Path

path = Path('implementation/orchestrator/semantic_intent_planning_loop.py')
text = path.read_text()

old = '''        satisfied_requests: set[tuple[str, str]] = set()\n        rejected_plan_signatures: set[str] = set()\n'''
new = '''        satisfied_requests: set[tuple[str, str]] = set()\n        reconciled_satisfied_requests: set[tuple[str, str]] = set()\n        rejected_plan_signatures: set[str] = set()\n'''
if old not in text:
    raise SystemExit('planner initialization marker not found')
text = text.replace(old, new, 1)

old = '''                if request_signature in satisfied_requests:\n                    return IntentPlanningOutcome(\n                        status="knowledge_gap",\n                        plan=None,\n                        gap_summary=(\n                            "planning reasoner repeated an already-satisfied governed context request "\n                            "without progressing the fulfillment plan"\n                        ),\n                        trace=tuple(trace),\n                        iterations_used=iteration,\n                        context_requests_used=context_requests,\n                    )\n'''
new = '''                if request_signature in satisfied_requests:\n                    if request_signature in reconciled_satisfied_requests:\n                        return IntentPlanningOutcome(\n                            status="knowledge_gap",\n                            plan=None,\n                            gap_summary=(\n                                "planning reasoner repeated an already-satisfied governed context request "\n                                "after explicit reconciliation feedback"\n                            ),\n                            trace=tuple(trace),\n                            iterations_used=iteration,\n                            context_requests_used=context_requests,\n                        )\n                    reconciled_satisfied_requests.add(request_signature)\n                    context["context_request_feedback"] = {\n                        "status": "already_satisfied",\n                        "view": request.view,\n                        "query": dict(request.query),\n                        "instruction": (\n                            "The requested governed context is already present in governed_context. "\n                            "Do not request it again. Consume the existing snapshot, request a different "\n                            "governed information need, revise the plan, or declare a knowledge gap."\n                        ),\n                    }\n                    trace.append(PlanningTraceEntry(iteration, "context_reconciled", request.view))\n                    continue\n'''
if old not in text:
    raise SystemExit('repeated satisfied context marker not found')
text = text.replace(old, new, 1)

old = '''                snapshot = self.context_reader.read(request=request, intent=dict(intent))\n                _reject_forbidden_keys(snapshot)\n                satisfied_requests.add(request_signature)\n'''
new = '''                snapshot = self.context_reader.read(request=request, intent=dict(intent))\n                _reject_forbidden_keys(snapshot)\n                context.pop("context_request_feedback", None)\n                satisfied_requests.add(request_signature)\n'''
if old not in text:
    raise SystemExit('context read marker not found')
text = text.replace(old, new, 1)

path.write_text(text)
print(f'UPDATED: {path}')
PY

echo "========== SECTION 3: GUIDE OLLAMA REASONER TO CONSUME RECONCILIATION FEEDBACK =========="
"$PY" - <<'PY'
from pathlib import Path

path = Path('implementation/orchestrator/ollama_semantic_intent_planning.py')
text = path.read_text()
old = '''                "plan, request different governed context, or declare a knowledge gap. Never repeat a rejected "\n                "plan unchanged. If no governed fulfillment path is established, declare a knowledge gap. Keep "\n'''
new = '''                "plan, request different governed context, or declare a knowledge gap. Never repeat a rejected "\n                "plan unchanged. If context_request_feedback is present, the requested context is already supplied; "\n                "consume the existing snapshot and do not request that same view/query again. If no governed "\n                "fulfillment path is established, declare a knowledge gap. Keep "\n'''
if old not in text:
    raise SystemExit('Ollama prompt marker not found')
text = text.replace(old, new, 1)
path.write_text(text)
print(f'UPDATED: {path}')
PY

echo "========== SECTION 4: ADD GENERALIZED REGRESSION COVERAGE =========="
cat >> implementation/orchestrator/tests/test_semantic_intent_planning_loop.py <<'PY'


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
PY

echo "UPDATED: implementation/orchestrator/tests/test_semantic_intent_planning_loop.py"

echo "========== SECTION 5: STATIC VALIDATION ==========" 
git diff --check

echo "========== SECTION 6: FOCUSED TESTS ==========" 
"$PY" -m pytest -q \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_semantic_plan_sufficiency.py \
  implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py \
  implementation/orchestrator/tests/test_semantic_planning_bootstrap.py

echo "========== SECTION 7: CHANGE STATE ==========" 
git status --short

echo "========== RESULT ==========" 
echo "Already-satisfied governed context requests are now reconciled once without rereading providers or burning context-request budget."
echo "The reasoner receives explicit feedback to consume existing context, request a different governed need, revise the plan, or declare a gap."
echo "A second identical request after reconciliation still fails closed."
echo "This is provider-neutral and does not special-case Windows, Datto, or the acceptance question."
echo "NO RUNTIME ACTIVATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC PLANNER SATISFIED CONTEXT RECONCILIATION =========="
