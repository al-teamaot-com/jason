#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START DATTO SEMANTIC EQUIVALENT PROVIDER VALUE CHECKPOINT =========="

echo "========== SECTION 1: VALIDATE CHANGE SET =========="
EXPECTED=(
  "implementation/connectors/datto_rmm/semantic_evidence.py"
  "implementation/connectors/tests/test_datto_semantic_evidence.py"
)

mapfile -t CHANGED < <(git status --short | awk '{print $2}' | grep -v '^FETCH_HEAD$' || true)
for path in "${CHANGED[@]}"; do
  ok=0
  for expected in "${EXPECTED[@]}"; do
    if [[ "$path" == "$expected" ]]; then
      ok=1
      break
    fi
  done
  if [[ "$ok" -ne 1 ]]; then
    echo "ERROR: unexpected worktree change: $path"
    exit 20
  fi
done

echo "PASS: local changes are limited to Datto semantic equivalent provider value handling."

echo "========== SECTION 2: REVALIDATE =========="
git diff --check
.venv/bin/python -m pytest -q \
  implementation/connectors/tests/test_datto_semantic_evidence.py \
  implementation/orchestrator/tests/test_resource_evidence.py

echo "========== SECTION 3: COMMIT =========="
git add \
  implementation/connectors/datto_rmm/semantic_evidence.py \
  implementation/connectors/tests/test_datto_semantic_evidence.py

if git diff --cached --quiet; then
  echo "NOTE: no Datto semantic equivalent-value changes are staged; no new commit required."
else
  git commit -m "Collapse equivalent Datto semantic evidence aliases"
fi

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

if [[ "$LOCAL" == "$REMOTE" ]]; then
  echo "PASS: local and remote are already synchronized at $(git rev-parse --short HEAD)."
elif [[ "$BASE" == "$REMOTE" ]]; then
  git push origin "$BRANCH"
else
  echo "ERROR: local branch and origin/$BRANCH have diverged."
  exit 22
fi

echo "========== FINAL STATUS =========="
git log -1 --oneline --decorate
echo "PASS: Datto semantic equivalent provider value handling is durable in GitHub."
echo "========== END DATTO SEMANTIC EQUIVALENT PROVIDER VALUE CHECKPOINT =========="
