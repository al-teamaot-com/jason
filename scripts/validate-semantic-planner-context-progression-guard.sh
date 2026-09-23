#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC PLANNER CONTEXT PROGRESSION GUARD VALIDATION =========="
echo "========== SECTION 1: PRECONDITIONS =========="
git rev-parse --short HEAD
git status --short

PY="/home/al/projects/jason/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "ERROR: project Python not found at $PY"
  exit 20
fi

echo "========== SECTION 2: STATIC VALIDATION =========="
git diff --check

echo "========== SECTION 3: FOCUSED TESTS =========="
"$PY" -m pytest -q \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py \
  implementation/orchestrator/tests/test_planning_context_reader.py \
  implementation/runtime_service/tests/test_semantic_planner_observe_only_probe.py

echo "========== SECTION 4: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Semantic planner context progression guard validated with real static and focused test execution."
echo "NO RUNTIME ACTIVATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC PLANNER CONTEXT PROGRESSION GUARD VALIDATION =========="
