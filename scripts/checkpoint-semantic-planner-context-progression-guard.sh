#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC PLANNER CONTEXT PROGRESSION GUARD CHECKPOINT =========="
echo "========== SECTION 1: VALIDATE CHANGE SET =========="
STATUS="$(git status --short)"
printf '%s\n' "$STATUS"
if printf '%s\n' "$STATUS" | grep -Ev '^\?\? FETCH_HEAD$|^ M implementation/orchestrator/ollama_semantic_intent_planning.py$|^ M implementation/orchestrator/semantic_intent_planning_loop.py$|^ M implementation/orchestrator/tests/test_semantic_intent_planning_loop.py$|^ M scripts/run-live-observe-only-semantic-planner-intent-probe.sh$' | grep -q .; then
  echo "ERROR: unexpected worktree changes are present."
  exit 20
fi

echo "PASS: local changes are limited to semantic planner context progression and the observe-only probe contract repairs."

echo "========== SECTION 2: REVALIDATE =========="
git diff --check
/home/al/projects/jason/.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py \
  implementation/orchestrator/tests/test_planning_context_reader.py \
  implementation/runtime_service/tests/test_semantic_planner_observe_only_probe.py

echo "========== SECTION 3: COMMIT =========="
git add \
  implementation/orchestrator/ollama_semantic_intent_planning.py \
  implementation/orchestrator/semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  scripts/run-live-observe-only-semantic-planner-intent-probe.sh

if git diff --cached --quiet; then
  echo "PASS: no staged changes remain; target work is already durable locally."
else
  git commit -m "Require forward progression in semantic planning"
fi

echo "========== SECTION 4: PUSH =========="
BRANCH="$(git branch --show-current)"
echo "Branch: $BRANCH"
git fetch origin "$BRANCH"
REMOTE="$(git rev-parse "origin/$BRANCH")"
BASE="$(git merge-base HEAD "origin/$BRANCH")"
if [ "$BASE" != "$REMOTE" ]; then
  echo "ERROR: remote branch contains commits not in local HEAD."
  exit 21
fi
if [ "$(git rev-parse HEAD)" != "$REMOTE" ]; then
  git push origin "$BRANCH"
else
  echo "PASS: remote branch already matches local HEAD."
fi

echo "========== FINAL STATUS =========="
git log -1 --oneline --decorate
echo "PASS: semantic planner context progression guard is durable in GitHub."
echo "Planner remains observe-only and disconnected from execution."
echo "NO RUNTIME ACTIVATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "========== END SEMANTIC PLANNER CONTEXT PROGRESSION GUARD CHECKPOINT =========="
