#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START RESOURCE EVIDENCE UNAVAILABLE RESPONSE CHECKPOINT =========="
echo "========== SECTION 1: VALIDATE CHANGE SET =========="

allowed=(
  "implementation/orchestrator/resource_evidence.py"
  "implementation/orchestrator/tests/test_resource_evidence.py"
)

mapfile -t changed < <(git status --short | awk '{print $2}' | grep -v '^FETCH_HEAD$' || true)
for path in "${changed[@]}"; do
  ok=false
  for expected in "${allowed[@]}"; do
    if [[ "$path" == "$expected" ]]; then
      ok=true
      break
    fi
  done
  if [[ "$ok" != true ]]; then
    echo "ERROR: unexpected worktree change present: $path"
    exit 20
  fi
done

echo "PASS: local changes are limited to resource evidence unavailable-response handling."

echo "========== SECTION 2: REVALIDATE =========="
git diff --check
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_resource_evidence.py \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py

echo "========== SECTION 3: COMMIT =========="
git add \
  implementation/orchestrator/resource_evidence.py \
  implementation/orchestrator/tests/test_resource_evidence.py

if git diff --cached --quiet; then
  echo "NOTE: no unavailable-response changes are staged; no new commit required."
else
  git commit -m "Render unavailable governed resource evidence safely"
fi

echo "========== SECTION 4: PUSH =========="
branch="$(git branch --show-current)"
echo "Branch: $branch"
git fetch origin "$branch"
local_sha="$(git rev-parse HEAD)"
remote_sha="$(git rev-parse "origin/$branch")"
if [[ "$local_sha" == "$remote_sha" ]]; then
  echo "PASS: local and remote are already synchronized at $(git rev-parse --short HEAD)."
else
  git push origin "$branch"
fi

echo "========== FINAL STATUS =========="
git log -1 --oneline --decorate
echo "PASS: resource evidence unavailable-response handling is durable in GitHub."
echo "NO DEPLOYMENT PERFORMED."
echo "========== END RESOURCE EVIDENCE UNAVAILABLE RESPONSE CHECKPOINT =========="
