#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START BROAD SEMANTIC KNOWLEDGE REGISTRY SEED CHECKPOINT =========="
echo "========== SECTION 1: VALIDATE CHANGE SET =========="

ALLOWED=(
  "implementation/orchestrator/semantic_knowledge_registry.py"
  "implementation/orchestrator/semantic_knowledge_seed.py"
  "implementation/orchestrator/tests/test_semantic_fact_resolver.py"
  "implementation/orchestrator/tests/test_semantic_knowledge_registry.py"
  "implementation/orchestrator/tests/test_semantic_knowledge_seed.py"
)

UNEXPECTED="$(git status --porcelain | while read -r status path; do
  [[ "$path" == "FETCH_HEAD" ]] && continue
  matched=false
  for allowed in "${ALLOWED[@]}"; do
    if [[ "$path" == "$allowed" ]]; then
      matched=true
      break
    fi
  done
  if [[ "$matched" == false ]]; then
    printf '%s %s\n' "$status" "$path"
  fi
done)"

if [[ -n "$UNEXPECTED" ]]; then
  echo "ERROR: unexpected worktree changes present."
  printf '%s\n' "$UNEXPECTED"
  exit 20
fi

echo "PASS: local changes are limited to broad Semantic Knowledge Registry seed work."

echo "========== SECTION 2: REVALIDATE =========="
git diff --check
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_semantic_knowledge_registry.py \
  implementation/orchestrator/tests/test_semantic_knowledge_seed.py \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_conversation_resource_intent.py

echo "========== SECTION 3: COMMIT =========="
git add \
  implementation/orchestrator/semantic_knowledge_registry.py \
  implementation/orchestrator/semantic_knowledge_seed.py \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_knowledge_registry.py \
  implementation/orchestrator/tests/test_semantic_knowledge_seed.py

if git diff --cached --quiet; then
  echo "NOTE: no broad semantic seed changes are staged; no new commit required."
else
  git commit -m "Expand governed Semantic Knowledge Registry seed"
fi

echo "========== SECTION 4: PUSH =========="
BRANCH="$(git branch --show-current)"
echo "Branch: $BRANCH"
git fetch origin "$BRANCH"
LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse "origin/$BRANCH")"
if [[ "$LOCAL" == "$REMOTE" ]]; then
  echo "PASS: local and remote are already synchronized at $(git rev-parse --short HEAD)."
else
  BASE="$(git merge-base HEAD "origin/$BRANCH")"
  if [[ "$BASE" != "$REMOTE" ]]; then
    echo "ERROR: local branch is not a fast-forward of origin/$BRANCH."
    exit 21
  fi
  echo "Local branch is ahead of remote. Ready to push."
  git push origin "$BRANCH"
fi

echo "========== FINAL STATUS =========="
git log -1 --oneline --decorate
echo "PASS: broad Semantic Knowledge Registry seed is durable in GitHub."
echo "========== END BROAD SEMANTIC KNOWLEDGE REGISTRY SEED CHECKPOINT =========="
