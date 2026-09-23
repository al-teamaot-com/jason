#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START RESOURCE EVIDENCE UNAVAILABLE TEST FIXTURE INTERPRETER REPAIR =========="
echo "========== SECTION 1: PRECONDITIONS =========="
echo "HEAD: $(git rev-parse --short HEAD)"
git status --short

echo "========== SECTION 2: PATCH TEST FIXTURES USING PROJECT PYTHON =========="
.venv/bin/python - <<'PY'
from pathlib import Path

path = Path("implementation/orchestrator/tests/test_resource_evidence.py")
text = path.read_text(encoding="utf-8")
old1 = 'result=result(data={"provider_data": {}}),'
new1 = 'result=result(data={"resource_matches": [{"resource_id": "device-1", "hostname": "AOT-50282"}], "provider_data": {}}),'
old2 = 'result=result(data={"provider_data": {"displayVersion": "4.4.11965.11965"}}),'
new2 = 'result=result(data={"resource_matches": [{"resource_id": "device-1", "hostname": "AOT-50282"}], "provider_data": {"displayVersion": "4.4.11965.11965"}}),'
replaced = 0
if old1 in text:
    text = text.replace(old1, new1, 1)
    replaced += 1
if old2 in text:
    text = text.replace(old2, new2, 1)
    replaced += 1
if replaced == 0:
    print("PASS: canonical endpoint-search fixtures already present")
else:
    path.write_text(text, encoding="utf-8")
    print(f"UPDATED: {path} ({replaced} replacements)")
PY

echo "========== SECTION 3: STATIC VALIDATION =========="
git diff --check

echo "========== SECTION 4: FOCUSED TESTS =========="
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_resource_evidence.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py

echo "========== SECTION 5: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Unavailable-response test fixtures now use the project virtualenv interpreter and canonical endpoint search evidence."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END RESOURCE EVIDENCE UNAVAILABLE TEST FIXTURE INTERPRETER REPAIR =========="
