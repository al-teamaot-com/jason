#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' '========== START DISABLED SEMANTIC PLANNER RUNTIME COMPOSITION CHECKPOINT =========='
printf '%s\n' '========== SECTION 1: VALIDATE CHANGE SET =========='
allowed_re='^(implementation/runtime_service/src/jason_runtime/composition.py|implementation/runtime_service/tests/test_semantic_planner_composition.py|FETCH_HEAD)$'
unexpected="$(git status --short | awk '{print $2}' | grep -Ev "$allowed_re" || true)"
if [ -n "$unexpected" ]; then
  printf '%s\n' 'FAIL: unexpected local changes present:'
  printf '%s\n' "$unexpected"
  exit 1
fi
printf '%s\n' 'PASS: local changes are limited to disabled semantic planner runtime composition.'

printf '%s\n' '========== SECTION 2: REVALIDATE =========='
git diff --check
/home/al/projects/jason/.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_planning_context_views.py \
  implementation/orchestrator/tests/test_planning_context_reader.py \
  implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py \
  implementation/runtime_service/tests/test_semantic_planner_composition.py

printf '%s\n' '========== SECTION 3: COMMIT =========='
git add \
  implementation/runtime_service/src/jason_runtime/composition.py \
  implementation/runtime_service/tests/test_semantic_planner_composition.py
if git diff --cached --quiet; then
  printf '%s\n' 'No staged source changes to commit.'
else
  git commit -m 'Compose semantic planner behind disabled runtime flag'
fi

printf '%s\n' '========== SECTION 4: PUSH =========='
branch="$(git branch --show-current)"
printf 'Branch: %s\n' "$branch"
git fetch origin "$branch"
if git merge-base --is-ancestor "origin/$branch" HEAD; then
  git push origin "$branch"
else
  printf '%s\n' 'FAIL: local branch is not a fast-forward of origin.'
  exit 1
fi

printf '%s\n' '========== FINAL STATUS =========='
git log -1 --oneline --decorate
printf '%s\n' 'PASS: disabled semantic planner runtime composition is durable in GitHub.'
printf '%s\n' 'Planner remains disabled by default and disconnected from execution.'
printf '%s\n' 'NO RUNTIME ACTIVATION PERFORMED.'
printf '%s\n' 'NO DEPLOYMENT PERFORMED.'
printf '%s\n' '========== END DISABLED SEMANTIC PLANNER RUNTIME COMPOSITION CHECKPOINT =========='
