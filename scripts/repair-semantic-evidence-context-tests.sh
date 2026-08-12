#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC EVIDENCE CONTEXT TEST REPAIR =========="
echo "========== SECTION 1: CURRENT STATE =========="
git status --short

PY=.venv/bin/python
if [[ ! -x "$PY" ]]; then
  echo "ERROR: .venv/bin/python is required."
  exit 21
fi

echo "========== SECTION 2: REPAIR TEST FIXTURE =========="
$PY - <<'PY'
from pathlib import Path
p = Path('implementation/orchestrator/tests/test_resource_evidence.py')
s = p.read_text(encoding='utf-8')

if 'class FakeEvidenceReasoner:' not in s:
    anchor = 'from orchestrator.resource_evidence import '
    # insert a tiny local test fixture before the first test function instead of changing production code
    marker = '\ndef test_'
    idx = s.find(marker)
    if idx == -1:
        raise SystemExit('ERROR: test insertion anchor missing')
    fixture = '''\n\nclass FakeEvidenceReasoner:\n    def __init__(self, proposals):\n        self.proposals = tuple(proposals)\n\n    def locate(self, *, requested_facts, data):\n        return self.proposals\n'''
    s = s[:idx] + fixture + s[idx:]
    p.write_text(s, encoding='utf-8')
    print('UPDATED:', p)
else:
    print('PASS: FakeEvidenceReasoner already present')
PY

echo "========== SECTION 3: STATIC VALIDATION =========="ngit diff --check
$PY -m py_compile implementation/orchestrator/resource_inquiry.py implementation/orchestrator/semantic_request_bridge.py implementation/orchestrator/ollama_reasoning.py implementation/orchestrator/resource_evidence.py implementation/orchestrator/tests/test_resource_evidence.py

echo "========== SECTION 4: FOCUSED TESTS =========="n$PY -m pytest -q implementation/orchestrator/tests/test_resource_evidence.py implementation/orchestrator/tests/test_semantic_request_bridge.py implementation/orchestrator/tests/test_conversation_resource_intent.py implementation/orchestrator/tests/test_ollama_reasoning.py

echo "========== SECTION 5: CHANGE STATE =========="ngit status --short

echo "========== RESULT =========="necho "Semantic evidence context propagation test fixture repaired and validated."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC EVIDENCE CONTEXT TEST REPAIR =========="
