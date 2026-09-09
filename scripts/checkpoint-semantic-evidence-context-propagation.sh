#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC EVIDENCE CONTEXT PROPAGATION CHECKPOINT =========="

echo "========== SECTION 1: VALIDATE CHANGE SET =========="
mapfile -t CHANGED < <(git status --porcelain | awk '{$1=""; sub(/^ /, ""); print}' | grep -v '^FETCH_HEAD$' || true)
EXPECTED=(
  "implementation/orchestrator/ollama_reasoning.py"
  "implementation/orchestrator/resource_evidence.py"
  "implementation/orchestrator/resource_inquiry.py"
  "implementation/orchestrator/semantic_request_bridge.py"
  "implementation/orchestrator/tests/test_resource_evidence.py"
  "implementation/orchestrator/tests/test_semantic_request_bridge.py"
)

for path in "${CHANGED[@]}"; do
  allowed=false
  for expected in "${EXPECTED[@]}"; do
    if [[ "$path" == "$expected" ]]; then
      allowed=true
      break
    fi
  done
  if [[ "$allowed" != true ]]; then
    echo "ERROR: unexpected worktree change: $path"
    exit 20
  fi
done

echo "PASS: local changes are limited to semantic evidence context propagation."

PY=.venv/bin/python
if [[ ! -x "$PY" ]]; then
  echo "ERROR: .venv/bin/python is required."
  exit 21
fi

echo "========== SECTION 2: REVALIDATE =========="
git diff --check
$PY -m py_compile \
  implementation/orchestrator/resource_inquiry.py \
  implementation/orchestrator/semantic_request_bridge.py \
  implementation/orchestrator/ollama_reasoning.py \
  implementation/orchestrator/resource_evidence.py \
  implementation/orchestrator/tests/test_resource_evidence.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py
$PY -m pytest -q \
  implementation/orchestrator/tests/test_resource_evidence.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_conversation_resource_intent.py \
  implementation/orchestrator/tests/test_ollama_reasoning.py

echo "========== SECTION 3: COMMIT =========="
git add \
  implementation/orchestrator/ollama_reasoning.py \
  implementation/orchestrator/resource_evidence.py \
  implementation/orchestrator/resource_inquiry.py \
  implementation/orchestrator/semantic_request_bridge.py \
  implementation/orchestrator/tests/test_resource_evidence.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py

if git diff --cached --quiet; then
  echo "NOTE: no semantic evidence context changes are staged; no new commit required."
else
  git commit -m "Propagate semantic evidence context through governed reads"
fi

echo "========== SECTION 4: PUSH =========="
bash scripts/jason-push-checkpoint.sh

echo "========== FINAL STATUS =========="
git log -1 --oneline --decorate
echo "PASS: semantic evidence context propagation is durable in GitHub."
echo "========== END SEMANTIC EVIDENCE CONTEXT PROPAGATION CHECKPOINT =========="
