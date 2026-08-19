#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC KNOWLEDGE REGISTRY FOUNDATION VALIDATION =========="
echo "========== SECTION 1: PRECONDITIONS =========="
echo "HEAD: $(git rev-parse --short HEAD)"

for path in \
  implementation/orchestrator/semantic_knowledge_registry.py \
  implementation/orchestrator/tests/test_semantic_knowledge_registry.py
 do
  if [[ ! -f "$path" ]]; then
    echo "ERROR: required foundation file is missing: $path"
    exit 20
  fi
done

echo "========== SECTION 2: STATIC VALIDATION =========="
git diff --check

echo "========== SECTION 3: FOCUSED TESTS =========="
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_semantic_knowledge_registry.py \
  implementation/orchestrator/tests/test_canonical_fact_vocabulary.py \
  implementation/orchestrator/tests/test_semantic_resource_request.py

echo "========== SECTION 4: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Semantic Knowledge Registry foundation validated with real static and test execution."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC KNOWLEDGE REGISTRY FOUNDATION VALIDATION =========="
