#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC REQUEST CONVERSATION BRIDGE CHECKPOINT =========="

echo "========== SECTION 1: VALIDATE CHANGE SET =========="
ALLOWED=(
  "implementation/orchestrator/conversation_resource_intent.py"
  "implementation/orchestrator/semantic_request_bridge.py"
  "implementation/orchestrator/tests/test_semantic_request_bridge.py"
)

unexpected=0
while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  if [[ "$line" == "?? FETCH_HEAD" ]]; then
    continue
  fi
  path="${line:3}"
  ok=0
  for allowed in "${ALLOWED[@]}"; do
    if [[ "$path" == "$allowed" ]]; then
      ok=1
      break
    fi
  done
  if [[ $ok -eq 0 ]]; then
    echo "UNEXPECTED: $line"
    unexpected=1
  fi
done < <(git status --porcelain)

if [[ $unexpected -ne 0 ]]; then
  echo "ERROR: unrelated worktree changes are present."
  exit 20
fi

echo "PASS: local changes are limited to the semantic request conversation bridge."

echo "========== SECTION 2: REVALIDATE =========="
git diff --check
.venv/bin/python -m py_compile \
  implementation/orchestrator/semantic_request_bridge.py \
  implementation/orchestrator/conversation_resource_intent.py
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_semantic_resource_request.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_conversation_resource_intent.py \
  implementation/orchestrator/tests/test_canonical_fact_vocabulary.py

echo "========== SECTION 3: COMMIT =========="
git add \
  implementation/orchestrator/conversation_resource_intent.py \
  implementation/orchestrator/semantic_request_bridge.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py

if git diff --cached --quiet; then
  echo "NOTE: no semantic bridge changes are staged; no new commit required."
else
  git commit -m "Route resource conversation through semantic request IR"
fi

echo "========== SECTION 4: PUSH =========="
bash scripts/jason-push-checkpoint.sh

echo "========== FINAL STATUS =========="
git log -1 --oneline --decorate
echo "PASS: semantic request conversation bridge is durable in GitHub."
echo "========== END SEMANTIC REQUEST CONVERSATION BRIDGE CHECKPOINT =========="
