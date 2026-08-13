#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START RESOURCE EVIDENCE UNAVAILABLE TEST FIXTURE REPAIR =========="
echo "========== SECTION 1: CURRENT STATE =========="
git status --short

echo "========== SECTION 2: ALIGN TEST FIXTURES WITH CANONICAL ENDPOINT SEARCH RESULT =========="
python - <<'PY'
from pathlib import Path

path = Path("implementation/orchestrator/tests/test_resource_evidence.py")
text = path.read_text(encoding="utf-8")

replacements = {
    'result=result(data={"provider_data": {}}),': '''result=result(data={
            "resource_matches": [
                {"resource_id": "device-50282", "hostname": "AOT-50282"}
            ],
            "resolved_resource_id": "device-50282",
            "provider_data": {},
        }),''',
    'result=result(data={"provider_data": {"displayVersion": "4.4.11965.11965"}}),': '''result=result(data={
            "resource_matches": [
                {"resource_id": "device-50282", "hostname": "AOT-50282"}
            ],
            "resolved_resource_id": "device-50282",
            "provider_data": {"displayVersion": "4.4.11965.11965"},
        }),''',
}

changed = 0
for old, new in replacements.items():
    if old in text:
        text = text.replace(old, new, 1)
        changed += 1

if changed != 2:
    raise SystemExit(f"ERROR: expected to repair 2 unavailable-response fixtures, repaired {changed}")

path.write_text(text, encoding="utf-8")
print("UPDATED: implementation/orchestrator/tests/test_resource_evidence.py")
PY

echo "========== SECTION 3: STATIC VALIDATION =========="
git diff --check

echo "========== SECTION 4: FOCUSED TESTS =========="
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_resource_evidence.py \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/connectors/tests/test_datto_semantic_evidence.py

echo "========== SECTION 5: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Unavailable-evidence response tests now use the canonical endpoint discovery/result contract."
echo "The renderer remains strict about durable endpoint identity and does not weaken discovery safeguards."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END RESOURCE EVIDENCE UNAVAILABLE TEST FIXTURE REPAIR =========="
