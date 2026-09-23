#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' '========== START GOVERNED PLANNING CONTEXT READER CHECKPOINT =========='
printf '%s\n' '========== SECTION 1: VALIDATE CHANGE SET =========='
status=$(git status --short)
allowed='implementation/orchestrator/planning_context_reader.py
implementation/orchestrator/tests/test_planning_context_reader.py'
while IFS= read -r line; do
  [ -z "$line" ] && continue
  path=${line#?? }
  [ "$path" = 'FETCH_HEAD' ] && continue
  if ! printf '%s\n' "$allowed" | grep -Fxq "$path"; then
    printf 'FAIL: unexpected worktree change: %s\n' "$line" >&2
    exit 1
  fi
done <<EOF
$status
EOF
printf '%s\n' 'PASS: local changes are limited to governed planning context reader integration.'

printf '%s\n' '========== SECTION 2: REVALIDATE =========='
git diff --check
/home/al/projects/jason/.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_planning_context_views.py \
  implementation/orchestrator/tests/test_planning_context_reader.py \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_semantic_knowledge_registry.py

printf '%s\n' '========== SECTION 3: COMMIT =========='
git add \
  implementation/orchestrator/planning_context_reader.py \
  implementation/orchestrator/tests/test_planning_context_reader.py
git commit -m 'Adapt governed context catalog to semantic planning loop'

printf '%s\n' '========== SECTION 4: PUSH =========='
printf 'Branch: '
git branch --show-current
git fetch origin feature/jason-runtime-service
if git merge-base --is-ancestor origin/feature/jason-runtime-service HEAD; then
  printf '%s\n' 'Local branch is ahead of remote. Ready to push.'
else
  printf '%s\n' 'FAIL: local branch is not a fast-forward of origin/feature/jason-runtime-service.' >&2
  exit 1
fi
git push origin feature/jason-runtime-service

printf '%s\n' '========== FINAL STATUS =========='
git log -1 --oneline --decorate
printf '%s\n' 'PASS: governed planning context reader integration is durable in GitHub.'
printf '%s\n' 'NO DEPLOYMENT PERFORMED.'
printf '%s\n' '========== END GOVERNED PLANNING CONTEXT READER CHECKPOINT =========='
