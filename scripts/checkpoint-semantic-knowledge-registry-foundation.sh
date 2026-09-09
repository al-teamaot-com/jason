#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC KNOWLEDGE REGISTRY FOUNDATION CHECKPOINT =========="

echo "========== SECTION 1: VALIDATE CHANGE SET =========="
EXPECTED=$(cat <<'EOF'
implementation/orchestrator/semantic_knowledge_registry.py
implementation/orchestrator/tests/test_semantic_knowledge_registry.py
EOF
)

ACTUAL="$(git status --porcelain | awk '{print $2}' | grep -v '^FETCH_HEAD$' | sort || true)"
EXPECTED_SORTED="$(printf '%s\n' "$EXPECTED" | sort)"

if [[ "$ACTUAL" != "$EXPECTED_SORTED" ]]; then
  echo "ERROR: unexpected worktree changes present."
  git status --short
  exit 20
fi

echo "PASS: local changes are limited to Semantic Knowledge Registry foundation."

echo "========== SECTION 2: REVALIDATE =========="
git diff --check
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_semantic_knowledge_registry.py \
  implementation/orchestrator/tests/test_canonical_fact_vocabulary.py \
  implementation/orchestrator/tests/test_semantic_resource_request.py

echo "========== SECTION 3: COMMIT =========="
git add \
  implementation/orchestrator/semantic_knowledge_registry.py \
  implementation/orchestrator/tests/test_semantic_knowledge_registry.py

git commit -m "Add governed Semantic Knowledge Registry foundation"

echo "========== SECTION 4: PUSH =========="
BRANCH="$(git branch --show-current)"
if [[ "$BRANCH" != "feature/jason-runtime-service" ]]; then
  echo "ERROR: expected feature/jason-runtime-service, found $BRANCH"
  exit 21
fi

git fetch origin "$BRANCH"
LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse "origin/$BRANCH")"
BASE="$(git merge-base HEAD "origin/$BRANCH")"

if [[ "$BASE" != "$REMOTE" ]]; then
  echo "ERROR: local branch is not a fast-forward of origin/$BRANCH."
  exit 22
fi

git push origin "$BRANCH"

echo "========== FINAL STATUS =========="
git log -1 --oneline --decorate
echo "PASS: Semantic Knowledge Registry foundation is durable in GitHub."
echo "========== END SEMANTIC KNOWLEDGE REGISTRY FOUNDATION CHECKPOINT =========="
