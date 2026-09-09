#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC EVIDENCE DIRECT RESOLUTION CHECKPOINT =========="

echo "========== SECTION 1: VALIDATE CHANGE SET =========="
allowed=(
  "implementation/orchestrator/resource_evidence.py"
  "implementation/orchestrator/tests/test_resource_evidence.py"
)

unexpected=0
while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  path="${line:3}"
  if [[ "$path" == "FETCH_HEAD" ]]; then
    continue
  fi
  ok=0
  for allowed_path in "${allowed[@]}"; do
    if [[ "$path" == "$allowed_path" ]]; then
      ok=1
      break
    fi
  done
  if [[ "$ok" -ne 1 ]]; then
    echo "ERROR: unexpected worktree change: $line"
    unexpected=1
  fi
done < <(git status --short)

if [[ "$unexpected" -ne 0 ]]; then
  exit 20
fi

echo "PASS: local changes are limited to semantic evidence direct resolution."

echo "========== SECTION 2: REVALIDATE =========="
git diff --check
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_resource_evidence.py \
  implementation/connectors/tests/test_datto_semantic_evidence.py \
  implementation/orchestrator/tests/test_resource_capability_catalog.py

echo "========== SECTION 3: COMMIT =========="
git add \
  implementation/orchestrator/resource_evidence.py \
  implementation/orchestrator/tests/test_resource_evidence.py

if git diff --cached --quiet; then
  echo "NOTE: no semantic evidence direct-resolution changes are staged; no new commit required."
else
  git commit -m "Resolve adapted semantic evidence deterministically"
fi

echo "========== SECTION 4: PUSH =========="
bash scripts/jason-push-checkpoint.sh

echo "========== FINAL STATUS =========="
git log -1 --oneline --decorate
echo "PASS: semantic evidence direct resolution is durable in GitHub."
echo "========== END SEMANTIC EVIDENCE DIRECT RESOLUTION CHECKPOINT =========="
