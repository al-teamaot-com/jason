#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC REGISTRY LIVE REQUEST WIRING TARGET REPAIR =========="
echo "========== SECTION 1: CURRENT STATE =========="
git status --short

echo "========== SECTION 2: PATCH ACTUAL SEMANTIC REQUEST BRIDGE =========="
.venv/bin/python - <<'PY'
from pathlib import Path

path = Path("implementation/orchestrator/semantic_request_bridge.py")
text = path.read_text()

old_import = "from .canonical_fact_vocabulary import CanonicalFactVocabulary\n"
new_import = (
    "from .canonical_fact_vocabulary import CanonicalFactVocabulary\n"
    "from .semantic_fact_resolver import SemanticFactResolver\n"
)
if "from .semantic_fact_resolver import SemanticFactResolver" not in text:
    if old_import not in text:
        raise SystemExit("ERROR: canonical fact vocabulary import anchor missing")
    text = text.replace(old_import, new_import, 1)

old_field = "    fact_vocabulary: CanonicalFactVocabulary | None = None\n"
new_field = (
    "    fact_vocabulary: CanonicalFactVocabulary | None = None\n"
    "    fact_resolver: SemanticFactResolver | None = None\n"
)
if "fact_resolver: SemanticFactResolver | None = None" not in text:
    if old_field not in text:
        raise SystemExit("ERROR: SemanticRequestBridge fact_vocabulary field anchor missing")
    text = text.replace(old_field, new_field, 1)

old_block = '''        facts = requested_facts\n        if self.fact_vocabulary is not None:\n            facts = self.fact_vocabulary.canonicalize_requested_facts(\n                human_text=human_text,\n                requested_facts=facts,\n            )\n'''
new_block = '''        facts = requested_facts\n        if self.fact_resolver is not None:\n            resolutions = self.fact_resolver.resolve_requested_facts(\n                human_text=human_text,\n                requested_facts=facts,\n            )\n            facts = tuple(item.canonical_label for item in resolutions)\n        elif self.fact_vocabulary is not None:\n            facts = self.fact_vocabulary.canonicalize_requested_facts(\n                human_text=human_text,\n                requested_facts=facts,\n            )\n'''
if "self.fact_resolver.resolve_requested_facts" not in text:
    if old_block not in text:
        raise SystemExit("ERROR: request fact canonicalization block anchor missing")
    text = text.replace(old_block, new_block, 1)

old_constraints = '''        constraints: dict[str, SemanticEvidenceConstraint] = {}\n        if self.fact_vocabulary is not None:\n            for fact in facts:\n                definition = self.fact_vocabulary.resolve(fact)\n                if definition is None:\n                    continue\n                contexts = self._semantic_contexts(definition.canonical_fact)\n                constraints[fact] = SemanticEvidenceConstraint(\n                    contexts=contexts,\n                    expected_shape=definition.expected_shape,\n                )\n'''
new_constraints = '''        constraints: dict[str, SemanticEvidenceConstraint] = {}\n        if self.fact_resolver is not None:\n            for resolution in resolutions:\n                if resolution.expected_shape is None and not resolution.evidence_contexts:\n                    continue\n                constraints[resolution.canonical_label] = SemanticEvidenceConstraint(\n                    contexts=resolution.evidence_contexts,\n                    expected_shape=resolution.expected_shape,\n                )\n        elif self.fact_vocabulary is not None:\n            for fact in facts:\n                definition = self.fact_vocabulary.resolve(fact)\n                if definition is None:\n                    continue\n                contexts = self._semantic_contexts(definition.canonical_fact)\n                constraints[fact] = SemanticEvidenceConstraint(\n                    contexts=contexts,\n                    expected_shape=definition.expected_shape,\n                )\n'''
if "for resolution in resolutions" not in text:
    if old_constraints not in text:
        raise SystemExit("ERROR: semantic evidence constraint block anchor missing")
    text = text.replace(old_constraints, new_constraints, 1)

path.write_text(text)
print(f"UPDATED: {path}")
PY

echo "========== SECTION 3: ADD BRIDGE REGRESSION COVERAGE =========="
cat >> implementation/orchestrator/tests/test_semantic_request_bridge.py <<'PY'


def test_registry_first_fact_resolver_drives_bridge_fact_and_evidence_contexts():
    from orchestrator.semantic_fact_resolver import SemanticFactResolver
    from orchestrator.semantic_knowledge_seed import build_trusted_semantic_registry

    semantic_bridge = SemanticRequestBridge(
        fact_resolver=SemanticFactResolver(
            registry=build_trusted_semantic_registry(),
            legacy_vocabulary=None,
        )
    )

    request = semantic_bridge.build(
        human_text="What CPU does AOT-50282 have?",
        resource_type="endpoint",
        resource_selector={"hostname": "AOT-50282"},
        requested_facts=("CPU",),
        result_intent="summary",
        completeness_requirement="sufficient",
    )

    assert request.requested_facts == ("processor model",)
    assert request.evidence_constraints is not None
    constraint = request.evidence_constraints["processor model"]
    assert constraint.contexts == ("processor", "hardware_inventory")
    assert constraint.expected_shape == "descriptive_string"
PY

echo "========== SECTION 4: STATIC VALIDATION =========="ngit diff --check

echo "========== SECTION 5: FOCUSED TESTS =========="n.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_knowledge_seed.py \
  implementation/orchestrator/tests/test_conversation_resource_intent.py

echo "========== SECTION 6: CHANGE STATE =========="ngit status --short

echo "========== RESULT =========="necho "SemanticRequestBridge now consumes registry-first fact resolution when supplied, with legacy vocabulary fallback preserved."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC REGISTRY LIVE REQUEST WIRING TARGET REPAIR =========="
