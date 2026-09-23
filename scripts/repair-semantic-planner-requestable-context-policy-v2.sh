#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC PLANNER REQUESTABLE CONTEXT POLICY REPAIR V2 =========="
echo "========== SECTION 1: PRECONDITIONS =========="
git rev-parse --short HEAD
git status --short

PY="/home/al/projects/jason/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "ERROR: project Python not found at $PY"
  exit 20
fi

echo "========== SECTION 2: APPLY STRUCTURAL REQUESTABLE-CONTEXT POLICY =========="
"$PY" - <<'PY'
from pathlib import Path

path = Path('implementation/orchestrator/ollama_semantic_intent_planning.py')
text = path.read_text()

if 'requestable_context_views = tuple(' not in text:
    marker = '    ) -> PlanningTurn:\n        schema = {\n'
    insert = '''    ) -> PlanningTurn:\n        governed_context_views = (\n            "semantic_knowledge",\n            "capability_registry",\n            "system_registry",\n            "evidence_catalog",\n            "derivation_registry",\n        )\n        available_context_views = tuple(\n            view for view in governed_context_views if view in context\n        )\n        requestable_context_views = tuple(\n            view for view in governed_context_views if view not in context\n        )\n        allowed_statuses = ["propose_plan", "declare_gap"]\n        if requestable_context_views:\n            allowed_statuses.insert(0, "request_context")\n\n        schema = {\n'''
    if marker not in text:
        raise SystemExit('planner schema marker not found')
    text = text.replace(marker, insert, 1)

text = text.replace(
    '"enum": ["request_context", "propose_plan", "declare_gap"],',
    '"enum": allowed_statuses,',
    1,
)

old_view_enum = '''"enum": [\n                        "semantic_knowledge",\n                        "capability_registry",\n                        "system_registry",\n                        "evidence_catalog",\n                        "derivation_registry",\n                    ],'''
new_view_enum = '"enum": list(requestable_context_views) if requestable_context_views else [""],'
if old_view_enum in text:
    text = text.replace(old_view_enum, new_view_enum, 1)
elif new_view_enum not in text:
    raise SystemExit('context-view schema marker not found')

payload_marker = '''                    "intent": dict(intent),\n                    "governed_context": dict(context),\n                    "history": [\n'''
payload_replacement = '''                    "intent": dict(intent),\n                    "governed_context": dict(context),\n                    "available_context_views": list(available_context_views),\n                    "requestable_context_views": list(requestable_context_views),\n                    "history": [\n'''
if payload_replacement not in text:
    if payload_marker not in text:
        raise SystemExit('planner user payload marker not found')
    text = text.replace(payload_marker, payload_replacement, 1)

prompt_marker = '''                "plan unchanged. If context_request_feedback is present, the requested context is already supplied; "\n                "consume the existing snapshot and do not request that same view/query again. If no governed "\n'''
prompt_replacement = '''                "plan unchanged. The user payload explicitly lists available_context_views and "\n                "requestable_context_views. A request_context response is permitted only for a view listed in "\n                "requestable_context_views; never request a view already listed in available_context_views. "\n                "If context_request_feedback is present, consume the existing snapshot and do not request that "\n                "same view/query again. If no governed "\n'''
if prompt_replacement not in text:
    if prompt_marker not in text:
        raise SystemExit('current planner prompt marker not found')
    text = text.replace(prompt_marker, prompt_replacement, 1)

request_marker = '''        if status == "request_context":\n            view = str(result.get("context_view", "")).strip()\n            query = str(result.get("context_query", "")).strip()\n'''
request_replacement = '''        if status == "request_context":\n            view = str(result.get("context_view", "")).strip()\n            if view not in requestable_context_views:\n                raise PermissionError(\n                    f"semantic planner requested context view that is not requestable this turn: {view}"\n                )\n            query = str(result.get("context_query", "")).strip()\n'''
if request_replacement not in text:
    if request_marker not in text:
        raise SystemExit('request-context handling marker not found')
    text = text.replace(request_marker, request_replacement, 1)

path.write_text(text)
print(f'UPDATED: {path}')
PY

echo "========== SECTION 3: ADD CONTRACT REGRESSION COVERAGE =========="
cat >> implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py <<'PY'


def test_reasoner_schema_exposes_only_context_views_not_already_supplied():
    response = _base_response("request_context")
    response.update(
        {
            "context_view": "evidence_catalog",
            "context_query": "operating system display version",
            "context_purpose": "inspect governed evidence availability",
        }
    )
    client = FakeClient(response)
    reasoner = OllamaSemanticIntentPlanningReasoner(client)
    turn = reasoner.next_turn(
        intent={"goal": "retrieve_fact"},
        context={
            "semantic_knowledge": {"items": []},
            "capability_registry": {"items": []},
        },
        history=(),
    )
    assert turn.status == "request_context"
    assert client.calls is not None
    schema = client.calls[0]["schema"]
    assert schema["properties"]["context_view"]["enum"] == [
        "system_registry",
        "evidence_catalog",
        "derivation_registry",
    ]


def test_reasoner_rejects_model_request_for_context_already_supplied():
    response = _base_response("request_context")
    response.update(
        {
            "context_view": "semantic_knowledge",
            "context_query": "operating system display version",
            "context_purpose": "repeat supplied semantic context",
        }
    )
    reasoner = OllamaSemanticIntentPlanningReasoner(FakeClient(response))
    with pytest.raises(PermissionError, match="not requestable"):
        reasoner.next_turn(
            intent={"goal": "retrieve_fact"},
            context={"semantic_knowledge": {"items": []}},
            history=(),
        )
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
echo "Requestable context is now enforced structurally by the reasoner schema and post-response contract."
echo "Already-supplied governed views are removed from the model's requestable context choices for that turn."
echo "The policy remains provider-neutral, observe-only, and disconnected from execution."
echo "NO RUNTIME ACTIVATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC PLANNER REQUESTABLE CONTEXT POLICY REPAIR V2 =========="
