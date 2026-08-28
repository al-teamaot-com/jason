#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC EVIDENCE CONTEXT RESULT SHADOWING REPAIR =========="
echo "========== SECTION 1: CURRENT STATE =========="
git status --short

PY=.venv/bin/python
if [[ ! -x "$PY" ]]; then
  echo "ERROR: .venv/bin/python is required."
  exit 21
fi

echo "========== SECTION 2: REPAIR LOCAL RESULT VARIABLE SHADOWING =========="
$PY - <<'PY'
from pathlib import Path
p = Path('implementation/orchestrator/tests/test_resource_evidence.py')
s = p.read_text(encoding='utf-8')
old = '    result = result(\n'
new = '    orchestration_result = result(\n'
count = s.count(old)
if count:
    s = s.replace(old, new)
    s = s.replace('            result=result,\n', '            result=orchestration_result,\n')
    s = s.replace('        result=result,\n', '        result=orchestration_result,\n')
    p.write_text(s, encoding='utf-8')
    print(f'UPDATED: {p} ({count} shadowing assignments repaired)')
else:
    print('PASS: no result fixture shadowing assignments remain')
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
echo "Semantic evidence context result fixture shadowing repaired and validated."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC EVIDENCE CONTEXT RESULT SHADOWING REPAIR =========="
