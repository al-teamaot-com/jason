#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START OBSERVE-ONLY SEMANTIC PLANNER PROBE CHECKPOINT =========="
echo "========== SECTION 1: VALIDATE CHANGE SET =========="
STATUS="$(git status --short)"
printf '%s\n' "$STATUS"
if printf '%s\n' "$STATUS" | grep -Ev '^\?\? FETCH_HEAD$|^\?\? implementation/runtime_service/tests/test_semantic_planner_observe_only_probe.py$' | grep -q .; then
  echo "ERROR: unexpected worktree changes are present."
  exit 20
fi
if [ ! -f implementation/runtime_service/tests/test_semantic_planner_observe_only_probe.py ]; then
  echo "ERROR: observe-only probe test file is missing."
  exit 21
fi
echo "PASS: local changes are limited to observe-only semantic planner probe coverage."

echo "========== SECTION 2: REVALIDATE =========="
git diff --check
/home/al/projects/jason/.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_planning_context_views.py \
  implementation/orchestrator/tests/test_planning_context_reader.py \
  implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py \
  implementation/runtime_service/tests/test_semantic_planner_composition.py \
  implementation/runtime_service/tests/test_semantic_planner_observe_only_probe.py

echo "========== SECTION 3: COMMIT =========="
git add implementation/runtime_service/tests/test_semantic_planner_observe_only_probe.py
git commit -m "Validate observe-only semantic planning cycle"

echo "========== SECTION 4: PUSH =========="
BRANCH="$(git branch --show-current)"
echo "Branch: $BRANCH"
git fetch origin "$BRANCH"
REMOTE="$(git rev-parse "origin/$BRANCH")"
BASE="$(git merge-base HEAD "origin/$BRANCH")"
if [ "$BASE" != "$REMOTE" ]; then
  echo "ERROR: remote branch contains commits not in local HEAD."
  exit 22
fi
git push origin "$BRANCH"

echo "========== FINAL STATUS =========="
git log -1 --oneline --decorate
echo "PASS: observe-only semantic planner probe is durable in GitHub."
echo "Planner remains disconnected from execution and production traffic."
echo "NO RUNTIME ACTIVATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "========== END OBSERVE-ONLY SEMANTIC PLANNER PROBE CHECKPOINT =========="
