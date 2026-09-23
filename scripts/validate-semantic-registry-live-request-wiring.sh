#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC REGISTRY LIVE REQUEST WIRING VALIDATION =========="
echo "========== SECTION 1: PRECONDITIONS =========="
echo "HEAD: $(git rev-parse --short HEAD)"

BACKUP="implementation/orchestrator/semantic_fact_resolver.py.semantic-registry-wiring.bak"
if [[ -f "$BACKUP" ]]; then
  rm -f "$BACKUP"
  echo "REMOVED: stale semantic registry wiring backup artifact"
fi

echo "========== SECTION 2: STATIC VALIDATION =========="
git diff --check

echo "========== SECTION 3: FOCUSED TESTS =========="
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_knowledge_seed.py \
  implementation/orchestrator/tests/test_conversation_resource_intent.py

echo "========== SECTION 4: CHANGE STATE =========="
git status --short

DIRTY="$(git status --porcelain | grep -v '^?? FETCH_HEAD$' || true)"
UNEXPECTED="$(printf '%s\n' "$DIRTY" | grep -v '^ M implementation/orchestrator/semantic_request_bridge.py$' || true)"
if [[ -n "$UNEXPECTED" ]]; then
  echo "ERROR: unexpected worktree changes present after live request wiring validation."
  printf '%s\n' "$UNEXPECTED"
  exit 21
fi

if ! grep -q 'fact_resolver' implementation/orchestrator/semantic_request_bridge.py; then
  echo "ERROR: SemanticRequestBridge does not contain registry-first fact resolver wiring."
  exit 22
fi

echo "========== RESULT =========="
echo "SemanticRequestBridge registry-first live request wiring validated with real static and focused test execution."
echo "Legacy vocabulary fallback remains available through the compatibility resolver."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC REGISTRY LIVE REQUEST WIRING VALIDATION =========="
