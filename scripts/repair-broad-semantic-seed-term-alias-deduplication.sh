#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START BROAD SEMANTIC SEED TERM ALIAS DEDUPLICATION REPAIR =========="
echo "========== SECTION 1: CURRENT STATE =========="
git status --short

echo "========== SECTION 2: DEDUPLICATE NORMALIZED TERM ALIASES BEFORE ACTIVATION =========="
.venv/bin/python - <<'PY'
from pathlib import Path

path = Path("implementation/orchestrator/semantic_knowledge_seed.py")
text = path.read_text()

old = '''    for concept_id, aliases in broad_terms.items():
        for term in aliases:
            registry.add_term(SemanticTermBinding(term=term, concept_id=concept_id, provenance=provenance))
            _activate_term(registry, term=term)
'''

new = '''    seen_broad_terms: dict[tuple[str, str], str] = {}
    for concept_id, aliases in broad_terms.items():
        for term in aliases:
            normalized_term = normalize_semantic_term(term)
            key = ("global", normalized_term)
            existing_concept_id = seen_broad_terms.get(key)
            if existing_concept_id is not None:
                if existing_concept_id != concept_id:
                    raise ValueError(
                        f"broad semantic term is ambiguous: {term!r} maps to both "
                        f"{existing_concept_id!r} and {concept_id!r}"
                    )
                continue
            seen_broad_terms[key] = concept_id
            registry.add_term(SemanticTermBinding(term=term, concept_id=concept_id, provenance=provenance))
            _activate_term(registry, term=term)
'''

if new in text:
    print(f"PASS: normalized broad-term deduplication already present in {path}")
elif old in text:
    text = text.replace(old, new, 1)
    path.write_text(text)
    print(f"UPDATED: {path}")
else:
    raise SystemExit("ERROR: broad term registration block not found")
PY

echo "========== SECTION 3: ADD DEDUPLICATION REGRESSION COVERAGE =========="
TEST_FILE="implementation/orchestrator/tests/test_semantic_knowledge_seed.py"
if grep -q '^def test_broad_seed_collapses_equivalent_normalized_term_aliases' "$TEST_FILE"; then
  echo "PASS: broad-term alias deduplication regression already present"
else
cat >> "$TEST_FILE" <<'PY'


def test_broad_seed_collapses_equivalent_normalized_term_aliases():
    registry = build_trusted_semantic_registry()
    spaced = registry.resolve_term("last check in")
    hyphenated = registry.resolve_term("last check-in")
    assert spaced is not None and hyphenated is not None
    assert spaced.concept_id == "endpoint.last_seen"
    assert hyphenated.concept_id == "endpoint.last_seen"
PY
  echo "UPDATED: $TEST_FILE"
fi

echo "========== SECTION 4: STATIC VALIDATION =========="
git diff --check

echo "========== SECTION 5: FOCUSED TESTS =========="
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_semantic_knowledge_seed.py \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_request_bridge.py \
  implementation/orchestrator/tests/test_semantic_knowledge_registry.py \
  implementation/orchestrator/tests/test_conversation_resource_intent.py

echo "========== SECTION 6: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Broad semantic seed now deduplicates equivalent human aliases by normalized term identity before lifecycle activation."
echo "Conflicting mappings for the same normalized term still fail closed."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END BROAD SEMANTIC SEED TERM ALIAS DEDUPLICATION REPAIR =========="
