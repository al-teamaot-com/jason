#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC FACT RESOLVER BATCH RESOLUTION CONTRACT REPAIR =========="
echo "========== SECTION 1: CURRENT STATE =========="
git status --short

echo "========== SECTION 2: ALIGN RESOLVER RESULT CONTRACT WITH REQUEST BRIDGE =========="
.venv/bin/python - <<'PY'
from pathlib import Path

path = Path("implementation/orchestrator/semantic_fact_resolver.py")
text = path.read_text()

# The bridge consumes a semantic resolution object. Preserve canonical_fact as the
# durable internal name while exposing canonical_label as a compatibility/readability
# alias for callers that operate in semantic-registry terminology.
property_anchor = "    concept_id: str | None = None\n\n\nclass SemanticFactResolver:"
property_replacement = '''    concept_id: str | None = None\n\n    @property\n    def canonical_label(self) -> str:\n        return self.canonical_fact\n\n\nclass SemanticFactResolver:'''
if "def canonical_label(self)" not in text:
    if property_anchor not in text:
        raise SystemExit("ERROR: SemanticFactResolution property insertion anchor missing")
    text = text.replace(property_anchor, property_replacement, 1)

# Add a batch resolver that preserves the exact same canonicalization semantics as
# canonicalize_requested_facts, then enriches each canonical fact with governed
# shape/context metadata. Unknown facts remain represented rather than disappearing.
method_anchor = '''    def canonicalize(self, value: str) -> str:\n        resolution = self.resolve(value)\n        return resolution.canonical_fact if resolution is not None else value.strip()\n\n'''
method_replacement = '''    def canonicalize(self, value: str) -> str:\n        resolution = self.resolve(value)\n        return resolution.canonical_fact if resolution is not None else value.strip()\n\n    def resolve_requested_facts(\n        self,\n        *,\n        human_text: str,\n        requested_facts: Iterable[str],\n    ) -> tuple[SemanticFactResolution, ...]:\n        canonical = self.canonicalize_requested_facts(\n            human_text=human_text,\n            requested_facts=requested_facts,\n        )\n        resolved: list[SemanticFactResolution] = []\n        for fact in canonical:\n            resolution = self.resolve(fact)\n            if resolution is None:\n                resolution = SemanticFactResolution(\n                    canonical_fact=str(fact).strip(),\n                    expected_shape=None,\n                    evidence_contexts=(),\n                    source="unresolved_passthrough",\n                    concept_id=None,\n                )\n            resolved.append(resolution)\n        return tuple(resolved)\n\n'''
if "def resolve_requested_facts(" not in text:
    if method_anchor not in text:
        raise SystemExit("ERROR: SemanticFactResolver canonicalize method anchor missing")
    text = text.replace(method_anchor, method_replacement, 1)

path.write_text(text)
print(f"UPDATED: {path}")
PY

echo "========== SECTION 3: ADD RESOLVER CONTRACT REGRESSION COVERAGE =========="
.venv/bin/python - <<'PY'
from pathlib import Path

path = Path("implementation/orchestrator/tests/test_semantic_fact_resolver.py")
text = path.read_text()
marker = "def test_resolve_requested_facts_returns_registry_metadata_for_cpu"
if marker not in text:
    text += '''\n\ndef test_resolve_requested_facts_returns_registry_metadata_for_cpu():\n    resolver = SemanticFactResolver(\n        registry=build_trusted_semantic_registry(),\n        legacy_vocabulary=None,\n    )\n    resolutions = resolver.resolve_requested_facts(\n        human_text="What CPU does AOT-50282 have?",\n        requested_facts=("CPU",),\n    )\n    assert len(resolutions) == 1\n    resolution = resolutions[0]\n    assert resolution.canonical_fact == "processor model"\n    assert resolution.canonical_label == "processor model"\n    assert resolution.concept_id == "processor.model"\n    assert resolution.evidence_contexts == ("processor", "hardware_inventory")\n    assert resolution.expected_shape == "descriptive_string"\n\n\ndef test_resolve_requested_facts_preserves_unknown_fact_without_inventing_semantics():\n    resolver = SemanticFactResolver(\n        registry=build_trusted_semantic_registry(),\n        legacy_vocabulary=None,\n    )\n    resolutions = resolver.resolve_requested_facts(\n        human_text="What quantum widget is on AOT-50282?",\n        requested_facts=("quantum widget",),\n    )\n    assert len(resolutions) == 1\n    resolution = resolutions[0]\n    assert resolution.canonical_fact == "quantum widget"\n    assert resolution.expected_shape is None\n    assert resolution.evidence_contexts == ()\n    assert resolution.source == "unresolved_passthrough"\n'''
    path.write_text(text)
    print(f"UPDATED: {path}")
else:
    print(f"PASS: resolver batch contract tests already present in {path}")
PY

echo "========== SECTION 4: STATIC VALIDATION ==========" 
git diff --check

echo "========== SECTION 5: FOCUSED TESTS ==========" 
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_semantic_knowledge_seed.py \
  implementation/orchestrator/tests/test_conversation_resource_intent.py

echo "========== SECTION 6: CHANGE STATE ==========" 
git status --short

echo "========== RESULT ==========" 
echo "SemanticFactResolver now exposes a governed batch-resolution contract consumed by SemanticRequestBridge."
echo "Unknown facts remain unresolved passthrough values; no semantic meaning is invented."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC FACT RESOLVER BATCH RESOLUTION CONTRACT REPAIR =========="
