#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC EVIDENCE CONTEXT VOCABULARY IMPORT REPAIR =========="
echo "========== SECTION 1: CURRENT STATE =========="
git status --short

PY=.venv/bin/python
if [[ ! -x "$PY" ]]; then
  echo "ERROR: .venv/bin/python is required."
  exit 21
fi

echo "========== SECTION 2: ENSURE ACTUAL VOCABULARY IMPORT EXISTS =========="
$PY - <<'PY'
from pathlib import Path

p = Path('implementation/orchestrator/tests/test_resource_evidence.py')
s = p.read_text(encoding='utf-8')
import_line = 'from orchestrator.canonical_fact_vocabulary import DEFAULT_CANONICAL_FACT_VOCABULARY\n'

# Check only the import section, not arbitrary later references to the symbol.
head = '\n'.join(s.splitlines()[:40]) + '\n'
if import_line not in head:
    anchor = 'from orchestrator.contracts import (\n'
    idx = s.find(anchor)
    if idx == -1:
        raise SystemExit('ERROR: contracts import anchor missing')
    s = s[:idx] + import_line + s[idx:]
    p.write_text(s, encoding='utf-8')
    print('UPDATED:', p)
else:
    print('PASS: actual canonical fact vocabulary import is present')
PY

echo "========== SECTION 3: STATIC VALIDATION =========="
git diff --check
$PY -m py_compile \
  implementation/orchestrator/resource_inquiry.py \
  implementation/orchestrator/semantic_request_bridge.py \
  implementation/orchestrator/ollama_reasoning.py \
  implementation/orchestrator/resource_evidence.py \
  implementation/orchestrator/tests/test_resource_evidence.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py

echo "========== SECTION 4: FOCUSED TESTS =========="
$PY -m pytest -q \
  implementation/orchestrator/tests/test_resource_evidence.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_conversation_resource_intent.py \
  implementation/orchestrator/tests/test_ollama_reasoning.py

echo "========== SECTION 5: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Semantic evidence context vocabulary import repaired and validation executed."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC EVIDENCE CONTEXT VOCABULARY IMPORT REPAIR =========="