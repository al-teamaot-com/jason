#!/usr/bin/env bash
set -euo pipefail

cd /home/al/projects/jason

export PYTHONPATH="/home/al/projects/jason/implementation:/home/al/projects/jason/implementation/cap-001/src:/home/al/projects/jason/implementation/cap-002/src:/home/al/projects/jason/implementation/cap-003/src:/home/al/projects/jason/implementation/cap-007/src:/home/al/projects/jason/implementation/cli/src:/home/al/projects/jason/implementation/connectors/openclaw/src:/home/al/projects/jason/implementation/connectors/src:/home/al/projects/jason/implementation/runtime_service/src"

echo "========== START CANONICAL COLLECTION FACT NORMALIZATION =========="

echo "========== SECTION 1: PATCH CAPABILITY METADATA =========="
python3 - <<'PY'
from pathlib import Path

p = Path("implementation/orchestrator/resource_capability_catalog.py")
s = p.read_text(encoding="utf-8")

old = '''    fact_hints: str,\n    planning_guidance: str,\n) -> CapabilityDefinition:\n'''
new = '''    fact_hints: str,\n    planning_guidance: str,\n    collection_fact: str | None = None,\n) -> CapabilityDefinition:\n'''
if old in s:
    s = s.replace(old, new, 1)
elif "collection_fact: str | None = None" not in s:
    raise SystemExit("ERROR: read capability signature anchor not found")

old = '''            "fact_hints": fact_hints,\n            "planning_guidance": planning_guidance,\n'''
new = '''            "fact_hints": fact_hints,\n            **({"collection_fact": collection_fact} if collection_fact else {}),\n            "planning_guidance": planning_guidance,\n'''
if old in s:
    s = s.replace(old, new, 1)
elif '"collection_fact": collection_fact' not in s:
    raise SystemExit("ERROR: metadata anchor not found")

replacements = {
'''        planning_guidance=(\n            "Use when the human asks whether a named endpoint has alerts or asks for "\n            "alert details. Resolve a human endpoint selector before invoking the "\n            "device-scoped provider alert operation."\n        ),\n    )\n''':
'''        planning_guidance=(\n            "Use when the human asks whether a named endpoint has alerts or asks for "\n            "alert details. Resolve a human endpoint selector before invoking the "\n            "device-scoped provider alert operation."\n        ),\n        collection_fact="alerts",\n    )\n''',
'''        planning_guidance=(\n            "Use when the human asks what software/applications/programs are installed "\n            "on a managed endpoint or asks whether particular software is present."\n        ),\n    )\n''':
'''        planning_guidance=(\n            "Use when the human asks what software/applications/programs are installed "\n            "on a managed endpoint or asks whether particular software is present."\n        ),\n        collection_fact="software",\n    )\n''',
'''        planning_guidance=(\n            "Use for account/site-wide alert questions rather than a question about "\n            "one already identified endpoint."\n        ),\n    )\n''':
'''        planning_guidance=(\n            "Use for account/site-wide alert questions rather than a question about "\n            "one already identified endpoint."\n        ),\n        collection_fact="alerts",\n    )\n''',
'''        planning_guidance=(\n            "Use for questions about managed Datto RMM sites or site discovery."\n        ),\n    )\n''':
'''        planning_guidance=(\n            "Use for questions about managed Datto RMM sites or site discovery."\n        ),\n        collection_fact="sites",\n    )\n''',
}

for old_block, new_block in replacements.items():
    if old_block in s:
        s = s.replace(old_block, new_block, 1)

p.write_text(s, encoding="utf-8")
print("Updated:", p)
PY

echo "========== SECTION 2: PROPAGATE CANONICAL COLLECTION FACT =========="
python3 - <<'PY'
from pathlib import Path

p = Path("implementation/runtime_service/src/jason_runtime/composition.py")
s = p.read_text(encoding="utf-8")

old = '''        fact_hints = tuple(\n            item.strip()\n            for item in metadata.get("fact_hints", "").split(",")\n            if item.strip()\n        )\n\n        # A zero-selector interpretation is safe only for resource contracts\n'''
new = '''        fact_hints = tuple(\n            item.strip()\n            for item in metadata.get("fact_hints", "").split(",")\n            if item.strip()\n        )\n        collection_fact = metadata.get("collection_fact", "").strip()\n\n        # A zero-selector interpretation is safe only for resource contracts\n'''
if old in s:
    s = s.replace(old, new, 1)
elif 'collection_fact = metadata.get("collection_fact"' not in s:
    raise SystemExit("ERROR: deterministic contract metadata anchor not found")

old = '''                "fact_hints": fact_hints,\n                "selector_required": selector_required,\n'''
new = '''                "fact_hints": fact_hints,\n                "collection_fact": collection_fact,\n                "selector_required": selector_required,\n'''
if old in s:
    s = s.replace(old, new, 1)
elif '"collection_fact": collection_fact' not in s:
    raise SystemExit("ERROR: deterministic contract output anchor not found")

p.write_text(s, encoding="utf-8")
print("Updated:", p)
PY

echo "========== SECTION 3: NORMALIZE EXHAUSTIVE COLLECTION REQUESTS =========="
python3 - <<'PY'
from pathlib import Path

p = Path("implementation/orchestrator/conversation_resource_intent.py")
s = p.read_text(encoding="utf-8")

old = '''        result_intent, completeness_requirement = (\n            self._result_outcome(normalized_text)\n        )\n\n        return ResourceInquiry(\n            resource_type=resource_types[0],\n            resource_selector={},\n            requested_facts=(requested_fact,),\n'''
new = '''        result_intent, completeness_requirement = (\n            self._result_outcome(normalized_text)\n        )\n\n        # Fact hints are recognition aliases, not evidence contracts. When the\n        # human requests an exhaustive collection outcome, normalize any matched\n        # singular/plural/synonym hint to the capability's canonical collection\n        # fact. This keeps varied language from collapsing a collection into one\n        # arbitrary nested scalar.\n        collection_fact = str(contract.get("collection_fact", "")).strip()\n        if (\n            collection_fact\n            and result_intent in {"enumerate", "count"}\n            and completeness_requirement == "complete"\n        ):\n            requested_fact = collection_fact\n\n        return ResourceInquiry(\n            resource_type=resource_types[0],\n            resource_selector={},\n            requested_facts=(requested_fact,),\n'''
if old in s:
    s = s.replace(old, new, 1)
elif "Fact hints are recognition aliases" not in s:
    raise SystemExit("ERROR: deterministic outcome anchor not found")

p.write_text(s, encoding="utf-8")
print("Updated:", p)
PY

echo "========== SECTION 4: ADD REGRESSION TEST =========="
python3 - <<'PY'
from pathlib import Path

p = Path("implementation/orchestrator/tests/test_conversation_resource_intent.py")
s = p.read_text(encoding="utf-8")

marker = "def test_metadata_first_normalizes_complete_collection_fact_aliases"
if marker not in s:
    s += r'''


def test_metadata_first_normalizes_complete_collection_fact_aliases():
    class ForbiddenFallback:
        def interpret(self, **kwargs):
            raise AssertionError("fallback must not be called")

    interpreter = MetadataFirstResourceInquiryInterpreter(
        contracts=(
            {
                "capability_name": "management.site.search",
                "resource_types": ("management_site",),
                "selector_keys": ("name", "site", "site_id"),
                "fact_hints": (
                    "site",
                    "sites",
                    "client site",
                    "managed site",
                ),
                "collection_fact": "sites",
                "selector_required": False,
            },
        ),
        fallback=ForbiddenFallback(),
    )

    inquiry = interpreter.interpret(
        text="List every site in Datto RMM",
        principal=principal(),
    )

    assert inquiry.requested_facts == ("sites",)
    assert inquiry.result_intent == "enumerate"
    assert inquiry.completeness_requirement == "complete"
'''

p.write_text(s, encoding="utf-8")
print("Updated:", p)
PY

echo "========== SECTION 5: VALIDATE =========="
git diff --check
./.venv-test/bin/python -m py_compile \
  implementation/orchestrator/resource_capability_catalog.py \
  implementation/orchestrator/conversation_resource_intent.py \
  implementation/runtime_service/src/jason_runtime/composition.py

./.venv-test/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_conversation_resource_intent.py \
  implementation/orchestrator/tests/test_resource_capability_catalog.py \
  implementation/orchestrator/tests/test_resource_evidence.py \
  implementation/runtime_service/tests/test_composition.py

echo "========== RESULT =========="
echo "Canonical collection fact normalization patch validated."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH PERFORMED."
echo "========== END CANONICAL COLLECTION FACT NORMALIZATION =========="
