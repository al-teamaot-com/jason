#!/usr/bin/env bash
set -euo pipefail

cd /home/al/projects/jason

PYTHON=/home/al/projects/jason/.venv/bin/python
TARGET=implementation/orchestrator/ollama_reasoning.py
TEST=implementation/orchestrator/tests/test_ollama_reasoning.py
PLANNER_TEST=implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py

echo '========== START BOUNDED OLLAMA RETRY FIRST-PASS BUDGET REPAIR =========='
echo '========== SECTION 1: CURRENT STATE =========='
git rev-parse --short HEAD
git status --short

echo '========== SECTION 2: PRESERVE CALLER BUDGET ON FIRST ATTEMPT =========='
"$PYTHON" - <<'PY'
from pathlib import Path
import re

path = Path('implementation/orchestrator/ollama_reasoning.py')
text = path.read_text()

# Remove any retry-budget assignment that was placed before the HTTP request and
# replace it with an explicit per-attempt contract: first attempt uses exactly the
# caller's budget; only the second bounded retry may increase it.
loop_marker = '        for attempt in range(2):\n'
if loop_marker not in text:
    raise SystemExit('bounded retry loop marker not found')

start = text.index(loop_marker)
request_marker = '            response = self.transport.request(\n'
request_pos = text.find(request_marker, start)
if request_pos < 0:
    raise SystemExit('Ollama transport request marker not found')

prefix = text[: start + len(loop_marker)]
segment = text[start + len(loop_marker):request_pos]
suffix = text[request_pos:]

# Strip prior retry-budget mutations in this narrow segment only.
segment = re.sub(
    r'^[ \t]*(?:retry_|attempt_)?(?:output_)?tokens\s*=.*\n',
    '',
    segment,
    flags=re.MULTILINE,
)
segment = re.sub(
    r'^[ \t]*request_payload\["options"\]\["num_predict"\]\s*=.*\n',
    '',
    segment,
    flags=re.MULTILINE,
)

contract = (
    '            attempt_output_tokens = (\n'
    '                max_output_tokens\n'
    '                if attempt == 0\n'
    '                else min(max_output_tokens * 2, 1024)\n'
    '            )\n'
    '            request_payload["options"]["num_predict"] = attempt_output_tokens\n'
)

text = prefix + contract + segment + suffix
path.write_text(text)
print(f'UPDATED: {path}')
PY

echo '========== SECTION 3: STATIC VALIDATION =========='
git diff --check

echo '========== SECTION 4: FOCUSED TESTS =========='
"$PYTHON" -m pytest -q \
  "$TEST" \
  "$PLANNER_TEST"

echo '========== SECTION 5: CHANGE STATE =========='
git status --short

echo '========== RESULT =========='
echo 'The first structured Ollama attempt now preserves the exact caller-supplied generation budget.'
echo 'Only the single bounded retry may increase that budget, capped at 1024 tokens.'
echo 'This repairs structured-response truncation recovery without silently doubling every normal reasoning call.'
echo 'NO RUNTIME ACTIVATION PERFORMED.'
echo 'NO DEPLOYMENT PERFORMED.'
echo 'NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED.'
echo '========== END BOUNDED OLLAMA RETRY FIRST-PASS BUDGET REPAIR =========='
