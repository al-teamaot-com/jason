#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START DATTO SEMANTIC EQUIVALENT PROVIDER VALUE REPAIR =========="
echo "========== SECTION 1: PRECONDITIONS =========="
echo "HEAD: $(git rev-parse --short HEAD)"

echo "========== SECTION 2: COLLAPSE EQUIVALENT PROVIDER VALUES =========="
.venv/bin/python - <<'PY'
from pathlib import Path

path = Path('implementation/connectors/datto_rmm/semantic_evidence.py')
text = path.read_text()
old = '''def _find_unique_provider_value(data: Any, provider_keys: tuple[str, ...]) -> Any:\n    wanted = {_normalized_key(key) for key in provider_keys}\n    matches: list[Any] = []\n    for mapping in _walk_mappings(data):\n        for raw_key, value in mapping.items():\n            if _normalized_key(str(raw_key)) in wanted:\n                matches.append(value)\n    if len(matches) != 1:\n        return None\n    return matches[0]\n'''
new = '''def _find_unique_provider_value(data: Any, provider_keys: tuple[str, ...]) -> Any:\n    wanted = {_normalized_key(key) for key in provider_keys}\n    matches: list[Any] = []\n    for mapping in _walk_mappings(data):\n        for raw_key, value in mapping.items():\n            if _normalized_key(str(raw_key)) in wanted:\n                matches.append(value)\n\n    if not matches:\n        return None\n    if len(matches) == 1:\n        return matches[0]\n\n    # Provider payloads may repeat the same authoritative value under multiple\n    # aliases or inventory sections. Equivalent duplicates are not ambiguity.\n    # Conflicting values remain unresolved and fail closed.\n    first = matches[0]\n    if all(value == first for value in matches[1:]):\n        return first\n    return None\n'''
if old in text:
    path.write_text(text.replace(old, new, 1))
    print(f'UPDATED: {path}')
elif new in text:
    print(f'PASS: equivalent-value collapse already present in {path}')
else:
    raise SystemExit('ERROR: expected Datto unique-value helper not found')
PY

echo "========== SECTION 3: ADD REGRESSION COVERAGE =========="
TEST_FILE=implementation/connectors/tests/test_datto_semantic_evidence.py
if ! grep -q '^def test_semantic_adapter_accepts_equivalent_duplicate_processor_aliases' "$TEST_FILE"; then
cat >> "$TEST_FILE" <<'PY'


def test_semantic_adapter_accepts_equivalent_duplicate_processor_aliases():
    from connectors.datto_rmm.semantic_evidence import adapt_datto_device_semantic_evidence

    value = "Intel(R) Core(TM) i7-9700F CPU @ 3.00GHz"
    adapted = adapt_datto_device_semantic_evidence(
        {
            "processor": value,
            "inventory": {"cpuModel": value},
        }
    )

    assert adapted["semantic_evidence"]["processor"]["hardware_inventory"]["processor_model"] == value


def test_semantic_adapter_rejects_conflicting_duplicate_processor_aliases():
    from connectors.datto_rmm.semantic_evidence import adapt_datto_device_semantic_evidence

    adapted = adapt_datto_device_semantic_evidence(
        {
            "processor": "CPU-A",
            "inventory": {"cpuModel": "CPU-B"},
        }
    )

    semantic = adapted.get("semantic_evidence", {})
    assert "processor" not in semantic
PY
else
    echo "PASS: equivalent/conflicting processor alias regression tests already present"
fi

echo "========== SECTION 4: STATIC VALIDATION =========="
git diff --check

echo "========== SECTION 5: FOCUSED TESTS =========="
.venv/bin/python -m pytest -q \
  implementation/connectors/tests/test_datto_semantic_evidence.py \
  implementation/orchestrator/tests/test_resource_evidence.py

echo "========== SECTION 6: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Equivalent provider aliases now collapse to one semantic fact while conflicting evidence still fails closed."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END DATTO SEMANTIC EQUIVALENT PROVIDER VALUE REPAIR =========="
