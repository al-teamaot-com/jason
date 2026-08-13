#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START GOVERNED SEMANTIC PLANNER BOOTSTRAP CONTEXT CHECKPOINT =========="
echo "========== SECTION 1: VALIDATE CHANGE SET =========="
STATUS="$(git status --short)"
printf '%s\n' "$STATUS"
if printf '%s\n' "$STATUS" | grep -Ev '^\?\? FETCH_HEAD$|^ M implementation/orchestrator/semantic_intent_planning_loop.py$|^ M implementation/orchestrator/tests/test_semantic_intent_planning_loop.py$|^ M scripts/run-live-observe-only-semantic-planner-intent-probe.sh$|^\?\? implementation/orchestrator/semantic_planning_bootstrap.py$|^\?\? implementation/orchestrator/tests/test_semantic_planning_bootstrap.py$' | grep -q .; then
  echo "ERROR: unexpected worktree changes are present."
  exit 20
fi
for path in \
  implementation/orchestrator/semantic_planning_bootstrap.py \
  implementation/orchestrator/tests/test_semantic_planning_bootstrap.py; do
  if [ ! -f "$path" ]; then
    echo "ERROR: expected bootstrap file is missing: $path"
    exit 21
  fi
done
echo "PASS: local changes are limited to governed semantic planner bootstrap context."

PY="/home/al/projects/jason/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "ERROR: project Python not found at $PY"
  exit 22
fi

echo "========== SECTION 2: REVALIDATE =========="
git diff --check
"$PY" -m pytest -q \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_semantic_planning_bootstrap.py \
  implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py \
  implementation/orchestrator/tests/test_planning_context_reader.py \
  implementation/runtime_service/tests/test_semantic_planner_observe_only_probe.py

echo "========== SECTION 3: COMMIT =========="
git add \
  implementation/orchestrator/semantic_planning_bootstrap.py \
  implementation/orchestrator/semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_semantic_planning_bootstrap.py \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  scripts/run-live-observe-only-semantic-planner-intent-probe.sh

if git diff --cached --quiet; then
  echo "PASS: target bootstrap changes are already committed."
else
  git commit -m "Bootstrap governed semantic planning context"
fi

echo "========== SECTION 4: PUSH =========="
BRANCH="$(git branch --show-current)"
echo "Branch: $BRANCH"
git fetch origin "$BRANCH"
REMOTE="$(git rev-parse "origin/$BRANCH")"
BASE="$(git merge-base HEAD "origin/$BRANCH")"
if [ "$BASE" != "$REMOTE" ]; then
  echo "ERROR: remote branch contains commits not in local HEAD."
  exit 23
fi
if [ "$(git rev-parse HEAD)" = "$REMOTE" ]; then
  echo "PASS: branch is already synchronized."
else
  git push origin "$BRANCH"
fi

echo "========== FINAL STATUS =========="
git log -1 --oneline --decorate
echo "PASS: governed semantic planner bootstrap context is durable in GitHub."
echo "Planner remains observe-only and disconnected from execution."
echo "NO RUNTIME ACTIVATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "========== END GOVERNED SEMANTIC PLANNER BOOTSTRAP CONTEXT CHECKPOINT =========="
