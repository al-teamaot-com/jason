#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC RESOURCE REQUEST IR CHECKPOINT =========="

echo "========== SECTION 1: VALIDATE CHANGE SET =========="
DIRTY="$(git status --porcelain | grep -v '^?? FETCH_HEAD$' || true)"
EXPECTED=$(cat <<'EOF'
?? implementation/orchestrator/semantic_resource_request.py
?? implementation/orchestrator/tests/test_semantic_resource_request.py
EOF
)
if [[ "$DIRTY" != "$EXPECTED" ]]; then
  echo "ERROR: unexpected worktree changes present."
  printf '%s\n' "$DIRTY"
  exit 20
fi
echo "PASS: local changes are limited to the semantic resource request IR foundation."

echo "========== SECTION 2: REVALIDATE =========="
git diff --check
.venv/bin/python -m py_compile implementation/orchestrator/semantic_resource_request.py
.venv/bin/python -m pytest -q implementation/orchestrator/tests/test_semantic_resource_request.py

echo "========== SECTION 3: COMMIT =========="
git add implementation/orchestrator/semantic_resource_request.py implementation/orchestrator/tests/test_semantic_resource_request.py
git commit -m "Add provider-neutral semantic resource request IR"

echo "========== SECTION 4: PUSH =========="
bash scripts/jason-push-checkpoint.sh

echo "========== FINAL STATUS =========="
git log -1 --oneline --decorate
echo "PASS: semantic resource request IR is durable in GitHub."
echo "========== END SEMANTIC RESOURCE REQUEST IR CHECKPOINT =========="