#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START CLEAN CANONICAL FACT VOCABULARY RECOVERY =========="

echo "========== SECTION 1: CONFIRM EXPECTED LOCAL CHANGE SET =========="
EXPECTED=$(cat <<'EOF'
implementation/orchestrator/conversation_resource_intent.py
implementation/orchestrator/tests/test_conversation_resource_intent.py
implementation/runtime_service/src/jason_runtime/composition.py
implementation/orchestrator/canonical_fact_vocabulary.py
implementation/orchestrator/tests/test_canonical_fact_vocabulary.py
EOF
)
ACTUAL=$(git status --porcelain | sed 's/^...//' | sort)
for path in $ACTUAL; do
  if ! grep -Fxq "$path" <<<"$EXPECTED"; then
    echo "ERROR: unrelated local change detected: $path"
    echo "No reset performed."
    exit 20
  fi
done
echo "PASS: local changes are limited to the failed canonical-fact workstream"

echo "========== SECTION 2: RESET ONLY FAILED WORKSTREAM FILES =========="
git restore -- \
  implementation/orchestrator/conversation_resource_intent.py \
  implementation/orchestrator/tests/test_conversation_resource_intent.py \
  implementation/runtime_service/src/jason_runtime/composition.py
rm -f \
  implementation/orchestrator/canonical_fact_vocabulary.py \
  implementation/orchestrator/tests/test_canonical_fact_vocabulary.py
echo "PASS: failed partial patch removed"

echo "========== SECTION 3: APPLY CANONICAL VOCABULARY FOUNDATION =========="
# Reuse the original patch helper from a clean source baseline. Its current version
# contains automatic pytest-runner discovery.
bash scripts/patch-canonical-fact-vocabulary-foundation.sh

echo "========== END CLEAN CANONICAL FACT VOCABULARY RECOVERY =========="
