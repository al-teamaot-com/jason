#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START DATTO SEMANTIC EVIDENCE ADAPTATION =========="
echo "========== SECTION 1: PRECONDITIONS =========="
DIRTY="$(git status --porcelain | grep -v '^?? FETCH_HEAD$' || true)"
ALLOWED='implementation/connectors/datto_rmm/connector.py|implementation/connectors/datto_rmm/semantic_evidence.py'
UNEXPECTED="$(printf '%s\n' "$DIRTY" | awk '{print $2}' | grep -Ev "^($ALLOWED)$" || true)"
if [[ -n "$UNEXPECTED" ]]; then
  echo "ERROR: unexpected worktree changes present."
  printf '%s\n' "$DIRTY"
  exit 20
fi
PY=.venv/bin/python
if [[ ! -x "$PY" ]]; then
  echo "ERROR: .venv/bin/python is required."
  exit 21
fi

echo "HEAD: $(git rev-parse --short HEAD)"

echo "========== SECTION 2: ENSURE DECLARATIVE DATTO SEMANTIC EVIDENCE MAP =========="
if [[ ! -f implementation/connectors/datto_rmm/semantic_evidence.py ]]; then
  echo "ERROR: semantic_evidence.py is missing from the prior patch stage."
  exit 22
fi
echo "PASS: implementation/connectors/datto_rmm/semantic_evidence.py present"

echo "========== SECTION 3: ENSURE ADAPTER IS WIRED AT DATTO DEVICE READ BOUNDARY =========="
grep -q 'adapt_datto_device_semantic_evidence' implementation/connectors/datto_rmm/connector.py || {
  echo "ERROR: connector adaptation wiring is missing."
  exit 23
}
echo "PASS: Datto connector semantic evidence wiring present"

echo "========== SECTION 4: ADD PROVIDER ADAPTATION TESTS IN EXISTING TEST TREE =========="
mkdir -p implementation/connectors/tests
cat > implementation/connectors/tests/test_datto_semantic_evidence.py <<'PY'
from connectors.datto_rmm.semantic_evidence import adapt_datto_device_semantic_evidence


def test_display_version_is_exposed_only_under_os_windows_release_context():
    adapted = adapt_datto_device_semantic_evidence({
        "health": {"version": "Unhealthy - Local user changes detected"},
        "operatingSystem": {"displayVersion": "24H2"},
    })
    assert adapted["semantic_evidence"]["operating_system"]["windows_release"]["operating_system_display_version"] == "24H2"
    assert adapted["health"]["version"] == "Unhealthy - Local user changes detected"


def test_ambiguous_provider_keys_fail_closed_by_omission():
    adapted = adapt_datto_device_semantic_evidence({
        "a": {"displayVersion": "23H2"},
        "b": {"DisplayVersion": "24H2"},
    })
    assert "semantic_evidence" not in adapted


def test_processor_model_and_count_remain_distinct_semantic_fields():
    adapted = adapt_datto_device_semantic_evidence({
        "hardware": {
            "processorModel": "Intel Core i7-12700",
            "logicalProcessors": 20,
        }
    })
    processor = adapted["semantic_evidence"]["processor"]["hardware_inventory"]
    assert processor["processor_model"] == "Intel Core i7-12700"
    assert processor["logical_processor_count"] == 20
PY

echo "WROTE: implementation/connectors/tests/test_datto_semantic_evidence.py"

echo "========== SECTION 5: VALIDATE =========="
git diff --check
$PY -m py_compile \
  implementation/connectors/datto_rmm/semantic_evidence.py \
  implementation/connectors/datto_rmm/connector.py \
  implementation/connectors/tests/test_datto_semantic_evidence.py
$PY -m pytest -q \
  implementation/connectors/tests/test_datto_semantic_evidence.py \
  implementation/connectors/tests/test_datto_rmm_connector.py \
  implementation/orchestrator/tests/test_resource_evidence.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py

echo "========== SECTION 6: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Datto semantic evidence adaptation validated."
echo "Provider-native device evidence can now be exposed through semantic context containers without changing human intent semantics."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END DATTO SEMANTIC EVIDENCE ADAPTATION =========="
