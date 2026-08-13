#!/usr/bin/env bash
set -euo pipefail

printf '%s\n' '========== START OLLAMA SEMANTIC INTENT PLANNING REASONER CHECKPOINT =========='
printf '%s\n' '========== SECTION 1: VALIDATE CHANGE SET =========='
allowed='implementation/orchestrator/ollama_semantic_intent_planning.py|implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py|FETCH_HEAD'
if git status --short | awk '{$1=""; sub(/^ /, ""); print}' | grep -Ev "^(${allowed})$" | grep -q .; then
  echo 'FAIL: unexpected local changes detected.'
  git status --short
  exit 1
fi
echo 'PASS: local changes are limited to Ollama semantic intent planning reasoner.'

printf '%s\n' '========== SECTION 2: REVALIDATE =========='
git diff --check
/home/al/projects/jason/.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_planning_context_views.py \
  implementation/orchestrator/tests/test_planning_context_reader.py \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_semantic_knowledge_registry.py

printf '%s\n' '========== SECTION 3: COMMIT =========='
git add \
  implementation/orchestrator/ollama_semantic_intent_planning.py \
  implementation/orchestrator/tests/test_ollama_semantic_intent_planning.py
git commit -m 'Add bounded Ollama semantic intent planning reasoner'

printf '%s\n' '========== SECTION 4: PUSH =========='
branch="$(git branch --show-current)"
echo "Branch: $branch"
git fetch origin "$branch"
if git merge-base --is-ancestor "origin/$branch" HEAD; then
  echo 'Local branch is ahead of remote. Ready to push.'
else
  echo 'FAIL: remote branch contains changes not in local HEAD.'
  exit 1
fi
git push origin "$branch"

printf '%s\n' '========== FINAL STATUS =========='
git log -1 --oneline --decorate
echo 'PASS: Ollama semantic intent planning reasoner is durable in GitHub.'
echo 'NO RUNTIME WIRING PERFORMED.'
echo 'NO DEPLOYMENT PERFORMED.'
printf '%s\n' '========== END OLLAMA SEMANTIC INTENT PLANNING REASONER CHECKPOINT =========='
