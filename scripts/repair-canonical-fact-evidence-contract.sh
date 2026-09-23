#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START CANONICAL FACT EVIDENCE CONTRACT REPAIR =========="
echo "========== SECTION 1: CURRENT STATE =========="
git status --short

echo "========== SECTION 2: REPAIR SHAPE VALIDATOR + KEEP CANONICAL FACT LABELS =========="
python3 - <<'PY'
from pathlib import Path
p = Path('implementation/orchestrator/resource_evidence.py')
s = p.read_text(encoding='utf-8')

# Evidence hints must never become requested fact labels. The reasoner may only
# return the canonical facts the human requested.
old = '''        reasoner_facts = unresolved
        if self.fact_vocabulary is not None:
            expanded: list[str] = []
            for fact in unresolved:
                definition = self.fact_vocabulary.resolve(fact)
                expanded.append(fact)
                if definition is not None:
                    expanded.extend(definition.evidence_hints)
            reasoner_facts = tuple(dict.fromkeys(expanded))

        if unresolved:
'''
new = '''        if unresolved:
'''
if old in s:
    s = s.replace(old, new, 1)

s = s.replace(
'''                    requested_facts=reasoner_facts,
                    data=data,
''',
'''                    requested_facts=unresolved,
                    data=data,
''',
1,
)

if 'def _value_matches_expected_shape(' not in s:
    helper = '''\n\ndef _value_matches_expected_shape(value: Any, expected_shape: str) -> bool:\n    """Validate provider evidence against the provider-neutral fact contract."""\n    if expected_shape == "descriptive_string":\n        return isinstance(value, str) and bool(value.strip()) and not value.strip().isdigit()\n    if expected_shape == "integer_count":\n        return isinstance(value, int) and not isinstance(value, bool) and value >= 0\n    if expected_shape == "capacity":\n        if isinstance(value, (int, float)) and not isinstance(value, bool):\n            return value >= 0\n        if isinstance(value, str):\n            text = value.strip().casefold()\n            return bool(text) and any(\n                unit in text for unit in ("kb", "mb", "gb", "tb", "bytes", "byte")\n            )\n        return False\n    if expected_shape == "collection":\n        return isinstance(value, (list, tuple))\n    return True\n'''
    anchor = '\n\n@dataclass(frozen=True, slots=True)\nclass GovernedTeamsResourceResponseRenderer:'
    if anchor not in s:
        raise SystemExit('ERROR: response renderer anchor missing')
    s = s.replace(anchor, helper + anchor, 1)

p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 3: USE EVIDENCE HINTS ONLY FOR STRUCTURAL RANKING =========="
python3 - <<'PY'
from pathlib import Path
p = Path('implementation/orchestrator/ollama_reasoning.py')
s = p.read_text(encoding='utf-8')

imp = 'from .canonical_fact_vocabulary import CanonicalFactVocabulary\n'
anchor = 'from .resource_inquiry import ResourceInquiry, ResourcePlanStep\n'
if imp not in s:
    if anchor not in s:
        raise SystemExit('ERROR: ollama reasoning import anchor missing')
    s = s.replace(anchor, imp + anchor, 1)

old_sig = '''def _bounded_evidence_index(
    data: Any,
    *,
    requested_facts: tuple[str, ...] = (),
    max_entries: int = 32,
'''
new_sig = '''def _bounded_evidence_index(
    data: Any,
    *,
    requested_facts: tuple[str, ...] = (),
    fact_vocabulary: CanonicalFactVocabulary | None = None,
    max_entries: int = 32,
'''
if old_sig in s:
    s = s.replace(old_sig, new_sig, 1)
elif new_sig not in s:
    raise SystemExit('ERROR: bounded evidence index signature anchor missing')

old_words = '''    requested_words: set[str] = set()
    for fact in requested_facts:
        requested_words.update(words(fact))
'''
new_words = '''    requested_words: set[str] = set()
    for fact in requested_facts:
        requested_words.update(words(fact))
        if fact_vocabulary is not None:
            definition = fact_vocabulary.resolve(fact)
            if definition is not None:
                for hint in definition.evidence_hints:
                    requested_words.update(words(hint))
'''
if old_words in s:
    s = s.replace(old_words, new_words, 1)
elif new_words not in s:
    raise SystemExit('ERROR: requested evidence words anchor missing')

old_class = '''@dataclass(frozen=True, slots=True)
class OllamaResourceEvidenceReasoner:
    client: OllamaStructuredJsonClient
'''
new_class = '''@dataclass(frozen=True, slots=True)
class OllamaResourceEvidenceReasoner:
    client: OllamaStructuredJsonClient
    fact_vocabulary: CanonicalFactVocabulary | None = None
'''
if old_class in s:
    s = s.replace(old_class, new_class, 1)
elif new_class not in s:
    raise SystemExit('ERROR: evidence reasoner class anchor missing')

old_call = '''        evidence_index = _bounded_evidence_index(
            data,
            requested_facts=requested_facts,
        )
'''
new_call = '''        evidence_index = _bounded_evidence_index(
            data,
            requested_facts=requested_facts,
            fact_vocabulary=self.fact_vocabulary,
        )
'''
if old_call in s:
    s = s.replace(old_call, new_call, 1)
elif new_call not in s:
    raise SystemExit('ERROR: evidence index call anchor missing')

p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 4: WIRE RANKING VOCABULARY IN PRODUCTION =========="
python3 - <<'PY'
from pathlib import Path
p = Path('implementation/runtime_service/src/jason_runtime/composition.py')
s = p.read_text(encoding='utf-8')
old = 'reasoner=OllamaResourceEvidenceReasoner(ollama_client),\n'
new = '''reasoner=OllamaResourceEvidenceReasoner(
                ollama_client,
                fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
            ),
'''
if old in s:
    s = s.replace(old, new, 1)
elif new not in s:
    raise SystemExit('ERROR: production evidence reasoner construction anchor missing')
p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 5: ADD RANKING REGRESSION =========="
python3 - <<'PY'
from pathlib import Path
p = Path('implementation/orchestrator/tests/test_ollama_reasoning.py')
s = p.read_text(encoding='utf-8')
marker = 'def test_canonical_evidence_hints_rank_provider_fields_without_changing_requested_fact_labels():'
if marker not in s:
    s = s.rstrip() + '''\n\n\ndef test_canonical_evidence_hints_rank_provider_fields_without_changing_requested_fact_labels():
    from orchestrator.canonical_fact_vocabulary import DEFAULT_CANONICAL_FACT_VOCABULARY
    from orchestrator.ollama_reasoning import _bounded_evidence_index

    data = {
        "provider_data": {
            "processors": [
                {"logicalProcessors": 8, "name": "Intel Core i7"}
            ]
        }
    }
    index = _bounded_evidence_index(
        data,
        requested_facts=("processor model",),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    pointers = [item["json_pointer"] for item in index]
    assert "/provider_data/processors/0/name" in pointers[:8]
'''
p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 6: STATIC VALIDATION =========="
git diff --check
.venv/bin/python -m py_compile \
  implementation/orchestrator/canonical_fact_vocabulary.py \
  implementation/orchestrator/resource_evidence.py \
  implementation/orchestrator/ollama_reasoning.py \
  implementation/runtime_service/src/jason_runtime/composition.py

echo "========== SECTION 7: FOCUSED TESTS =========="
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_canonical_fact_vocabulary.py \
  implementation/orchestrator/tests/test_resource_evidence.py \
  implementation/orchestrator/tests/test_ollama_reasoning.py \
  implementation/runtime_service/tests/test_composition.py

echo "========== SECTION 8: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Canonical fact evidence contract repaired and validated."
echo "Evidence hints affect ranking only; canonical requested-fact labels remain authoritative."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH PERFORMED."
echo "========== END CANONICAL FACT EVIDENCE CONTRACT REPAIR =========="
