#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

BRANCH="feature/jason-runtime-service"
PY="/home/al/projects/jason/.venv/bin/python"

echo "========== START SEMANTIC PLANNER REQUESTABLE CONTEXT POLICY CHECKPOINT =========="
echo "========== SECTION 1: VALIDATE CHANGE SET =========="
git status --short

allowed_paths=(
  "implementation/orchestrator/ollama_semantic_intent_planning.py"
  "implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py"
)

unexpected=()
while IFS= read -r line; do
  [ -z "$line" ] && continue
  path="${line:3}"
  [ "$path" = "FETCH_HEAD" ] && continue
  ok=0
  for allowed in "${allowed_paths[@]}"; do
    if [ "$path" = "$allowed" ]; then
      ok=1
      break
    fi
  done
  if [ "$ok" -ne 1 ]; then
    unexpected+=("$path")
  fi
done < <(git status --short)

if [ "${#unexpected[@]}" -ne 0 ]; then
  echo "ERROR: unexpected worktree changes detected:"
  printf ' - %s\n' "${unexpected[@]}"
  exit 20
fi

echo "PASS: local changes are limited to semantic planner requestable-context policy."

if [ ! -x "$PY" ]; then
  echo "ERROR: project Python not found at $PY"
  exit 21
fi

echo "========== SECTION 2: REVALIDATE =========="
git diff --check
"$PY" -m pytest -q \
  implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_semantic_plan_sufficiency.py \
  implementation/orchestrator/tests/test_semantic_planning_bootstrap.py

echo "========== SECTION 3: COMMIT =========="
git add \
  implementation/orchestrator/ollama_semantic_intent_planning.py \
  implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py

if git diff --cached --quiet; then
  echo "PASS: requestable-context policy already durable; nothing new to commit."
else
  git commit -m "Enforce requestable context in semantic planning"
fi

echo "========== SECTION 4: PUSH =========="
git fetch origin "$BRANCH"
if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/$BRANCH)" ]; then
  git push origin "$BRANCH"
else
  echo "PASS: branch already synchronized with origin."
fi

echo "========== FINAL STATUS =========="
git log -1 --oneline --decorate
echo "PASS: semantic planner requestable-context policy is durable in GitHub."
echo "Planner remains observe-only and disconnected from execution."
echo "NO RUNTIME ACTIVATION PERFORMED."
echo "NO DEPLOYMENT PERFORMED."
echo "========== END SEMANTIC PLANNER REQUESTABLE CONTEXT POLICY CHECKPOINT =========="
