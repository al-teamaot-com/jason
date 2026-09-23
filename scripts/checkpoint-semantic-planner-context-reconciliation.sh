#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

BRANCH="feature/jason-runtime-service"
PY="/home/al/projects/jason/.venv/bin/python"

echo "========== START SEMANTIC PLANNER CONTEXT RECONCILIATION CHECKPOINT =========="
echo "========== SECTION 1: VALIDATE CHANGE SET =========="
git status --short

unexpected="$(git status --short | awk '{print $2}' | grep -v '^FETCH_HEAD$' | grep -v '^implementation/orchestrator/ollama_semantic_intent_planning.py$' | grep -v '^implementation/orchestrator/semantic_intent_planning_loop.py$' | grep -v '^implementation/orchestrator/tests/test_semantic_intent_planning_loop.py$' || true)"
if [ -n "$unexpected" ]; then
  echo "ERROR: unexpected worktree changes detected:"
  printf '%s\n' "$unexpected"
  exit 20
fi

echo "PASS: local changes are limited to semantic planner satisfied-context reconciliation."

echo "========== SECTION 2: REVALIDATE =========="
git diff --check
"$PY" -m pytest -q \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py \
  implementation/orchestrator/tests/test_semantic_plan_sufficiency.py

echo "========== SECTION 3: COMMIT =========="
git add \
  implementation/orchestrator/ollama_semantic_intent_planning.py \
  implementation/orchestrator/semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py

if git diff --cached --quiet; then
  echo "PASS: no new reconciliation changes remain to commit; target state is already durable locally."
else
  git commit -m "Reconcile satisfied context during semantic planning"
fi

echo "========== SECTION 4: PUSH =========="
git fetch origin "$BRANCH"
if [ "$(git rev-parse HEAD)" = "$(git rev-parse origin/$BRANCH)" ]; then
  echo "PASS: branch already matches origin/$BRANCH."
else
  git push origin "$BRANCH"
fi

echo "========== FINAL STATUS =========="
git log -1 --oneline --decorate
if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/$BRANCH)" ]; then
  echo "ERROR: local HEAD does not match origin/$BRANCH after checkpoint."
  exit 21
fi

echo "PASS: satisfied-context reconciliation is durable in GitHub."
echo "Planner remains observe-only and disconnected from execution."
echo "NO RUNTIME ACTIVATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "========== END SEMANTIC PLANNER CONTEXT RECONCILIATION CHECKPOINT =========="
