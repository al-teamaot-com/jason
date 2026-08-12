#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC EVIDENCE DIRECT RESOLUTION REPAIR =========="
echo "========== SECTION 1: PRECONDITIONS =========="
echo "HEAD: $(git rev-parse --short HEAD)"

echo "========== SECTION 2: PATCH TRUSTED SEMANTIC EVIDENCE DIRECT LOOKUP =========="
.venv/bin/python - <<'PY'
from pathlib import Path

path = Path('implementation/orchestrator/resource_evidence.py')
text = path.read_text()

anchor = '''    verified: list[VerifiedResourceFact] = []\n    for requested_fact in requested_facts:\n        wanted = _normalized_field_name(requested_fact)\n        candidates: list[tuple[str, Any]] = []\n'''
replacement = '''    verified: list[VerifiedResourceFact] = []\n    for requested_fact in requested_facts:\n        wanted = _normalized_field_name(requested_fact)\n        candidates: list[tuple[str, Any]] = []\n\n        # Provider adapters may expose deterministic canonical facts beneath\n        # provider_data/semantic_evidence. Those paths are deliberately trusted\n        # only as locations, never as asserted values: Jason still dereferences\n        # the actual provider-derived value and applies semantic-context and\n        # expected-shape validation afterward. This avoids asking a language\n        # reasoner to rediscover a provider mapping that the adapter already\n        # declared explicitly.\n        if isinstance(data, Mapping):\n            provider_data = data.get("provider_data")\n            if isinstance(provider_data, Mapping):\n                semantic_root = provider_data.get("semantic_evidence")\n                if isinstance(semantic_root, Mapping):\n\n                    def walk_semantic(value: Any, pointer: str) -> None:\n                        if not isinstance(value, Mapping):\n                            return\n                        for raw_key, child in value.items():\n                            key = str(raw_key)\n                            child_pointer = f"{pointer}/{_escape_json_pointer_segment(key)}"\n                            if _normalized_field_name(key) == wanted:\n                                candidates.append((child_pointer, child))\n                            walk_semantic(child, child_pointer)\n\n                    walk_semantic(\n                        semantic_root,\n                        "/provider_data/semantic_evidence",\n                    )\n'''

if anchor not in text:
    raise SystemExit('ERROR: direct fact resolution anchor not found')
text = text.replace(anchor, replacement, 1)
path.write_text(text)
print(f'UPDATED: {path}')
PY

echo "========== SECTION 3: ADD REGRESSION COVERAGE =========="
cat >> implementation/orchestrator/tests/test_resource_evidence.py <<'PY'


def test_semantic_adapter_processor_fact_resolves_deterministically_before_reasoner():
    class NoEvidenceReasoner:
        def locate(self, *, requested_facts, data):
            raise AssertionError("semantic adapter fact should resolve without language reasoning")

    interpreter = GovernedResourceEvidenceInterpreter(
        reasoner=NoEvidenceReasoner(),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    orchestration_result = result(
        data={
            "provider_data": {
                "processor": "Intel(R) Core(TM) i7-9700F CPU @ 3.00GHz",
                "semantic_evidence": {
                    "processor": {
                        "hardware_inventory": {
                            "processor_model": "Intel(R) Core(TM) i7-9700F CPU @ 3.00GHz",
                        }
                    }
                },
            }
        }
    )

    facts = interpreter.interpret(
        result=orchestration_result,
        requested_facts=("processor model",),
        evidence_contexts={
            "processor model": ("processor", "hardware_inventory"),
        },
    )

    assert len(facts) == 1
    assert facts[0].value == "Intel(R) Core(TM) i7-9700F CPU @ 3.00GHz"
    assert facts[0].json_pointer == "/provider_data/semantic_evidence/processor/hardware_inventory/processor_model"


def test_raw_processor_field_cannot_bypass_required_semantic_context():
    class WrongPathReasoner:
        def locate(self, *, requested_facts, data):
            return ({
                "requested_fact": "processor model",
                "json_pointer": "/provider_data/processor",
            },)

    interpreter = GovernedResourceEvidenceInterpreter(
        reasoner=WrongPathReasoner(),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    orchestration_result = result(
        data={
            "provider_data": {
                "processor": "Intel(R) Core(TM) i7-9700F CPU @ 3.00GHz",
            }
        }
    )

    import pytest
    with pytest.raises(LookupError, match="outside required semantic context"):
        interpreter.interpret(
            result=orchestration_result,
            requested_facts=("processor model",),
            evidence_contexts={
                "processor model": ("processor", "hardware_inventory"),
            },
        )
PY

echo "========== SECTION 4: STATIC VALIDATION =========="
git diff --check

echo "========== SECTION 5: FOCUSED TESTS =========="
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_resource_evidence.py \
  implementation/connectors/tests/test_datto_semantic_evidence.py \
  implementation/orchestrator/tests/test_resource_capability_catalog.py

echo "========== SECTION 6: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Semantic adapter evidence now resolves deterministically before language evidence discovery."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC EVIDENCE DIRECT RESOLUTION REPAIR =========="
