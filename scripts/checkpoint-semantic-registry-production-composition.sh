#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC REGISTRY PRODUCTION COMPOSITION CHECKPOINT =========="
echo "========== SECTION 1: VALIDATE CHANGE SET =========="

DIRTY="$(git status --porcelain | grep -v '^?? FETCH_HEAD$' || true)"
EXPECTED=$(cat <<'EOF'
 M implementation/orchestrator/conversation_resource_intent.py
 M implementation/orchestrator/tests/test_conversation_resource_intent.py
 M implementation/runtime_service/src/jason_runtime/composition.py
EOF
)

if [[ "$(printf '%s\n' "$DIRTY" | sort)" != "$(printf '%s\n' "$EXPECTED" | sort)" ]]; then
  echo "ERROR: unexpected worktree changes present."
  git status --short
  exit 20
fi

echo "PASS: local changes are limited to semantic registry production composition wiring."

echo "========== SECTION 2: REVALIDATE =========="
git diff --check
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_conversation_resource_intent.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_knowledge_seed.py \
  implementation/runtime_service/tests

echo "========== SECTION 3: COMMIT =========="
git add \
  implementation/orchestrator/conversation_resource_intent.py \
  implementation/orchestrator/tests/test_conversation_resource_intent.py \
  implementation/runtime_service/src/jason_runtime/composition.py

git commit -m "Use semantic registry in production resource interpretation"

echo "========== SECTION 4: PUSH =========="
BRANCH="$(git branch --show-current)"
echo "Branch: $BRANCH"
git fetch origin "$BRANCH"
LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse "origin/$BRANCH")"
BASE="$(git merge-base HEAD "origin/$BRANCH")"
if [[ "$LOCAL" == "$REMOTE" ]]; then
  echo "PASS: local and remote are already synchronized at $(git rev-parse --short HEAD)."
elif [[ "$BASE" == "$REMOTE" ]]; then
  echo "Local branch is ahead of remote. Ready to push."
  git push origin "$BRANCH"
else
  echo "ERROR: local branch is not a clean fast-forward from origin/$BRANCH."
  exit 21
fi

echo "========== FINAL STATUS =========="
git log -1 --oneline --decorate
echo "PASS: semantic registry production composition wiring is durable in GitHub."
echo "NO DEPLOYMENT PERFORMED."
echo "========== END SEMANTIC REGISTRY PRODUCTION COMPOSITION CHECKPOINT =========="
