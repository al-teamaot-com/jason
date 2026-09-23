#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START CANONICAL FACT VOCABULARY CHECKPOINT =========="

echo "========== SECTION 1: VALIDATE EXPECTED CHANGE SET =========="
ALLOWED=(
  "implementation/orchestrator/canonical_fact_vocabulary.py"
  "implementation/orchestrator/conversation_resource_intent.py"
  "implementation/orchestrator/tests/test_canonical_fact_vocabulary.py"
  "implementation/orchestrator/tests/test_conversation_resource_intent.py"
  "implementation/runtime_service/src/jason_runtime/composition.py"
)

mapfile -t CHANGED < <(git status --porcelain | sed 's/^...//')
for path in "${CHANGED[@]}"; do
  allowed=false
  for expected in "${ALLOWED[@]}"; do
    if [[ "$path" == "$expected" ]]; then
      allowed=true
      break
    fi
  done
  if [[ "$allowed" != true ]]; then
    echo "ERROR: unrelated local change detected: $path"
    echo "No commit performed."
    exit 20
  fi
done

echo "PASS: local changes are limited to the canonical fact vocabulary workstream."

echo "========== SECTION 2: REVALIDATE =========="
git diff --check
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_canonical_fact_vocabulary.py \
  implementation/orchestrator/tests/test_conversation_resource_intent.py \
  implementation/runtime_service/tests/test_composition.py

echo "========== SECTION 3: COMMIT =========="
git add \
  implementation/orchestrator/canonical_fact_vocabulary.py \
  implementation/orchestrator/conversation_resource_intent.py \
  implementation/orchestrator/tests/test_canonical_fact_vocabulary.py \
  implementation/orchestrator/tests/test_conversation_resource_intent.py \
  implementation/runtime_service/src/jason_runtime/composition.py

if git diff --cached --quiet; then
  echo "PASS: no uncommitted canonical vocabulary changes remain."
else
  git commit -m "Add canonical endpoint fact vocabulary foundation"
fi

echo "========== SECTION 4: PUSH =========="
bash scripts/jason-push-checkpoint.sh

echo "========== FINAL STATUS =========="
git log -1 --oneline
git status --short
echo "PASS: canonical fact vocabulary foundation is durable in GitHub."
echo "========== END CANONICAL FACT VOCABULARY CHECKPOINT =========="
