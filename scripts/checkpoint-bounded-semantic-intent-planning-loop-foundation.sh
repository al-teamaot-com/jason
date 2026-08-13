#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START BOUNDED SEMANTIC INTENT PLANNING LOOP FOUNDATION CHECKPOINT =========="
echo "========== SECTION 1: VALIDATE CHANGE SET =========="

allowed=(
  "implementation/orchestrator/semantic_intent_planning_loop.py"
  "implementation/orchestrator/tests/test_semantic_intent_planning_loop.py"
)

mapfile -t changed < <(git status --short | awk '{print $2}' | grep -v '^FETCH_HEAD$' || true)
for path in "${changed[@]}"; do
  ok=false
  for expected in "${allowed[@]}"; do
    if [ "$path" = "$expected" ]; then
      ok=true
      break
    fi
  done
  if [ "$ok" != true ]; then
    echo "ERROR: unexpected worktree change present: $path"
    exit 20
  fi
done

echo "PASS: local changes are limited to bounded semantic intent planning loop foundation."

PY="/home/al/projects/jason/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "ERROR: project Python not found at $PY"
  exit 21
fi

echo "========== SECTION 2: REVALIDATE =========="
git diff --check
"$PY" -m pytest -q \
  implementation/orchestrator/tests/test_semantic_intent_planning_loop.py \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_semantic_knowledge_registry.py

echo "========== SECTION 3: COMMIT =========="
git add -- "${allowed[@]}"
if git diff --cached --quiet; then
  echo "NOTE: no bounded planning-loop changes are staged; no new commit required."
else
  git commit -m "Add bounded semantic intent planning loop foundation"
fi

echo "========== SECTION 4: PUSH =========="
branch="$(git branch --show-current)"
echo "Branch: $branch"
if [ "$branch" != "feature/jason-runtime-service" ]; then
  echo "ERROR: expected feature/jason-runtime-service, found $branch"
  exit 22
fi

git fetch origin "$branch"
local_sha="$(git rev-parse HEAD)"
remote_sha="$(git rev-parse "origin/$branch")"
base_sha="$(git merge-base HEAD "origin/$branch")"
if [ "$local_sha" = "$remote_sha" ]; then
  echo "PASS: local and remote are already synchronized at $(git rev-parse --short HEAD)."
elif [ "$base_sha" = "$remote_sha" ]; then
  echo "Local branch is ahead of remote. Ready to push."
  git push origin "$branch"
else
  echo "ERROR: local and remote have diverged; refusing automatic push."
  exit 23
fi

echo "========== FINAL STATUS =========="
git log -1 --oneline --decorate
echo "PASS: bounded semantic intent planning loop foundation is durable in GitHub."
echo "NO DEPLOYMENT PERFORMED."
echo "========== END BOUNDED SEMANTIC INTENT PLANNING LOOP FOUNDATION CHECKPOINT =========="
