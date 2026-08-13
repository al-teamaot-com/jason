#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

PY="/home/al/projects/jason/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "ERROR: project Python not found at $PY"
  exit 20
fi

echo "========== START SEMANTIC PLANNER REQUESTABLE CONTEXT POLICY =========="
echo "========== SECTION 1: PRECONDITIONS =========="
git rev-parse --short HEAD
git status --short

echo "========== SECTION 2: EXPOSE REQUESTABLE CONTEXT POLICY TO REASONER =========="
"$PY" - <<'PY'
from pathlib import Path

path = Path('implementation/orchestrator/ollama_semantic_intent_planning.py')
text = path.read_text()

marker = '''        result = self.client.complete(\n            system=(\n'''
if marker not in text:
    raise SystemExit('Ollama completion marker not found')

insert = '''        governed_view_names = (\n            "semantic_knowledge",\n            "capability_registry",\n            "system_registry",\n            "evidence_catalog",\n            "derivation_registry",\n        )\n        already_available_context_views = tuple(\n            name for name in governed_view_names if name in context\n        )\n        requestable_context_views = tuple(\n            name for name in governed_view_names if name not in context\n        )\n\n'''
text = text.replace(marker, insert + marker, 1)

old = '''                "plan, request different governed context, or declare a knowledge gap. Never repeat a rejected "\n                "plan unchanged. If no governed fulfillment path is established, declare a knowledge gap. Keep "\n                "reasoning concise and structured."\n'''
new = '''                "plan, request different governed context, or declare a knowledge gap. Never repeat a rejected "\n                "plan unchanged. The user payload includes already_available_context_views and "\n                "requestable_context_views. If requesting context, choose only a view listed in "\n                "requestable_context_views; do not ask again for a view that is already available. If no "\n                "requestable view can materially advance the plan, revise from supplied context or declare a "\n                "knowledge gap. If no governed fulfillment path is established, declare a knowledge gap. Keep "\n                "reasoning concise and structured."\n'''
if old not in text:
    raise SystemExit('Ollama system prompt marker not found')
text = text.replace(old, new, 1)

old = '''                    "history": [\n                        {\n                            "iteration": item.iteration,\n                            "status": item.status,\n                            "context_view": item.context_view,\n                        }\n                        for item in history\n                    ],\n'''
new = '''                    "history": [\n                        {\n                            "iteration": item.iteration,\n                            "status": item.status,\n                            "context_view": item.context_view,\n                        }\n                        for item in history\n                    ],\n                    "already_available_context_views": list(already_available_context_views),\n                    "requestable_context_views": list(requestable_context_views),\n'''
if old not in text:
    raise SystemExit('Ollama user payload marker not found')
text = text.replace(old, new, 1)

old = '''        if status == "request_context":\n            view = str(result.get("context_view", "")).strip()\n            query = str(result.get("context_query", "")).strip()\n            purpose = str(result.get("context_purpose", "")).strip()\n            return PlanningTurn(\n'''
new = '''        if status == "request_context":\n            view = str(result.get("context_view", "")).strip()\n            query = str(result.get("context_query", "")).strip()\n            purpose = str(result.get("context_purpose", "")).strip()\n            if view not in requestable_context_views:\n                return PlanningTurn(\n                    status="declare_gap",\n                    gap_summary=(\n                        "semantic planning requested governed context that is already available or not "\n                        "requestable in the current turn"\n                    ),\n                )\n            return PlanningTurn(\n'''
if old not in text:
    raise SystemExit('request_context parse marker not found')
text = text.replace(old, new, 1)

path.write_text(text)
print(f'UPDATED: {path}')
PY

echo "========== SECTION 3: ADD GENERALIZED REGRESSION COVERAGE =========="
cat >> implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py <<'PY'


def test_reasoner_declares_gap_when_model_requests_context_view_already_supplied():
    class Client:
        def complete(self, **kwargs):
            return {
                "status": "request_context",
                "context_view": "semantic_knowledge",
                "context_query": "processor model",
                "context_purpose": "inspect semantics again",
                "plan_steps": [],
                "rationale_summary": "",
                "unresolved_requirements": [],
                "gap_summary": "",
            }

    reasoner = OllamaSemanticIntentPlanningReasoner(client=Client())
    turn = reasoner.next_turn(
        intent={"resource_type": "endpoint", "requested_facts": ["processor model"]},
        context={
            "semantic_knowledge": {"items": ({"concept_id": "processor.model"},)},
            "capability_registry": {"capability_names": ("endpoint.device.search",)},
        },
        history=(),
    )

    assert turn.status == "declare_gap"
    assert "already available" in str(turn.gap_summary)


def test_reasoner_allows_request_for_governed_context_not_yet_supplied():
    class Client:
        def complete(self, **kwargs):
            return {
                "status": "request_context",
                "context_view": "evidence_catalog",
                "context_query": "processor model",
                "context_purpose": "inspect authoritative evidence options",
                "plan_steps": [],
                "rationale_summary": "",
                "unresolved_requirements": [],
                "gap_summary": "",
            }

    reasoner = OllamaSemanticIntentPlanningReasoner(client=Client())
    turn = reasoner.next_turn(
        intent={"resource_type": "endpoint", "requested_facts": ["processor model"]},
        context={
            "semantic_knowledge": {"items": ({"concept_id": "processor.model"},)},
            "capability_registry": {"capability_names": ("endpoint.device.search",)},
        },
        history=(),
    )

    assert turn.status == "request_context"
    assert turn.context_request is not None
    assert turn.context_request.view == "evidence_catalog"
PY

echo "UPDATED: implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py"

echo "========== SECTION 4: STATIC VALIDATION =========="
git diff --check

echo "========== SECTION 5: FOCUSED TESTS =========="
"$PY" -m pytest -q \
  implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_semantic_plan_sufficiency.py \
  implementation/orchestrator/tests/test_semantic_planning_bootstrap.py \
  implementation/runtime_service/tests/test_semantic_planner_observe_only_probe.py

echo "========== SECTION 6: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Semantic planning now exposes which governed context views are already available and which remain requestable."
echo "The local reasoner may request only not-yet-supplied governed views; otherwise it must revise from existing context or declare a gap."
echo "This is provider-neutral and does not special-case Windows, Datto, or the current acceptance question."
echo "NO RUNTIME ACTIVATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC PLANNER REQUESTABLE CONTEXT POLICY =========="
