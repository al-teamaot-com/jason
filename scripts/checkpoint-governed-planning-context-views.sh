#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START GOVERNED PLANNING CONTEXT VIEWS CHECKPOINT =========="
echo "========== SECTION 1: VALIDATE CHANGE SET =========="
allowed='^(implementation/orchestrator/planning_context_views.py|implementation/orchestrator/tests/test_planning_context_views.py)$'
unexpected="$(git status --short | awk '{print $2}' | grep -Ev "$allowed|^FETCH_HEAD$" || true)"
if [ -n "$unexpected" ]; then
  echo "ERROR: unexpected worktree changes present."
  printf '%s\n' "$unexpected"
  exit 20
fi

echo "PASS: local changes are limited to governed planning context views."

echo "========== SECTION 2: REVALIDATE =========="
git diff --check
/home/al/projects/jason/.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_planning_context_views.py \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_semantic_knowledge_registry.py \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py

echo "========== SECTION 3: COMMIT =========="
git add \
  implementation/orchestrator/planning_context_views.py \
  implementation/orchestrator/tests/test_planning_context_views.py
if git diff --cached --quiet; then
  echo "NOTE: no governed planning context view changes are staged; no new commit required."
else
  git commit -m "Add governed semantic planning context views"
fi

echo "========== SECTION 4: PUSH =========="
branch="$(git branch --show-current)"
echo "Branch: $branch"
git fetch origin "$branch"
local_sha="$(git rev-parse HEAD)"
remote_sha="$(git rev-parse "origin/$branch")"
base_sha="$(git merge-base HEAD "origin/$branch")"
if [ "$local_sha" = "$remote_sha" ]; then
  echo "PASS: local and remote are already synchronized at ${local_sha:0:7}."
elif [ "$base_sha" = "$remote_sha" ]; then
  echo "Local branch is ahead of remote. Ready to push."
  git push origin "$branch"
else
  echo "ERROR: local and remote histories diverged; refusing automatic push."
  exit 30
fi

echo "========== FINAL STATUS =========="
git log -1 --oneline --decorate
echo "PASS: governed planning context views are durable in GitHub."
echo "NO DEPLOYMENT PERFORMED."
echo "========== END GOVERNED PLANNING CONTEXT VIEWS CHECKPOINT =========="
