#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START CANONICAL FACT VOCABULARY FOUNDATION =========="

echo "========== SECTION 1: PRECONDITIONS =========="
echo "HEAD: $(git rev-parse --short HEAD)"

# This helper is intentionally idempotent. It may be rerun after a partial
# validation failure without duplicating source/test blocks.

echo "========== SECTION 2: CREATE PROVIDER-NEUTRAL CANONICAL FACT VOCABULARY =========="
cat > implementation/orchestrator/canonical_fact_vocabulary.py <<'PY'
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable


@dataclass(frozen=True, slots=True)
class CanonicalFactDefinition:
    """Provider-neutral fact concept and its human recognition vocabulary.

    Aliases are recognition input only. The canonical fact is what passes through
    governed inquiry/planning/evidence contracts. Expected shape is descriptive
    contract metadata; provider evidence validation is applied in a later layer.
    """

    canonical_fact: str
    aliases: tuple[str, ...]
    expected_shape: str


class CanonicalFactVocabulary:
    """Normalize varied human fact wording to a small governed vocabulary."""

    def __init__(self, definitions: Iterable[CanonicalFactDefinition]) -> None:
        self._definitions = tuple(definitions)
        aliases: dict[str, CanonicalFactDefinition] = {}
        for definition in self._definitions:
            for raw in (definition.canonical_fact, *definition.aliases):
                normalized = self.normalize_text(raw)
                if not normalized:
                    continue
                existing = aliases.get(normalized)
                if existing is not None and existing != definition:
                    raise ValueError(
                        f"canonical fact alias is ambiguous: {raw!r}"
                    )
                aliases[normalized] = definition
        self._aliases = aliases

    @staticmethod
    def normalize_text(value: str) -> str:
        return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())

    @property
    def definitions(self) -> tuple[CanonicalFactDefinition, ...]:
        return self._definitions

    def resolve(self, value: str) -> CanonicalFactDefinition | None:
        normalized = self.normalize_text(value)
        if not normalized:
            return None

        exact = self._aliases.get(normalized)
        if exact is not None:
            return exact

        # Bounded typo tolerance is deliberately conservative. It applies only to
        # one-token human fact labels and only when exactly one governed alias is a
        # very close match. Semantic ambiguity must continue through bounded
        # reasoning or fail closed rather than being guessed here.
        if " " in normalized or len(normalized) < 4:
            return None

        candidates: list[tuple[float, CanonicalFactDefinition]] = []
        for alias, definition in self._aliases.items():
            if " " in alias:
                continue
            score = SequenceMatcher(a=normalized, b=alias).ratio()
            if score >= 0.80:
                candidates.append((score, definition))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0], reverse=True)
        best_score = candidates[0][0]
        best = {
            item[1]
            for item in candidates
            if abs(item[0] - best_score) < 0.03
        }
        if len(best) != 1:
            return None
        return next(iter(best))

    def canonicalize(self, value: str) -> str:
        definition = self.resolve(value)
        return definition.canonical_fact if definition is not None else value.strip()


DEFAULT_CANONICAL_FACT_VOCABULARY = CanonicalFactVocabulary(
    (
        CanonicalFactDefinition(
            canonical_fact="processor model",
            aliases=(
                "processor",
                "cpu",
                "cpu model",
                "processor name",
                "cpu name",
            ),
            expected_shape="descriptive_string",
        ),
        CanonicalFactDefinition(
            canonical_fact="logical processor count",
            aliases=(
                "logical processors",
                "logical processor count",
                "cpu count",
                "processor count",
                "threads",
                "thread count",
            ),
            expected_shape="integer_count",
        ),
        CanonicalFactDefinition(
            canonical_fact="total memory",
            aliases=(
                "memory",
                "ram",
                "physical memory",
                "installed memory",
                "total ram",
                "memory total",
            ),
            expected_shape="capacity",
        ),
        CanonicalFactDefinition(
            canonical_fact="operating system display version",
            aliases=(
                "windows display version",
                "displayversion",
                "windows release version",
                "windows feature version",
                "os display version",
            ),
            expected_shape="descriptive_string",
        ),
        CanonicalFactDefinition(
            canonical_fact="operating system build",
            aliases=(
                "windows build",
                "os build",
                "operating system build number",
                "windows build number",
            ),
            expected_shape="descriptive_string",
        ),
        CanonicalFactDefinition(
            canonical_fact="operating system",
            aliases=(
                "os",
                "windows version",
                "operating system version",
            ),
            expected_shape="descriptive_string",
        ),
        CanonicalFactDefinition(
            canonical_fact="bios version",
            aliases=("bios", "bios version"),
            expected_shape="descriptive_string",
        ),
        CanonicalFactDefinition(
            canonical_fact="network adapters",
            aliases=("network adapter", "network adapters", "nic", "nics"),
            expected_shape="collection",
        ),
        CanonicalFactDefinition(
            canonical_fact="logical disks",
            aliases=("logical disk", "logical disks", "disk", "disks"),
            expected_shape="collection",
        ),
        CanonicalFactDefinition(
            canonical_fact="display adapters",
            aliases=(
                "display adapter",
                "display adapters",
                "video board",
                "video boards",
                "graphics adapter",
                "graphics adapters",
                "gpu",
            ),
            expected_shape="collection",
        ),
    )
)
PY

echo "WROTE: implementation/orchestrator/canonical_fact_vocabulary.py"

echo "========== SECTION 3: NORMALIZE REASONED REQUESTED FACTS =========="
python3 - <<'PY'
from pathlib import Path

p = Path('implementation/orchestrator/conversation_resource_intent.py')
s = p.read_text(encoding='utf-8')

import_anchor = 'from .resource_inquiry import GovernedResourceInquiryPlanner, ResourceInquiry\n'
import_line = 'from .canonical_fact_vocabulary import CanonicalFactVocabulary\n'
if import_line not in s:
    if import_anchor not in s:
        raise SystemExit('ERROR: resource intent import anchor missing')
    s = s.replace(import_anchor, import_line + import_anchor, 1)

old_decl = '''@dataclass(frozen=True, slots=True)
class ReasonedResourceInquiryInterpreter:
    reasoner: StructuredResourceInquiryReasoner
'''
new_decl = '''@dataclass(frozen=True, slots=True)
class ReasonedResourceInquiryInterpreter:
    reasoner: StructuredResourceInquiryReasoner
    fact_vocabulary: CanonicalFactVocabulary | None = None
'''
if old_decl in s:
    s = s.replace(old_decl, new_decl, 1)
elif new_decl not in s:
    raise SystemExit('ERROR: reasoned interpreter declaration anchor missing')

old = '''        return ResourceInquiry(
            resource_type=resource_type,
            resource_selector=normalized_selector,
            requested_facts=tuple(str(item).strip() for item in requested_facts),
            execution_mode=str(proposed.get("execution_mode", "deterministic")).strip(),
'''
new = '''        normalized_facts = tuple(str(item).strip() for item in requested_facts)
        if self.fact_vocabulary is not None:
            normalized_facts = tuple(
                self.fact_vocabulary.canonicalize(item)
                for item in normalized_facts
            )

        return ResourceInquiry(
            resource_type=resource_type,
            resource_selector=normalized_selector,
            requested_facts=normalized_facts,
            execution_mode=str(proposed.get("execution_mode", "deterministic")).strip(),
'''
if old in s:
    s = s.replace(old, new, 1)
elif new not in s:
    raise SystemExit('ERROR: requested fact normalization anchor missing')

p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 4: WIRE VOCABULARY INTO PRODUCTION COMPOSITION =========="
python3 - <<'PY'
from pathlib import Path

p = Path('implementation/runtime_service/src/jason_runtime/composition.py')
s = p.read_text(encoding='utf-8')

anchor = 'from orchestrator.conversation_resource_intent import (\n'
imp = 'from orchestrator.canonical_fact_vocabulary import DEFAULT_CANONICAL_FACT_VOCABULARY\n'
if imp not in s:
    if anchor not in s:
        raise SystemExit('ERROR: composition import anchor missing')
    s = s.replace(anchor, imp + anchor, 1)

old = '''            fallback=ReasonedResourceInquiryInterpreter(
                reasoner=OllamaResourceInquiryReasoner(
                    ollama_client,
                    resource_types=resource_types,
                    selector_keys=selector_keys,
                    fact_hints=fact_hints,
                )
            ),
'''
new = '''            fallback=ReasonedResourceInquiryInterpreter(
                reasoner=OllamaResourceInquiryReasoner(
                    ollama_client,
                    resource_types=resource_types,
                    selector_keys=selector_keys,
                    fact_hints=fact_hints,
                ),
                fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
            ),
'''
if old in s:
    s = s.replace(old, new, 1)
elif new not in s:
    raise SystemExit('ERROR: production fallback construction anchor missing')

p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 5: ADD REGRESSION TESTS =========="
cat > implementation/orchestrator/tests/test_canonical_fact_vocabulary.py <<'PY'
from orchestrator.canonical_fact_vocabulary import DEFAULT_CANONICAL_FACT_VOCABULARY


def canonical(value: str) -> str:
    return DEFAULT_CANONICAL_FACT_VOCABULARY.canonicalize(value)


def test_processor_language_normalizes_to_model_concept():
    assert canonical("processor") == "processor model"
    assert canonical("CPU") == "processor model"
    assert canonical("cpu model") == "processor model"


def test_processor_count_language_is_distinct_from_model():
    assert canonical("processor count") == "logical processor count"
    assert canonical("logical processors") == "logical processor count"
    assert canonical("threads") == "logical processor count"


def test_memory_aliases_and_bounded_typo_normalize():
    assert canonical("RAM") == "total memory"
    assert canonical("memory") == "total memory"
    assert canonical("physical memory") == "total memory"
    assert canonical("memore") == "total memory"


def test_windows_display_version_is_not_graphics_display():
    assert canonical("Windows Display Version") == "operating system display version"
    assert canonical("DisplayVersion") == "operating system display version"
    assert canonical("display") == "display"
    assert canonical("GPU") == "display adapters"


def test_unknown_or_ambiguous_language_is_not_invented():
    assert canonical("temperature") == "temperature"
    assert canonical("count") == "count"
PY

python3 - <<'PY'
from pathlib import Path

p = Path('implementation/orchestrator/tests/test_conversation_resource_intent.py')
s = p.read_text(encoding='utf-8')
marker = 'def test_reasoned_requested_facts_can_be_normalized_to_canonical_vocabulary():'
if marker not in s:
    s = s.rstrip() + '''\n\n\ndef test_reasoned_requested_facts_can_be_normalized_to_canonical_vocabulary():
    from orchestrator.canonical_fact_vocabulary import DEFAULT_CANONICAL_FACT_VOCABULARY

    class CanonicalFactReasoner:
        def __init__(self, fact):
            self.fact = fact

        def propose(self, *, text, organization_id, client_id):
            return {
                "resource_type": "endpoint",
                "resource_selector": {"hostname": "AOT-50282"},
                "requested_facts": [self.fact],
                "execution_mode": "deterministic",
                "permission_mode": "observe",
                "result_intent": "summary",
                "completeness_requirement": "sufficient",
            }

    for human_fact, expected in (
        ("processor", "processor model"),
        ("CPU", "processor model"),
        ("RAM", "total memory"),
        ("memore", "total memory"),
        ("Windows Display Version", "operating system display version"),
    ):
        interpreter = ReasonedResourceInquiryInterpreter(
            CanonicalFactReasoner(human_fact),
            fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,
        )
        inquiry = interpreter.interpret(
            text=f"What is the {human_fact} for AOT-50282?",
            principal=principal(),
        )
        assert inquiry is not None
        assert inquiry.requested_facts == (expected,)
'''
p.write_text(s, encoding='utf-8')
PY

echo "Tests added."

echo "========== SECTION 6: STATIC VALIDATION =========="
git diff --check
python3 -m py_compile \
  implementation/orchestrator/canonical_fact_vocabulary.py \
  implementation/orchestrator/conversation_resource_intent.py \
  implementation/runtime_service/src/jason_runtime/composition.py

echo "========== SECTION 7: FOCUSED TESTS =========="
if command -v pytest >/dev/null 2>&1; then
  PYTEST_CMD=(pytest)
elif python3 -c 'import pytest' >/dev/null 2>&1; then
  PYTEST_CMD=(python3 -m pytest)
elif [[ -x .venv/bin/python ]] && .venv/bin/python -c 'import pytest' >/dev/null 2>&1; then
  PYTEST_CMD=(.venv/bin/python -m pytest)
elif [[ -x venv/bin/python ]] && venv/bin/python -c 'import pytest' >/dev/null 2>&1; then
  PYTEST_CMD=(venv/bin/python -m pytest)
else
  echo "ERROR: pytest is not available from PATH, python3, .venv, or venv."
  echo "No source rollback performed; static validation already passed."
  exit 30
fi

echo "Pytest runner: ${PYTEST_CMD[*]}"
"${PYTEST_CMD[@]}" -q \
  implementation/orchestrator/tests/test_canonical_fact_vocabulary.py \
  implementation/orchestrator/tests/test_conversation_resource_intent.py \
  implementation/runtime_service/tests/test_composition.py

echo "========== SECTION 8: CHANGE STATE =========="
git status --short

echo "========== RESULT =========="
echo "Canonical fact vocabulary foundation validated."
echo "This stage normalizes human fact language only; it does not yet claim provider evidence-shape correctness."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH PERFORMED."
echo "========== END CANONICAL FACT VOCABULARY FOUNDATION =========="