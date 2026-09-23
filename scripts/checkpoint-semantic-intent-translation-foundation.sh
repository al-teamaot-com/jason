#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC INTENT TRANSLATION CHECKPOINT =========="

EXPECTED=(
  "implementation/connectors/datto_rmm/connector.py"
  "implementation/connectors/tests/test_datto_rmm_connector.py"
  "implementation/orchestrator/canonical_fact_vocabulary.py"
  "implementation/orchestrator/conversation_resource_intent.py"
  "implementation/orchestrator/ollama_reasoning.py"
  "implementation/orchestrator/resource_capability_catalog.py"
  "implementation/orchestrator/tests/test_canonical_fact_vocabulary.py"
)

echo "========== SECTION 1: VALIDATE CHANGE SET =========="
mapfile -t CHANGED < <(git status --porcelain | awk '{print $2}' | grep -v '^FETCH_HEAD$' || true)
for path in "${CHANGED[@]}"; do
  allowed=false
  for expected in "${EXPECTED[@]}"; do
    if [[ "$path" == "$expected" ]]; then
      allowed=true
      break
    fi
  done
  if [[ "$allowed" != true ]]; then
    echo "ERROR: unrelated changed path detected: $path"
    exit 20
  fi
done

echo "PASS: local changes are limited to the semantic intent translation workstream."

echo "========== SECTION 2: REVALIDATE =========="
git diff --check
PY=.venv/bin/python
if [[ ! -x "$PY" ]]; then
  echo "ERROR: .venv/bin/python is required."
  exit 21
fi
$PY -m pytest -q \
  implementation/connectors/tests/test_datto_rmm_connector.py \
  implementation/orchestrator/tests/test_canonical_fact_vocabulary.py \
  implementation/orchestrator/tests/test_conversation_resource_intent.py \
  implementation/orchestrator/tests/test_ollama_reasoning.py

echo "========== SECTION 3: COMMIT =========="
git add "${EXPECTED[@]}"
git commit -m "Add semantic intent translation foundation"

echo "========== SECTION 4: PUSH =========="
bash scripts/jason-push-checkpoint.sh

echo "========== FINAL STATUS =========="
git log -1 --oneline --decorate
echo "PASS: semantic intent translation foundation is durable in GitHub."
echo "========== END SEMANTIC INTENT TRANSLATION CHECKPOINT =========="
