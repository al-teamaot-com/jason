#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC REGISTRY LIVE REQUEST WIRING CHECKPOINT =========="

echo "========== SECTION 1: VALIDATE CHANGE SET =========="
DIRTY="$(git status --porcelain | grep -v '^?? FETCH_HEAD$' || true)"
ALLOWED='^( M implementation/orchestrator/semantic_fact_resolver.py| M implementation/orchestrator/semantic_request_bridge.py| M implementation/orchestrator/tests/test_semantic_fact_resolver.py| M implementation/orchestrator/tests/test_semantic_request_bridge.py)$'
UNEXPECTED="$(printf '%s\n' "$DIRTY" | grep -Ev "$ALLOWED" || true)"
if [[ -n "$UNEXPECTED" ]]; then
  echo "ERROR: unexpected worktree changes present."
  printf '%s\n' "$UNEXPECTED"
  exit 20
fi

echo "PASS: local changes are limited to semantic registry live request wiring."

echo "========== SECTION 2: REVALIDATE =========="
git diff --check
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_knowledge_seed.py \
  implementation/orchestrator/tests/test_conversation_resource_intent.py

echo "========== SECTION 3: COMMIT =========="
git add \
  implementation/orchestrator/semantic_fact_resolver.py \
  implementation/orchestrator/semantic_request_bridge.py \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py

if git diff --cached --quiet; then
  echo "NOTE: no semantic registry live request wiring changes are staged; no new commit required."
else
  git commit -m "Wire semantic registry into request interpretation"
fi

echo "========== SECTION 4: PUSH =========="
BRANCH="$(git branch --show-current)"
echo "Branch: $BRANCH"
git fetch origin "$BRANCH"
LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse "origin/$BRANCH")"
if [[ "$LOCAL" == "$REMOTE" ]]; then
  echo "PASS: local and remote are already synchronized at $(git rev-parse --short HEAD)."
elif git merge-base --is-ancestor "$REMOTE" "$LOCAL"; then
  echo "Local branch is ahead of remote. Ready to push."
  git push origin "$BRANCH"
else
  echo "ERROR: branch is not a simple fast-forward over origin/$BRANCH."
  exit 21
fi

echo "========== FINAL STATUS =========="
git log -1 --oneline --decorate
if [[ -n "$(git status --porcelain | grep -v '^?? FETCH_HEAD$' || true)" ]]; then
  echo "ERROR: tracked worktree is not clean after checkpoint."
  git status --short
  exit 22
fi

echo "PASS: semantic registry live request wiring is durable in GitHub."
echo "========== END SEMANTIC REGISTRY LIVE REQUEST WIRING CHECKPOINT =========="
