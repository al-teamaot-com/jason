#!/usr/bin/env bash
set -euo pipefail

cd /home/al/projects/jason

TEST_FILE="implementation/orchestrator/tests/test_conversation_resource_intent.py"

echo "========== START RESOURCE OUTCOME TEST ALIGNMENT =========="

python3 - <<'PY'
from pathlib import Path

p = Path("implementation/orchestrator/tests/test_conversation_resource_intent.py")
s = p.read_text(encoding="utf-8")

old = '''    assert intent.arguments == {
        "hostname": "AOT-50282",
        "requested_facts": ("last logged in user",),
    }
'''
new = '''    assert intent.arguments == {
        "hostname": "AOT-50282",
        "requested_facts": ("last logged in user",),
        "result_intent": "summary",
        "completeness_requirement": "sufficient",
    }
'''

if old in s:
    s = s.replace(old, new, 1)
elif new not in s:
    raise SystemExit("ERROR: expected intent argument assertion not found")

p.write_text(s, encoding="utf-8")
print("Updated:", p)
PY

export PYTHONPATH="/home/al/projects/jason/implementation:/home/al/projects/jason/implementation/cap-001/src:/home/al/projects/jason/implementation/cap-002/src:/home/al/projects/jason/implementation/cap-003/src:/home/al/projects/jason/implementation/cap-007/src:/home/al/projects/jason/implementation/cli/src:/home/al/projects/jason/implementation/connectors/openclaw/src:/home/al/projects/jason/implementation/connectors/src:/home/al/projects/jason/implementation/runtime_service/src"

./.venv-test/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_conversation_resource_intent.py \
  implementation/orchestrator/tests/test_resource_capability_catalog.py \
  implementation/runtime_service/tests/test_composition.py

git diff --check

echo "========== RESULT =========="
echo "Resource outcome test alignment validated."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH PERFORMED."
echo "========== END RESOURCE OUTCOME TEST ALIGNMENT =========="
