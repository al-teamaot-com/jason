#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC REGISTRY EQUIVALENT PROVIDER BINDING REPAIR =========="
echo "========== SECTION 1: PRECONDITIONS =========="
echo "HEAD: $(git rev-parse --short HEAD)"

for required in \
  implementation/orchestrator/semantic_knowledge_registry.py \
  implementation/orchestrator/semantic_knowledge_seed.py \
  implementation/orchestrator/tests/test_semantic_knowledge_registry.py \
  implementation/orchestrator/tests/test_semantic_knowledge_seed.py; do
  if [[ ! -f "$required" ]]; then
    echo "ERROR: required file missing: $required"
    exit 20
  fi
done

echo "========== SECTION 2: MAKE EQUIVALENT PROVIDER BINDINGS IDEMPOTENT =========="
.venv/bin/python - <<'PY'
from pathlib import Path

path = Path('implementation/orchestrator/semantic_knowledge_registry.py')
text = path.read_text()
old = '''                if existing.concept_id != binding.concept_id:\n                    raise ValueError("semantic provider field mapping is ambiguous")\n                raise ValueError("semantic provider field mapping already exists")\n        self._provider_fields.append(binding)\n        self._bump()\n'''
new = '''                if existing.concept_id != binding.concept_id:\n                    raise ValueError("semantic provider field mapping is ambiguous")\n                # Provider schemas commonly expose case/style aliases such as\n                # displayVersion and DisplayVersion. After normalization these are\n                # the same governed binding, so repeated registration is idempotent\n                # rather than a second semantic fact. Conflicting concept mappings\n                # still fail closed above.\n                return\n        self._provider_fields.append(binding)\n        self._bump()\n'''
if new in text:
    print(f'PASS: equivalent provider binding idempotence already present in {path}')
elif old in text:
    path.write_text(text.replace(old, new, 1))
    print(f'UPDATED: {path}')
else:
    raise SystemExit('ERROR: expected provider-field duplicate guard not found')
PY

echo "========== SECTION 3: ADD REGRESSION COVERAGE =========="
.venv/bin/python - <<'PY'
from pathlib import Path

path = Path('implementation/orchestrator/tests/test_semantic_knowledge_registry.py')
text = path.read_text()
marker = 'def test_equivalent_provider_field_registration_is_idempotent():'
if marker in text:
    print(f'PASS: idempotent provider-binding regression already present in {path}')
else:
    text += '''\n\ndef test_equivalent_provider_field_registration_is_idempotent():\n    registry = processor_registry()\n    promote_concept_to_active(registry, "processor.model")\n    first = SemanticProviderFieldBinding(\n        provider="datto_rmm",\n        resource_type="endpoint",\n        provider_field="cpuModel",\n        concept_id="processor.model",\n        provenance=provenance(),\n    )\n    equivalent = SemanticProviderFieldBinding(\n        provider="datto_rmm",\n        resource_type="endpoint",\n        provider_field="CPUModel",\n        concept_id="processor.model",\n        provenance=provenance(),\n    )\n    registry.add_provider_field(first)\n    version_after_first = registry.version\n    registry.add_provider_field(equivalent)\n\n    assert registry.version == version_after_first\n\n\ndef test_equivalent_provider_field_cannot_map_to_different_concept():\n    registry = processor_registry()\n    registry.add_concept(\n        SemanticConcept(\n            concept_id="processor.count",\n            canonical_label="logical processor count",\n            kind="fact",\n            provenance=provenance(),\n        )\n    )\n    registry.add_provider_field(\n        SemanticProviderFieldBinding(\n            provider="datto_rmm",\n            resource_type="endpoint",\n            provider_field="cpuModel",\n            concept_id="processor.model",\n            provenance=provenance(),\n        )\n    )\n    with pytest.raises(ValueError, match="ambiguous"):\n        registry.add_provider_field(\n            SemanticProviderFieldBinding(\n                provider="datto_rmm",\n                resource_type="endpoint",\n                provider_field="CPUModel",\n                concept_id="processor.count",\n                provenance=provenance(),\n            )\n        )\n'''
    path.write_text(text)
    print(f'UPDATED: {path}')
PY

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
echo "Equivalent normalized provider-field aliases are now idempotent when they map to the same canonical concept."
echo "Conflicting mappings still fail closed."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC REGISTRY EQUIVALENT PROVIDER BINDING REPAIR =========="
