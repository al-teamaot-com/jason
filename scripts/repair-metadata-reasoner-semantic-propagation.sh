#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START METADATA REASONER SEMANTIC PROPAGATION REPAIR =========="

echo "========== SECTION 1: CURRENT STATE =========="
git status --short

PY=.venv/bin/python
if [[ ! -x "$PY" ]]; then
  echo "ERROR: .venv/bin/python is required."
  exit 21
fi

echo "========== SECTION 2: PRESERVE SEMANTIC REQUEST CONTRACT IN METADATA PLANNING =========="
$PY - <<'PY'
from pathlib import Path
p = Path('implementation/orchestrator/resource_reasoner.py')
s = p.read_text(encoding='utf-8')
old = '''        return (\n            ResourcePlanStep(\n                capability_name=selected.capability_name,\n                arguments={\n                    **dict(inquiry.resource_selector),\n                    "requested_facts": inquiry.requested_facts,\n                    "result_intent": inquiry.result_intent,\n                    "completeness_requirement": inquiry.completeness_requirement,\n                },\n                purpose=(\n                    "retrieve the governed resource record most likely to contain "\n                    "the requested facts"\n                ),\n            ),\n        )\n'''
new = '''        arguments = {\n            **dict(inquiry.resource_selector),\n            "requested_facts": inquiry.requested_facts,\n            "result_intent": inquiry.result_intent,\n            "completeness_requirement": inquiry.completeness_requirement,\n        }\n        if inquiry.evidence_contexts:\n            arguments["evidence_contexts"] = {\n                fact: tuple(contexts)\n                for fact, contexts in inquiry.evidence_contexts.items()\n            }\n        if inquiry.relationship_type:\n            arguments["relationship_type"] = inquiry.relationship_type\n        if inquiry.temporal_semantics != "unspecified":\n            arguments["temporal_semantics"] = inquiry.temporal_semantics\n\n        return (\n            ResourcePlanStep(\n                capability_name=selected.capability_name,\n                arguments=arguments,\n                purpose=(\n                    "retrieve the governed resource record most likely to contain "\n                    "the requested facts"\n                ),\n            ),\n        )\n'''
if old in s:
    s = s.replace(old, new, 1)
elif 'arguments["evidence_contexts"]' not in s:
    raise SystemExit('ERROR: metadata resource reasoner return anchor missing')
p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 3: ADD REGRESSION COVERAGE =========="
$PY - <<'PY'
from pathlib import Path
p = Path('implementation/orchestrator/tests/test_resource_capability_catalog.py')
s = p.read_text(encoding='utf-8')
if 'def test_metadata_reasoner_preserves_semantic_evidence_and_relationship_contract()' not in s:
    s += '''\n\ndef test_metadata_reasoner_preserves_semantic_evidence_and_relationship_contract():\n    capabilities, _ = services()\n    planner = GovernedResourceInquiryPlanner(\n        registry=capabilities,\n        reasoner=MetadataResourceCapabilityReasoner(),\n    )\n\n    plan = planner.plan(\n        ResourceInquiry(\n            resource_type="endpoint",\n            resource_selector={"user_identity": "Lindsey Collins"},\n            requested_facts=("operating system display version",),\n            evidence_contexts={\n                "operating system display version": (\n                    "operating_system",\n                    "windows_release",\n                ),\n            },\n            relationship_type="logged_in_to",\n            temporal_semantics="most_recent",\n        )\n    )\n\n    assert plan.steps[0].arguments["evidence_contexts"] == {\n        "operating system display version": (\n            "operating_system",\n            "windows_release",\n        ),\n    }\n    assert plan.steps[0].arguments["relationship_type"] == "logged_in_to"\n    assert plan.steps[0].arguments["temporal_semantics"] == "most_recent"\n'''
    p.write_text(s, encoding='utf-8')
    print('UPDATED:', p)
else:
    print('PASS: regression test already present')
PY

echo "========== SECTION 4: STATIC VALIDATION =========="
git diff --check
$PY -m py_compile implementation/orchestrator/resource_reasoner.py

echo "========== SECTION 5: FOCUSED TESTS =========="
$PY -m pytest -q \
  implementation/orchestrator/tests/test_resource_capability_catalog.py \
  implementation/orchestrator/tests/test_resource_evidence.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_conversation_resource_intent.py

echo "========== SECTION 6: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Metadata resource planning now preserves provider-neutral evidence, relationship, and temporal semantics."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END METADATA REASONER SEMANTIC PROPAGATION REPAIR =========="
