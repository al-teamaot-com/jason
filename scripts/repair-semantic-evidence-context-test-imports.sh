#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC EVIDENCE CONTEXT TEST IMPORT REPAIR =========="
echo "========== SECTION 1: CURRENT STATE =========="
git status --short

PY=.venv/bin/python
if [[ ! -x "$PY" ]]; then
  echo "ERROR: .venv/bin/python is required."
  exit 21
fi

echo "========== SECTION 2: REPAIR CANONICAL FACT VOCABULARY TEST IMPORT =========="
$PY - <<'PY'
from pathlib import Path
p = Path('implementation/orchestrator/tests/test_resource_evidence.py')
s = p.read_text(encoding='utf-8')
import_line = 'from orchestrator.canonical_fact_vocabulary import DEFAULT_CANONICAL_FACT_VOCABULARY\n'
if import_line not in s:
    marker = 'from orchestrator.resource_evidence import '
    idx = s.find(marker)
    if idx == -1:
        raise SystemExit('ERROR: resource evidence import anchor missing')
    s = s[:idx] + import_line + s[idx:]
    p.write_text(s, encoding='utf-8')
    print('UPDATED:', p)
else:
    print('PASS: canonical fact vocabulary import already present')
PY

echo "========== SECTION 3: STATIC VALIDATION =========="
git diff --check
$PY -m py_compile implementation/orchestrator/tests/test_resource_evidence.py

echo "========== SECTION 4: FOCUSED TESTS =========="
$PY -m pytest -q \
  implementation/orchestrator/tests/test_resource_evidence.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_conversation_resource_intent.py \
  implementation/orchestrator/tests/test_ollama_reasoning.py

echo "========== SECTION 5: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Semantic evidence context test imports repaired and validated."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC EVIDENCE CONTEXT TEST IMPORT REPAIR =========="
