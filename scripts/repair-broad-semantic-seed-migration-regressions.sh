#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START BROAD SEMANTIC SEED MIGRATION REGRESSION REPAIR =========="
echo "========== SECTION 1: CURRENT STATE =========="
git status --short

echo "========== SECTION 2: ADD ACTIVE RELATIONSHIP COLLECTION READ API =========="
.venv/bin/python - <<'PY'
from pathlib import Path

path = Path("implementation/orchestrator/semantic_knowledge_registry.py")
text = path.read_text()

if "def active_relationships(self)" not in text:
    anchor = '''    def active_relationship(self, relationship_id: str) -> SemanticRelationshipDefinition | None:\n        relationship = self._relationships.get(relationship_id)\n        if relationship is None or relationship.state is not SemanticLifecycleState.ACTIVE:\n            return None\n        return relationship\n'''
    replacement = anchor + '''\n    def active_relationships(self) -> tuple[SemanticRelationshipDefinition, ...]:\n        \"\"\"Return all currently authoritative relationship definitions.\"\"\"\n        return tuple(\n            relationship\n            for relationship in self._relationships.values()\n            if relationship.state is SemanticLifecycleState.ACTIVE\n        )\n'''
    if anchor not in text:
        raise SystemExit("ERROR: active_relationship anchor missing")
    text = text.replace(anchor, replacement, 1)
    path.write_text(text)
    print(f"UPDATED: {path}")
else:
    print(f"PASS: {path} already exposes active_relationships()")
PY

echo "========== SECTION 3: REPAIR STALE LEGACY FALLBACK REGRESSION =========="
.venv/bin/python - <<'PY'
from pathlib import Path

path = Path("implementation/orchestrator/tests/test_semantic_fact_resolver.py")
text = path.read_text()

old = '''def test_unmigrated_concept_uses_legacy_compatibility_fallback():\n    resolver = SemanticFactResolver()\n    result = resolver.resolve("BIOS")\n    assert result is not None\n    assert result.canonical_fact == "bios version"\n    assert result.source == "canonical_fact_vocabulary_fallback"\n'''
new = '''def test_bios_uses_registry_after_broad_seed_migration():\n    resolver = SemanticFactResolver()\n    result = resolver.resolve("BIOS")\n    assert result is not None\n    assert result.canonical_fact == "bios version"\n    assert result.concept_id == "firmware.bios.version"\n    assert result.source == "semantic_knowledge_registry"\n\n\ndef test_legacy_compatibility_fallback_remains_available_for_unmigrated_registry():\n    from orchestrator.canonical_fact_vocabulary import DEFAULT_CANONICAL_FACT_VOCABULARY\n    from orchestrator.semantic_knowledge_registry import SemanticKnowledgeRegistry\n\n    resolver = SemanticFactResolver(\n        registry=SemanticKnowledgeRegistry(),\n        legacy_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,\n    )\n    result = resolver.resolve("BIOS")\n    assert result is not None\n    assert result.canonical_fact == "bios version"\n    assert result.source == "canonical_fact_vocabulary_fallback"\n'''

if old in text:
    text = text.replace(old, new, 1)
elif "def test_bios_uses_registry_after_broad_seed_migration" in text:
    print("PASS: migrated BIOS regression already repaired")
else:
    raise SystemExit("ERROR: stale BIOS fallback regression anchor missing")

path.write_text(text)
print(f"UPDATED: {path}")
PY

echo "========== SECTION 4: ADD REGISTRY READ API REGRESSION =========="
.venv/bin/python - <<'PY'
from pathlib import Path

path = Path("implementation/orchestrator/tests/test_semantic_knowledge_registry.py")
text = path.read_text()
marker = "def test_active_relationships_returns_only_authoritative_relationships():"
if marker not in text:
    text += '''\n\ndef test_active_relationships_returns_only_authoritative_relationships():\n    registry = SemanticKnowledgeRegistry()\n    relationship = SemanticRelationshipDefinition(\n        relationship_id="person.assigned_to.ticket",\n        subject_type="person",\n        target_type="ticket",\n    )\n    registry.add_relationship(relationship)\n    assert registry.active_relationships() == ()\n    for state in (\n        SemanticLifecycleState.REVIEWED,\n        SemanticLifecycleState.APPROVED,\n        SemanticLifecycleState.ACTIVE,\n    ):\n        registry.transition_relationship(relationship.relationship_id, state)\n    assert tuple(item.relationship_id for item in registry.active_relationships()) == (\n        "person.assigned_to.ticket",\n    )\n'''
    path.write_text(text)
    print(f"UPDATED: {path}")
else:
    print(f"PASS: {path} already contains active_relationships regression")
PY

echo "========== SECTION 5: STATIC VALIDATION =========="
git diff --check

echo "========== SECTION 6: FOCUSED TESTS =========="
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_semantic_knowledge_registry.py \
  implementation/orchestrator/tests/test_semantic_knowledge_seed.py \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_conversation_resource_intent.py

echo "========== SECTION 7: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Broad semantic seed migration regressions repaired."
echo "The registry now exposes an authoritative relationship collection read API."
echo "BIOS is correctly treated as registry-backed after migration while legacy fallback remains explicitly tested with an unmigrated registry."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END BROAD SEMANTIC SEED MIGRATION REGRESSION REPAIR =========="
