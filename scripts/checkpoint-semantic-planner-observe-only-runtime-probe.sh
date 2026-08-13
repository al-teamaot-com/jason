#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC PLANNER OBSERVE-ONLY RUNTIME PROBE CHECKPOINT =========="
echo "========== SECTION 1: VALIDATE CHANGE SET =========="
STATUS="$(git status --short)"
printf '%s\n' "$STATUS"

UNEXPECTED="$(printf '%s\n' "$STATUS" | grep -vE '^\?\? FETCH_HEAD$|^\?\? implementation/runtime_service/tests/test_semantic_planner_observe_only_probe.py$' || true)"
if [ -n "$UNEXPECTED" ]; then
  echo "ERROR: unexpected worktree changes detected:"
  printf '%s\n' "$UNEXPECTED"
  exit 20
fi

echo "PASS: local changes are limited to semantic planner observe-only runtime probe coverage."

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
LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse "origin/$BRANCH")"
BASE="$(git merge-base HEAD "origin/$BRANCH")"
if [ "$BASE" != "$REMOTE" ]; then
  echo "ERROR: local branch is not a clean fast-forward continuation of origin/$BRANCH."
  exit 30
fi
git push origin "$BRANCH"

echo "========== FINAL STATUS =========="
git log -1 --oneline --decorate
echo "PASS: observe-only semantic planner two-turn planning probe is durable in GitHub."
echo "Planner remains disconnected from execution and production traffic."
echo "NO RUNTIME ACTIVATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "========== END SEMANTIC PLANNER OBSERVE-ONLY RUNTIME PROBE CHECKPOINT =========="
