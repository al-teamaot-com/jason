#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START METADATA REASONER SEMANTIC PROPAGATION CHECKPOINT =========="

echo "========== SECTION 1: VALIDATE CHANGE SET =========="
allowed=(
  "implementation/orchestrator/resource_reasoner.py"
  "implementation/orchestrator/tests/test_resource_capability_catalog.py"
)

unexpected=0
while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  path="${line:3}"
  if [[ "$line" == "?? FETCH_HEAD" ]]; then
    continue
  fi
  ok=0
  for candidate in "${allowed[@]}"; do
    if [[ "$path" == "$candidate" ]]; then
      ok=1
      break
    fi
  done
  if [[ "$ok" -ne 1 ]]; then
    echo "UNEXPECTED: $line"
    unexpected=1
  fi
done < <(git status --short)

if [[ "$unexpected" -ne 0 ]]; then
  echo "ERROR: unexpected worktree changes present."
  exit 20
fi

echo "PASS: local changes are limited to metadata reasoner semantic propagation."

PY=.venv/bin/python
if [[ ! -x "$PY" ]]; then
  echo "ERROR: .venv/bin/python is required."
  exit 21
fi

echo "========== SECTION 2: REVALIDATE =========="
git diff --check
$PY -m pytest -q \
  implementation/orchestrator/tests/test_resource_capability_catalog.py \
  implementation/orchestrator/tests/test_resource_evidence.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_conversation_resource_intent.py \
  implementation/orchestrator/tests/test_ollama_reasoning.py

echo "========== SECTION 3: COMMIT =========="
git add \
  implementation/orchestrator/resource_reasoner.py \
  implementation/orchestrator/tests/test_resource_capability_catalog.py

if git diff --cached --quiet; then
  echo "NOTE: no metadata reasoner semantic propagation changes are staged; no new commit required."
else
  git commit -m "Preserve semantic context in metadata resource planning"
fi

echo "========== SECTION 4: PUSH =========="
if [[ -x scripts/jason-push-checkpoint.sh ]]; then
  bash scripts/jason-push-checkpoint.sh
else
  git fetch origin feature/jason-runtime-service
  LOCAL="$(git rev-parse HEAD)"
  REMOTE="$(git rev-parse origin/feature/jason-runtime-service)"
  BASE="$(git merge-base HEAD origin/feature/jason-runtime-service)"
  if [[ "$LOCAL" == "$REMOTE" ]]; then
    echo "PASS: local and remote are already synchronized at $(git rev-parse --short HEAD)."
  elif [[ "$BASE" == "$REMOTE" ]]; then
    git push origin feature/jason-runtime-service
  else
    echo "ERROR: branch diverged from origin; reconcile before push."
    exit 22
  fi
fi

echo "========== FINAL STATUS =========="
git log -1 --oneline --decorate
echo "PASS: metadata resource planning semantic propagation is durable in GitHub."
echo "========== END METADATA REASONER SEMANTIC PROPAGATION CHECKPOINT =========="
