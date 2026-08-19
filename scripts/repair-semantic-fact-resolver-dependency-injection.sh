#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC FACT RESOLVER DEPENDENCY INJECTION REPAIR =========="
echo "========== SECTION 1: CURRENT STATE =========="
git status --short

TARGET="implementation/orchestrator/semantic_fact_resolver.py"

if [[ ! -f "$TARGET" ]]; then
  echo "ERROR: $TARGET is missing."
  exit 20
fi

echo "========== SECTION 2: ALLOW EXPLICIT REGISTRY + LEGACY FALLBACK INJECTION =========="
.venv/bin/python - <<'PY'
from pathlib import Path

path = Path("implementation/orchestrator/semantic_fact_resolver.py")
text = path.read_text(encoding="utf-8")

text = text.replace(
    "from orchestrator.semantic_knowledge_registry import SemanticConcept\n",
    "from orchestrator.semantic_knowledge_registry import SemanticConcept, SemanticKnowledgeRegistry\n",
)

old = '''    def __init__(\n        self,\n        *,\n        vocabulary: CanonicalFactVocabulary = DEFAULT_CANONICAL_FACT_VOCABULARY,\n    ) -> None:\n        self._registry = build_trusted_semantic_registry()\n        self._vocabulary = vocabulary\n'''
new = '''    def __init__(\n        self,\n        *,\n        registry: SemanticKnowledgeRegistry | None = None,\n        legacy_vocabulary: CanonicalFactVocabulary | None = DEFAULT_CANONICAL_FACT_VOCABULARY,\n        vocabulary: CanonicalFactVocabulary | None = None,\n    ) -> None:\n        # ``vocabulary`` is retained as a temporary compatibility alias for older\n        # composition/tests. New construction should use ``legacy_vocabulary``.\n        if vocabulary is not None:\n            if legacy_vocabulary is not DEFAULT_CANONICAL_FACT_VOCABULARY:\n                raise ValueError("specify either legacy_vocabulary or vocabulary, not both")\n            legacy_vocabulary = vocabulary\n        self._registry = registry if registry is not None else build_trusted_semantic_registry()\n        self._vocabulary = legacy_vocabulary\n'''

if old not in text:
    if "registry: SemanticKnowledgeRegistry | None = None" in text:
        print("PASS: dependency injection already present")
    else:
        raise SystemExit("ERROR: SemanticFactResolver constructor anchor not found")
else:
    text = text.replace(old, new, 1)

old_resolve = '''        definition = self._vocabulary.resolve(value)\n        if definition is not None:\n            return self._from_legacy(definition)\n        return None\n'''
new_resolve = '''        if self._vocabulary is not None:\n            definition = self._vocabulary.resolve(value)\n            if definition is not None:\n                return self._from_legacy(definition)\n        return None\n'''
if old_resolve in text:
    text = text.replace(old_resolve, new_resolve, 1)
elif "if self._vocabulary is not None:" not in text:
    raise SystemExit("ERROR: SemanticFactResolver.resolve fallback anchor not found")

old_legacy = '''        legacy = self._vocabulary.canonicalize_requested_facts(\n            human_text=human_text,\n            requested_facts=requested,\n        )\n        return tuple(self.canonicalize(item) for item in legacy)\n'''
new_legacy = '''        if self._vocabulary is None:\n            return tuple(self.canonicalize(item) for item in requested)\n\n        legacy = self._vocabulary.canonicalize_requested_facts(\n            human_text=human_text,\n            requested_facts=requested,\n        )\n        return tuple(self.canonicalize(item) for item in legacy)\n'''
if old_legacy in text:
    text = text.replace(old_legacy, new_legacy, 1)
elif "if self._vocabulary is None:" not in text:
    raise SystemExit("ERROR: SemanticFactResolver legacy canonicalization anchor not found")

path.write_text(text, encoding="utf-8")
print(f"UPDATED: {path}")
PY

echo "========== SECTION 3: STATIC VALIDATION ==========" 
git diff --check

BACKUP="implementation/orchestrator/semantic_fact_resolver.py.semantic-registry-wiring.bak"
if [[ -f "$BACKUP" ]]; then
  rm -f "$BACKUP"
  echo "REMOVED: stale backup artifact"
fi

echo "========== SECTION 4: FOCUSED TESTS ==========" 
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_knowledge_seed.py \
  implementation/orchestrator/tests/test_semantic_knowledge_registry.py \
  implementation/orchestrator/tests/test_conversation_resource_intent.py

echo "========== SECTION 5: CHANGE STATE ==========" 
git status --short

echo "========== RESULT ==========" 
echo "SemanticFactResolver now supports explicit governed registry injection and an optional legacy vocabulary fallback."
echo "The default runtime behavior remains registry-first with the current compatibility fallback."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC FACT RESOLVER DEPENDENCY INJECTION REPAIR =========="
