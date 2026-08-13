#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC PLANNER CONTEXT RECONCILIATION REGRESSION REPAIR V2 =========="
echo "========== SECTION 1: CURRENT STATE =========="
git rev-parse --short HEAD
git status --short

PY="/home/al/projects/jason/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "ERROR: project Python not found at $PY"
  exit 20
fi

echo "========== SECTION 2: ALIGN REPEATED-CONTEXT REGRESSION BY FUNCTION SCOPE =========="
"$PY" - <<'PY'
from pathlib import Path

path = Path('implementation/orchestrator/tests/test_semantic_intent_planning_loop.py')
text = path.read_text()
start_marker = 'def test_repeated_identical_context_request_fails_closed_without_burning_budget():'
end_marker = '\n\ndef test_bootstrap_context_is_supplied_before_first_reasoning_turn():'
start = text.find(start_marker)
if start < 0:
    raise SystemExit('repeated-context regression function not found')
end = text.find(end_marker, start)
if end < 0:
    raise SystemExit('repeated-context regression end marker not found')
block = text[start:end]
old = '    assert outcome.iterations_used == 2\n'
new = '    assert outcome.iterations_used == 3\n    assert [entry.status for entry in outcome.trace] == ["request_context", "context_reconciled"]\n'
if old not in block:
    if '    assert outcome.iterations_used == 3\n' in block:
        print('PASS: repeated-context regression already expects one reconciliation turn')
    else:
        raise SystemExit('iterations assertion not found inside repeated-context regression function')
else:
    block = block.replace(old, new, 1)
    text = text[:start] + block + text[end:]
    path.write_text(text)
    print(f'UPDATED: {path}')
PY

echo "========== SECTION 3: STATIC VALIDATION =========="
git diff --check

echo "========== SECTION 4: FOCUSED TESTS =========="
"$PY" -m pytest -q \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_semantic_plan_sufficiency.py \
  implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py

echo "========== SECTION 5: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Repeated-context regression now reflects the intended one-turn reconciliation behavior."
echo "The context reader remains single-read for the repeated request, and a second repeat still fails closed."
echo "NO RUNTIME ACTIVATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC PLANNER CONTEXT RECONCILIATION REGRESSION REPAIR V2 =========="
