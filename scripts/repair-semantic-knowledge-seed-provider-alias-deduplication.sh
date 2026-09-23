#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC KNOWLEDGE SEED PROVIDER ALIAS DEDUPLICATION REPAIR =========="
echo "========== SECTION 1: CURRENT STATE =========="
git status --short

SEED="implementation/orchestrator/semantic_knowledge_seed.py"
TEST="implementation/orchestrator/tests/test_semantic_knowledge_seed.py"

if [[ ! -f "$SEED" || ! -f "$TEST" ]]; then
  echo "ERROR: semantic knowledge seed worktree files are required."
  exit 20
fi

echo "========== SECTION 2: DEDUPLICATE NORMALIZED PROVIDER ALIASES BEFORE LIFECYCLE ACTIVATION =========="
.venv/bin/python - <<'PY'
from pathlib import Path

path = Path("implementation/orchestrator/semantic_knowledge_seed.py")
text = path.read_text()

old_import = '''    SemanticTermBinding,\n)\n'''
new_import = '''    SemanticTermBinding,\n    normalize_semantic_term,\n)\n'''
if "normalize_semantic_term," not in text:
    if old_import not in text:
        raise SystemExit("ERROR: semantic registry import anchor not found")
    text = text.replace(old_import, new_import, 1)

old_loop = '''    for concept_id, provider_fields in datto_fields.items():\n        for provider_field in provider_fields:\n            registry.add_provider_field(\n                SemanticProviderFieldBinding(\n                    provider="datto_rmm",\n                    resource_type="endpoint",\n                    provider_field=provider_field,\n                    concept_id=concept_id,\n                    provenance=provenance,\n                )\n            )\n            _activate_provider_field(\n                registry,\n                provider="datto_rmm",\n                resource_type="endpoint",\n                provider_field=provider_field,\n            )\n'''
new_loop = '''    for concept_id, provider_fields in datto_fields.items():\n        seen_provider_fields: set[str] = set()\n        for provider_field in provider_fields:\n            normalized_provider_field = normalize_semantic_term(provider_field)\n            if normalized_provider_field in seen_provider_fields:\n                continue\n            seen_provider_fields.add(normalized_provider_field)\n            registry.add_provider_field(\n                SemanticProviderFieldBinding(\n                    provider="datto_rmm",\n                    resource_type="endpoint",\n                    provider_field=provider_field,\n                    concept_id=concept_id,\n                    provenance=provenance,\n                )\n            )\n            _activate_provider_field(\n                registry,\n                provider="datto_rmm",\n                resource_type="endpoint",\n                provider_field=provider_field,\n            )\n'''

if "seen_provider_fields: set[str] = set()" in text:
    print(f"PASS: normalized provider alias deduplication already present in {path}")
elif old_loop in text:
    text = text.replace(old_loop, new_loop, 1)
    path.write_text(text)
    print(f"UPDATED: {path}")
else:
    raise SystemExit("ERROR: Datto provider-field seed loop anchor not found")
PY

echo "========== SECTION 3: ADD REGRESSION COVERAGE =========="
if ! grep -q 'test_case_equivalent_provider_aliases_seed_once' "$TEST"; then
cat >> "$TEST" <<'PY'


def test_case_equivalent_provider_aliases_seed_once():
    registry = build_trusted_semantic_registry()
    lower = registry.resolve_provider_field(
        provider="datto_rmm",
        resource_type="endpoint",
        provider_field="displayVersion",
    )
    upper = registry.resolve_provider_field(
        provider="datto_rmm",
        resource_type="endpoint",
        provider_field="DisplayVersion",
    )
    assert lower is not None and upper is not None
    assert lower.concept_id == "operating_system.windows.display_version"
    assert upper.concept_id == lower.concept_id
PY
  echo "UPDATED: $TEST"
else
  echo "PASS: provider alias seed regression already present"
fi

echo "========== SECTION 4: STATIC VALIDATION =========="
git diff --check

echo "========== SECTION 5: FOCUSED TESTS =========="
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_semantic_knowledge_registry.py \
  implementation/orchestrator/tests/test_semantic_knowledge_seed.py \
  implementation/orchestrator/tests/test_canonical_fact_vocabulary.py \
  implementation/orchestrator/tests/test_semantic_resource_request.py

echo "========== SECTION 6: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Trusted semantic seed now deduplicates provider aliases by normalized field identity before lifecycle activation."
echo "Strict lifecycle transitions remain unchanged; conflicting semantic mappings still fail closed."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC KNOWLEDGE SEED PROVIDER ALIAS DEDUPLICATION REPAIR =========="
