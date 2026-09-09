#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC PLANNER CONTEXT RECONCILIATION REGRESSION REPAIR =========="
echo "========== SECTION 1: CURRENT STATE =========="
git rev-parse --short HEAD
git status --short

PY="/home/al/projects/jason/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "ERROR: project Python not found at $PY"
  exit 20
fi

echo "========== SECTION 2: ALIGN STALE REGRESSION WITH ONE-TURN RECONCILIATION =========="
"$PY" - <<'PY'
from pathlib import Path

path = Path('implementation/orchestrator/tests/test_semantic_intent_planning_loop.py')
text = path.read_text()
old = '''    assert outcome.status == "knowledge_gap"\n    assert outcome.context_requests_used == 1\n    assert outcome.iterations_used == 2\n    assert reader.calls == 1\n    assert "already-satisfied" in str(outcome.gap_summary)\n'''
new = '''    assert outcome.status == "knowledge_gap"\n    assert outcome.context_requests_used == 1\n    assert outcome.iterations_used == 3\n    assert reader.calls == 1\n    assert tuple(item.status for item in outcome.trace) == (\n        "request_context",\n        "context_reconciled",\n    )\n    assert "already-satisfied" in str(outcome.gap_summary)\n'''
if old not in text:
    raise SystemExit('stale repeated-context regression marker not found')
path.write_text(text.replace(old, new, 1))
print(f'UPDATED: {path}')
PY

echo "========== SECTION 3: STATIC VALIDATION =========="
git diff --check

echo "========== SECTION 4: FOCUSED TESTS =========="
"$PY" -m pytest -q \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py \
  implementation/orchestrator/tests/test_semantic_plan_sufficiency.py \
  implementation/orchestrator/tests/test_semantic_planning_bootstrap.py

echo "========== SECTION 5: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Satisfied-context reconciliation regression now expects exactly one reconciliation turn before fail-closed repetition handling."
echo "No implementation behavior was weakened or broadened by this repair."
echo "NO RUNTIME ACTIVATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC PLANNER CONTEXT RECONCILIATION REGRESSION REPAIR =========="
