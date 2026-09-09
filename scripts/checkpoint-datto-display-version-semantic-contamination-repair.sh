#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START DATTO DISPLAY VERSION SEMANTIC CONTAMINATION REPAIR CHECKPOINT =========="
echo "========== SECTION 1: VALIDATE CHANGE SET =========="

EXPECTED_FILES=(
  "implementation/connectors/datto_rmm/semantic_evidence.py"
  "implementation/connectors/tests/test_datto_semantic_evidence.py"
  "implementation/orchestrator/semantic_knowledge_seed.py"
  "implementation/orchestrator/tests/test_semantic_knowledge_seed.py"
)

mapfile -t DIRTY_FILES < <(git status --porcelain | awk '{print $2}' | grep -v '^FETCH_HEAD$' | sort -u)
mapfile -t EXPECTED_SORTED < <(printf '%s\n' "${EXPECTED_FILES[@]}" | sort -u)

if [[ "$(printf '%s\n' "${DIRTY_FILES[@]}")" != "$(printf '%s\n' "${EXPECTED_SORTED[@]}")" ]]; then
  echo "ERROR: unexpected worktree change set."
  echo "Expected:"
  printf '  %s\n' "${EXPECTED_SORTED[@]}"
  echo "Actual:"
  printf '  %s\n' "${DIRTY_FILES[@]}"
  exit 20
fi

echo "PASS: local changes are limited to Datto display-version semantic contamination repair."

echo "========== SECTION 2: REVALIDATE =========="
git diff --check
.venv/bin/python -m pytest -q \
  implementation/connectors/tests/test_datto_semantic_evidence.py \
  implementation/orchestrator/tests/test_semantic_knowledge_registry.py \
  implementation/orchestrator/tests/test_semantic_knowledge_seed.py \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_conversation_resource_intent.py

echo "========== SECTION 3: COMMIT =========="
git add \
  implementation/connectors/datto_rmm/semantic_evidence.py \
  implementation/connectors/tests/test_datto_semantic_evidence.py \
  implementation/orchestrator/semantic_knowledge_seed.py \
  implementation/orchestrator/tests/test_semantic_knowledge_seed.py

git commit -m "Remove false Datto display version semantic mapping"

echo "========== SECTION 4: PUSH =========="
BRANCH="$(git branch --show-current)"
echo "Branch: $BRANCH"
git fetch origin "$BRANCH"
if ! git merge-base --is-ancestor "origin/$BRANCH" HEAD; then
  echo "ERROR: remote branch is not an ancestor of local HEAD. Refusing push."
  exit 30
fi
git push origin "$BRANCH"

echo "========== FINAL STATUS =========="
git log -1 --oneline --decorate
if [[ -n "$(git status --porcelain | grep -v '^?? FETCH_HEAD$' || true)" ]]; then
  echo "ERROR: unexpected remaining worktree changes after checkpoint."
  git status --short
  exit 40
fi

echo "PASS: Datto display-version semantic contamination repair is durable in GitHub."
echo "NO DEPLOYMENT PERFORMED."
echo "========== END DATTO DISPLAY VERSION SEMANTIC CONTAMINATION REPAIR CHECKPOINT =========="
