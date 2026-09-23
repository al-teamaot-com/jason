#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

PY="/home/al/projects/jason/.venv/bin/python"

echo "========== START BOUNDED OLLAMA STRUCTURED TRUNCATION RECOVERY =========="
echo "========== SECTION 1: PRECONDITIONS =========="
git rev-parse --short HEAD
git status --short

if [ ! -x "$PY" ]; then
  echo "ERROR: project Python not found at $PY"
  exit 20
fi

echo "========== SECTION 2: ADD BOUNDED RETRY TOKEN ESCALATION =========="
"$PY" - <<'PY'
from pathlib import Path

path = Path('implementation/orchestrator/ollama_reasoning.py')
text = path.read_text()

old = '''        request_payload = {\n            "model": self.model,\n            "messages": [\n                {"role": "system", "content": system},\n                {"role": "user", "content": user},\n            ],\n            "think": False,\n            "stream": False,\n            "format": dict(schema),\n            "options": {\n                "temperature": 0,\n                "num_predict": max_output_tokens,\n            },\n        }\n\n        last_json_error: json.JSONDecodeError | None = None\n\n        for attempt in range(2):\n            response = self.transport.request(\n'''
new = '''        request_payload = {\n            "model": self.model,\n            "messages": [\n                {"role": "system", "content": system},\n                {"role": "user", "content": user},\n            ],\n            "think": False,\n            "stream": False,\n            "format": dict(schema),\n            "options": {\n                "temperature": 0,\n                "num_predict": max_output_tokens,\n            },\n        }\n\n        last_json_error: json.JSONDecodeError | None = None\n\n        for attempt in range(2):\n            if attempt == 1:\n                retry_budget = min(1024, max(max_output_tokens + 64, max_output_tokens * 2))\n                request_payload["options"] = {\n                    "temperature": 0,\n                    "num_predict": retry_budget,\n                }\n            response = self.transport.request(\n'''
if old not in text:
    raise SystemExit('structured Ollama request marker not found')
text = text.replace(old, new, 1)
path.write_text(text)
print(f'UPDATED: {path}')
PY

echo "========== SECTION 3: GIVE SEMANTIC PLANNER ADEQUATE FIRST-PASS BUDGET =========="
"$PY" - <<'PY'
from pathlib import Path

path = Path('implementation/orchestrator/ollama_semantic_intent_planning.py')
text = path.read_text()
old = '            max_output_tokens=320,\n'
new = '            max_output_tokens=512,\n'
if old not in text:
    raise SystemExit('semantic planner output budget marker not found')
text = text.replace(old, new, 1)
path.write_text(text)
print(f'UPDATED: {path}')
PY

echo "========== SECTION 4: ADD GENERALIZED REGRESSION COVERAGE =========="
cat >> implementation/orchestrator/tests/test_ollama_reasoning.py <<'PY'


def test_structured_json_retry_increases_generation_budget_after_truncated_json():
    import json

    class TruncatingTransport:
        def __init__(self):
            self.payloads = []

        def request(self, **kwargs):
            self.payloads.append(kwargs["json"])
            if len(self.payloads) == 1:
                return {"message": {"content": '{"status":"propose_plan","rationale_summary":"unterminated'}}
            return {"message": {"content": json.dumps({"status": "ok"})}}

    transport = TruncatingTransport()
    client = OllamaStructuredJsonClient(transport=transport, model="test-model")
    result = client.complete(
        system="bounded test",
        user="bounded test",
        schema={"type": "object"},
        max_output_tokens=160,
    )

    assert result == {"status": "ok"}
    assert transport.payloads[0]["options"]["num_predict"] == 160
    assert transport.payloads[1]["options"]["num_predict"] == 320
PY

echo "UPDATED: implementation/orchestrator/tests/test_ollama_reasoning.py"

echo "========== SECTION 5: STATIC VALIDATION ==========" 
git diff --check

echo "========== SECTION 6: FOCUSED TESTS ==========" 
"$PY" -m pytest -q \
  implementation/orchestrator/tests/test_ollama_reasoning.py \
  implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_semantic_plan_sufficiency.py

echo "========== SECTION 7: CHANGE STATE ==========" 
git status --short

echo "========== RESULT ==========" 
echo "Ollama structured reasoning now retries malformed/truncated JSON once with a bounded larger generation budget."
echo "Semantic intent planning receives a larger first-pass structured-output budget without changing authority or execution boundaries."
echo "This is a generic structured-reasoning reliability repair, not a Windows-, Datto-, or acceptance-question-specific patch."
echo "NO RUNTIME ACTIVATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END BOUNDED OLLAMA STRUCTURED TRUNCATION RECOVERY =========="
