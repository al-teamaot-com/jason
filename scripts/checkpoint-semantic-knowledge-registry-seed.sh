#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC KNOWLEDGE REGISTRY SEED CHECKPOINT =========="

echo "========== SECTION 1: VALIDATE CHANGE SET =========="
DIRTY="$(git status --porcelain | grep -v '^?? FETCH_HEAD$' || true)"
ALLOWED_RE='^( M|M |A |\?\?) implementation/orchestrator/(semantic_knowledge_registry.py|semantic_knowledge_seed.py|tests/test_semantic_knowledge_registry.py|tests/test_semantic_knowledge_seed.py)$'
UNEXPECTED="$(printf '%s\n' "$DIRTY" | grep -Ev "$ALLOWED_RE" || true)"
if [[ -n "$UNEXPECTED" ]]; then
  echo "ERROR: unexpected worktree changes present."
  printf '%s\n' "$UNEXPECTED"
  exit 20
fi
if [[ -z "$DIRTY" ]]; then
  echo "ERROR: expected semantic registry seed changes are not present."
  exit 21
fi
echo "PASS: local changes are limited to the Semantic Knowledge Registry seed workstream."

echo "========== SECTION 2: REVALIDATE =========="
git diff --check
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_semantic_knowledge_registry.py \
  implementation/orchestrator/tests/test_semantic_knowledge_seed.py \
  implementation/orchestrator/tests/test_canonical_fact_vocabulary.py \
  implementation/orchestrator/tests/test_semantic_resource_request.py

echo "========== SECTION 3: COMMIT =========="
git add \
  implementation/orchestrator/semantic_knowledge_registry.py \
  implementation/orchestrator/semantic_knowledge_seed.py \
  implementation/orchestrator/tests/test_semantic_knowledge_registry.py \
  implementation/orchestrator/tests/test_semantic_knowledge_seed.py

git commit -m "Seed governed Semantic Knowledge Registry"

echo "========== SECTION 4: PUSH =========="
BRANCH="$(git branch --show-current)"
echo "Branch: $BRANCH"
git fetch origin "$BRANCH"
LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse FETCH_HEAD)"
BASE="$(git merge-base HEAD FETCH_HEAD)"
if [[ "$BASE" != "$REMOTE" ]]; then
  echo "ERROR: remote branch is not an ancestor of local HEAD; reconcile before push."
  exit 22
fi
git push origin "$BRANCH"

FINAL="$(git rev-parse --short HEAD)"
echo "========== FINAL STATUS =========="
git log -1 --oneline --decorate
echo "PASS: Semantic Knowledge Registry trusted seed is durable in GitHub at $FINAL."
echo "========== END SEMANTIC KNOWLEDGE REGISTRY SEED CHECKPOINT =========="
