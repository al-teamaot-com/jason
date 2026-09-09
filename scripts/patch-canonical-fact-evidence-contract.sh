#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START CANONICAL FACT EVIDENCE CONTRACT =========="

echo "========== SECTION 1: PRECONDITIONS =========="
if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: worktree must be clean before applying canonical fact evidence contract."
  git status --short
  exit 20
fi

echo "HEAD: $(git rev-parse --short HEAD)"

echo "========== SECTION 2: EXTEND CANONICAL FACT DEFINITIONS WITH EVIDENCE HINTS =========="
python3 - <<'PY'
from pathlib import Path
p = Path('implementation/orchestrator/canonical_fact_vocabulary.py')
s = p.read_text(encoding='utf-8')
if 'evidence_hints: tuple[str, ...] = ()' not in s:
    s = s.replace(
        '    expected_shape: str\n',
        '    expected_shape: str\n    evidence_hints: tuple[str, ...] = ()\n',
        1,
    )

repls = {
'            expected_shape="descriptive_string",\n        ),\n        CanonicalFactDefinition(\n            canonical_fact="logical processor count"': '            expected_shape="descriptive_string",\n            evidence_hints=("model", "name", "caption", "processor", "cpu"),\n        ),\n        CanonicalFactDefinition(\n            canonical_fact="logical processor count"',
'            expected_shape="integer_count",\n        ),\n        CanonicalFactDefinition(\n            canonical_fact="total memory"': '            expected_shape="integer_count",\n            evidence_hints=("logical processors", "logical processor count", "thread count", "threads"),\n        ),\n        CanonicalFactDefinition(\n            canonical_fact="total memory"',
'            expected_shape="capacity",\n        ),\n        CanonicalFactDefinition(\n            canonical_fact="operating system display version"': '            expected_shape="capacity",\n            evidence_hints=("total physical memory", "physical memory", "total memory", "memory", "ram"),\n        ),\n        CanonicalFactDefinition(\n            canonical_fact="operating system display version"',
'            expected_shape="descriptive_string",\n        ),\n        CanonicalFactDefinition(\n            canonical_fact="operating system build"': '            expected_shape="descriptive_string",\n            evidence_hints=("displayversion", "display version", "releaseid", "release id"),\n        ),\n        CanonicalFactDefinition(\n            canonical_fact="operating system build"',
}
for old, new in repls.items():
    if old in s:
        s = s.replace(old, new, 1)

p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 3: ADD SHAPE VALIDATION + EVIDENCE VOCABULARY =========="
python3 - <<'PY'
from pathlib import Path
p = Path('implementation/orchestrator/resource_evidence.py')
s = p.read_text(encoding='utf-8')
imp = 'from .canonical_fact_vocabulary import CanonicalFactVocabulary\n'
anchor = 'from .contracts import OrchestrationResult, OrchestrationStatus\n'
if imp not in s:
    s = s.replace(anchor, anchor + imp, 1)

old = '''@dataclass(frozen=True, slots=True)
class GovernedResourceEvidenceInterpreter:
    reasoner: StructuredResourceEvidenceReasoner
'''
new = '''@dataclass(frozen=True, slots=True)
class GovernedResourceEvidenceInterpreter:
    reasoner: StructuredResourceEvidenceReasoner
    fact_vocabulary: CanonicalFactVocabulary | None = None
'''
if old in s:
    s = s.replace(old, new, 1)

needle = '''        unresolved = tuple(
            fact for fact in requested_facts if fact not in verified_by_fact
        )

        if unresolved:
'''
replacement = '''        unresolved = tuple(
            fact for fact in requested_facts if fact not in verified_by_fact
        )

        reasoner_facts = unresolved
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
if needle in s:
    s = s.replace(needle, replacement, 1)

s = s.replace(
'''                    requested_facts=unresolved,
                    data=data,
''',
'''                    requested_facts=reasoner_facts,
                    data=data,
''',
1,
)

# Accept only proposals for the actual canonical requested facts; evidence hints are ranking vocabulary only.
# Shape validation occurs after deterministic dereference.
shape_anchor = '''                actual = _resolve_json_pointer(data, pointer)
                verified_by_fact[requested_fact] = VerifiedResourceFact(
'''
shape_block = '''                actual = _resolve_json_pointer(data, pointer)
                if self.fact_vocabulary is not None:
                    definition = self.fact_vocabulary.resolve(requested_fact)
                    if definition is not None and not _value_matches_expected_shape(
                        actual,
                        definition.expected_shape,
                    ):
                        raise LookupError(
                            f"provider evidence has wrong shape for {requested_fact}: "
                            f"expected {definition.expected_shape}"
                        )
                verified_by_fact[requested_fact] = VerifiedResourceFact(
'''
if shape_anchor in s:
    s = s.replace(shape_anchor, shape_block, 1)

helper = '''\n\ndef _value_matches_expected_shape(value: Any, expected_shape: str) -> bool:\n    if expected_shape == "descriptive_string":\n        return isinstance(value, str) and bool(value.strip()) and not value.strip().isdigit()\n    if expected_shape == "integer_count":\n        return isinstance(value, int) and not isinstance(value, bool) and value >= 0\n    if expected_shape == "capacity":\n        if isinstance(value, (int, float)) and not isinstance(value, bool):\n            return value >= 0\n        if isinstance(value, str):\n            text = value.strip().casefold()\n            return bool(text) and any(unit in text for unit in ("kb", "mb", "gb", "tb", "bytes", "byte"))\n        return False\n    if expected_shape == "collection":\n        return isinstance(value, (list, tuple))\n    return True\n'''
if '_value_matches_expected_shape(' not in s.split('class GovernedTeamsResourceResponseRenderer')[0]:
    s = s.replace('\n\n@dataclass(frozen=True, slots=True)\nclass GovernedTeamsResourceResponseRenderer:', helper + '\n\n@dataclass(frozen=True, slots=True)\nclass GovernedTeamsResourceResponseRenderer:', 1)

p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 4: WIRE SHAPE CONTRACT INTO PRODUCTION =========="
python3 - <<'PY'
from pathlib import Path
p = Path('implementation/runtime_service/src/jason_runtime/composition.py')
s = p.read_text(encoding='utf-8')
old = '''        interpreter=GovernedResourceEvidenceInterpreter(
            reasoner=OllamaResourceEvidenceReasoner(ollama_client)
        )
'''
new = '''        interpreter=GovernedResourceEvidenceInterpreter(
            reasoner=OllamaResourceEvidenceReasoner(ollama_client),
            fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
        )
'''
if old in s:
    s = s.replace(old, new, 1)
elif new not in s:
    raise SystemExit('ERROR: production evidence interpreter anchor missing')
p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 5: ADD REGRESSION TESTS =========="
cat >> implementation/orchestrator/tests/test_canonical_fact_vocabulary.py <<'PY'


def test_canonical_facts_expose_provider_neutral_evidence_hints():
    vocab = DEFAULT_CANONICAL_FACT_VOCABULARY
    processor = vocab.resolve("processor")
    display_version = vocab.resolve("Windows Display Version")
    assert processor is not None and "model" in processor.evidence_hints
    assert display_version is not None and "displayversion" in display_version.evidence_hints
PY

cat >> implementation/orchestrator/tests/test_resource_evidence.py <<'PY'


def test_processor_model_rejects_numeric_count_as_wrong_shape():
    from orchestrator.canonical_fact_vocabulary import DEFAULT_CANONICAL_FACT_VOCABULARY

    interpreter = GovernedResourceEvidenceInterpreter(
        Reasoner([
            {
                "requested_fact": "processor model",
                "json_pointer": "/provider_data/processors/0/logicalProcessors",
            }
        ]),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    data = result()
    data = OrchestrationResult(
        execution_id=data.execution_id,
        correlation_id=data.correlation_id,
        capability_name=data.capability_name,
        status=data.status,
        stage=data.stage,
        reason_codes=data.reason_codes,
        resolution=data.resolution,
        output={
            "provider": "datto_rmm",
            "data": {"provider_data": {"processors": [{"logicalProcessors": 8}]}},
        },
        attempts=data.attempts,
        provider_id="datto_rmm",
    )
    with pytest.raises(LookupError, match="wrong shape"):
        interpreter.interpret(result=data, requested_facts=("processor model",))


def test_processor_model_accepts_descriptive_provider_value():
    from orchestrator.canonical_fact_vocabulary import DEFAULT_CANONICAL_FACT_VOCABULARY

    interpreter = GovernedResourceEvidenceInterpreter(
        Reasoner([
            {
                "requested_fact": "processor model",
                "json_pointer": "/provider_data/processors/0/name",
            }
        ]),
        fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
    )
    data = result()
    data = OrchestrationResult(
        execution_id=data.execution_id,
        correlation_id=data.correlation_id,
        capability_name=data.capability_name,
        status=data.status,
        stage=data.stage,
        reason_codes=data.reason_codes,
        resolution=data.resolution,
        output={
            "provider": "datto_rmm",
            "data": {"provider_data": {"processors": [{"name": "Intel Core i7"}]}},
        },
        attempts=data.attempts,
        provider_id="datto_rmm",
    )
    facts = interpreter.interpret(result=data, requested_facts=("processor model",))
    assert facts[0].value == "Intel Core i7"
PY

echo "========== SECTION 6: VALIDATE =========="
git diff --check
.venv/bin/python -m py_compile \
  implementation/orchestrator/canonical_fact_vocabulary.py \
  implementation/orchestrator/resource_evidence.py \
  implementation/runtime_service/src/jason_runtime/composition.py
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_canonical_fact_vocabulary.py \
  implementation/orchestrator/tests/test_resource_evidence.py \
  implementation/runtime_service/tests/test_composition.py

echo "========== SECTION 7: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Canonical fact evidence contract validated."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH PERFORMED."
echo "========== END CANONICAL FACT EVIDENCE CONTRACT =========="
