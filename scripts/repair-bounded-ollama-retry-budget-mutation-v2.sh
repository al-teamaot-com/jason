#!/usr/bin/env bash
set -e

echo "========== START BOUNDED OLLAMA RETRY BUDGET MUTATION REPAIR V2 =========="
echo "========== SECTION 1: CURRENT STATE =========="
git rev-parse --short HEAD
git status --short

echo "========== SECTION 2: MUTATE RETRY BUDGET ONLY AFTER FIRST JSON FAILURE =========="
PYTHON_BIN="/home/al/projects/jason/.venv/bin/python"
"$PYTHON_BIN" - <<'PY'
from pathlib import Path
path = Path("implementation/orchestrator/ollama_reasoning.py")
text = path.read_text()
old = '''        for attempt in range(2):\n            response = self.transport.request(\n                method="POST",\n                url=f"{self.base_url.rstrip('/')}/api/chat",\n                headers={"Content-Type": "application/json"},\n                json=request_payload,\n                timeout_seconds=self.timeout_seconds,\n            )\n'''
new = '''        for attempt in range(2):\n            request_payload["options"]["num_predict"] = (\n                max_output_tokens\n                if attempt == 0\n                else min(max_output_tokens * 2, 1024)\n            )\n            response = self.transport.request(\n                method="POST",\n                url=f"{self.base_url.rstrip('/')}/api/chat",\n                headers={"Content-Type": "application/json"},\n                json=request_payload,\n                timeout_seconds=self.timeout_seconds,\n            )\n'''
if old not in text:
    raise SystemExit("structured retry loop marker not found")
path.write_text(text.replace(old, new, 1))
print(f"UPDATED: {path}")
PY

echo "========== SECTION 3: STATIC VALIDATION =========="ngit diff --check

echo "========== SECTION 4: FOCUSED TESTS =========="n/home/al/projects/jason/.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_ollama_reasoning.py \
  implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py

echo "========== SECTION 5: CHANGE STATE =========="ngit status --short

echo "========== RESULT =========="necho "The first Ollama structured-generation attempt now uses the caller's exact token budget."necho "Only the bounded retry escalates to up to 2x, capped at 1024 tokens."necho "NO RUNTIME ACTIVATION PERFORMED."necho "NO DEPLOYMENT PERFORMED."necho "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."necho "========== END BOUNDED OLLAMA RETRY BUDGET MUTATION REPAIR V2 =========="
