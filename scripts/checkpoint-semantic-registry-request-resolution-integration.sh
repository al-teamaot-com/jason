#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC REGISTRY REQUEST RESOLUTION INTEGRATION CHECKPOINT =========="
echo "========== SECTION 1: VALIDATE CHANGE SET =========="

EXPECTED=(
  "implementation/orchestrator/semantic_knowledge_registry.py"
  "implementation/orchestrator/semantic_fact_resolver.py"
  "implementation/orchestrator/tests/test_semantic_fact_resolver.py"
)

UNEXPECTED="$(git status --porcelain | grep -v '^?? FETCH_HEAD$' | while read -r status path; do
  matched=0
  for expected in "${EXPECTED[@]}"; do
    if [[ "$path" == "$expected" ]]; then matched=1; break; fi
  done
  if [[ $matched -eq 0 ]]; then printf '%s %s\n' "$status" "$path"; fi
done)"

if [[ -n "$UNEXPECTED" ]]; then
  echo "ERROR: unexpected worktree changes present."
  printf '%s\n' "$UNEXPECTED"
  exit 20
fi

echo "PASS: local changes are limited to semantic registry request-resolution integration."

echo "========== SECTION 2: REVALIDATE =========="
git diff --check
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_knowledge_registry.py \
  implementation/orchestrator/tests/test_semantic_knowledge_seed.py \
  implementation/orchestrator/tests/test_canonical_fact_vocabulary.py \
  implementation/orchestrator/tests/test_semantic_resource_request.py

echo "========== SECTION 3: COMMIT =========="
git add -- "${EXPECTED[@]}"
if git diff --cached --quiet; then
  echo "NOTE: no semantic registry request-resolution changes are staged; no new commit required."
else
  git commit -m "Add registry-first semantic fact resolution"
fi

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
  echo "ERROR: branch is not a simple fast-forward ahead of origin/$BRANCH."
  exit 21
fi

echo "========== FINAL STATUS =========="
git log -1 --oneline --decorate
echo "PASS: registry-first semantic request fact resolution is durable in GitHub."
echo "========== END SEMANTIC REGISTRY REQUEST RESOLUTION INTEGRATION CHECKPOINT =========="
