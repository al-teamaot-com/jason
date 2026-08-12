#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START CANONICAL FACT VOCABULARY FOUNDATION =========="

echo "========== SECTION 1: PRECONDITIONS =========="
if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: worktree/index contains uncommitted changes."
  git status --short
  exit 20
fi

echo "HEAD: $(git rev-parse --short HEAD)"

echo "========== SECTION 2: CREATE PROVIDER-NEUTRAL CANONICAL FACT VOCABULARY =========="
cat > implementation/orchestrator/canonical_fact_vocabulary.py <<'PY'
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable


@dataclass(frozen=True, slots=True)
class CanonicalFactDefinition:
    fact_id: str
    canonical_label: str
    aliases: tuple[str, ...]
    resource_types: tuple[str, ...]
    expected_shape: str

    @property
    def recognition_terms(self) -> tuple[str, ...]:
        return (self.canonical_label, *self.aliases)


@dataclass(frozen=True, slots=True)
class CanonicalFactVocabulary:
    definitions: tuple[CanonicalFactDefinition, ...]
    fuzzy_threshold: float = 0.80
    fuzzy_margin: float = 0.08

    def normalize(
        self,
        value: str,
        *,
        resource_type: str | None = None,
    ) -> str:
        """Normalize human/provider-neutral wording to one canonical fact label.

        Exact aliases win. A bounded fuzzy match is allowed only for a single clear
        candidate and is intended for ordinary misspellings, not semantic guessing.
        Unknown/ambiguous wording is preserved so the existing bounded reasoner can
        continue to handle facts outside this initial vocabulary.
        """

        raw = value.strip()
        normalized = _normalize(raw)
        if not normalized:
            return raw

        candidates = tuple(self._eligible(resource_type))
        exact: list[CanonicalFactDefinition] = []
        for definition in candidates:
            if any(_normalize(term) == normalized for term in definition.recognition_terms):
                exact.append(definition)

        if len(exact) == 1:
            return exact[0].canonical_label
        if len(exact) > 1:
            return raw

        # Fuzzy matching is intentionally limited to reasonably specific tokens.
        # This handles misspellings such as "memore" -> "memory" while avoiding
        # broad semantic inference such as "display" -> Windows DisplayVersion.
        if len(normalized) < 5:
            return raw

        scored: list[tuple[float, CanonicalFactDefinition]] = []
        for definition in candidates:
            best = max(
                SequenceMatcher(None, normalized, _normalize(term)).ratio()
                for term in definition.recognition_terms
                if _normalize(term)
            )
            scored.append((best, definition))

        scored.sort(key=lambda item: item[0], reverse=True)
        if not scored or scored[0][0] < self.fuzzy_threshold:
            return raw

        runner_up = scored[1][0] if len(scored) > 1 else 0.0
        if scored[0][0] - runner_up < self.fuzzy_margin:
            return raw

        return scored[0][1].canonical_label

    def aliases_for_resource_types(self, resource_types: Iterable[str]) -> tuple[str, ...]:
        allowed = {item.strip() for item in resource_types if item.strip()}
        values: list[str] = []
        for definition in self.definitions:
            if allowed and not allowed.intersection(definition.resource_types):
                continue
            for term in definition.recognition_terms:
                if term not in values:
                    values.append(term)
        return tuple(values)

    def definition_for_label(self, label: str) -> CanonicalFactDefinition | None:
        normalized = _normalize(label)
        matches = [
            definition
            for definition in self.definitions
            if _normalize(definition.canonical_label) == normalized
        ]
        return matches[0] if len(matches) == 1 else None

    def _eligible(self, resource_type: str | None) -> Iterable[CanonicalFactDefinition]:
        wanted = (resource_type or "").strip()
        if not wanted:
            return self.definitions
        return tuple(
            definition
            for definition in self.definitions
            if wanted in definition.resource_types
        )


def _normalize(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


DEFAULT_CANONICAL_FACT_VOCABULARY = CanonicalFactVocabulary(
    definitions=(
        CanonicalFactDefinition(
            fact_id="endpoint.processor.model",
            canonical_label="processor model",
            aliases=(
                "processor",
                "cpu",
                "cpu model",
                "processor name",
                "cpu name",
            ),
            resource_types=("endpoint", "endpoint_audit"),
            expected_shape="text",
        ),
        CanonicalFactDefinition(
            fact_id="endpoint.processor.logical_count",
            canonical_label="logical processor count",
            aliases=(
                "logical processors",
                "logical cpu count",
                "processor count",
                "cpu count",
                "threads",
                "thread count",
            ),
            resource_types=("endpoint", "endpoint_audit"),
            expected_shape="integer",
        ),
        CanonicalFactDefinition(
            fact_id="endpoint.memory.total",
            canonical_label="total memory",
            aliases=(
                "memory",
                "ram",
                "physical memory",
                "installed memory",
                "memory size",
                "total ram",
            ),
            resource_types=("endpoint", "endpoint_audit"),
            expected_shape="capacity",
        ),
        CanonicalFactDefinition(
            fact_id="endpoint.os.display_version",
            canonical_label="operating system display version",
            aliases=(
                "windows display version",
                "display version",
                "windows release",
                "windows release version",
            ),
            resource_types=("endpoint", "endpoint_audit"),
            expected_shape="text",
        ),
        CanonicalFactDefinition(
            fact_id="endpoint.os.build",
            canonical_label="operating system build",
            aliases=(
                "windows build",
                "os build",
                "build number",
                "windows build number",
            ),
            resource_types=("endpoint", "endpoint_audit"),
            expected_shape="text",
        ),
        CanonicalFactDefinition(
            fact_id="endpoint.os.name",
            canonical_label="operating system",
            aliases=(
                "os",
                "windows edition",
                "operating system name",
            ),
            resource_types=("endpoint", "endpoint_audit"),
            expected_shape="text",
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

old_import = 'from .resource_inquiry import GovernedResourceInquiryPlanner, ResourceInquiry\n'
new_import = (
    'from .canonical_fact_vocabulary import CanonicalFactVocabulary\n'
    'from .resource_inquiry import GovernedResourceInquiryPlanner, ResourceInquiry\n'
)
if new_import not in s:
    if old_import not in s:
        raise SystemExit('ERROR: resource inquiry import anchor missing')
    s = s.replace(old_import, new_import, 1)

old = '''@dataclass(frozen=True, slots=True)\nclass ReasonedResourceInquiryInterpreter:\n    reasoner: StructuredResourceInquiryReasoner\n'''
new = '''@dataclass(frozen=True, slots=True)\nclass ReasonedResourceInquiryInterpreter:\n    reasoner: StructuredResourceInquiryReasoner\n    fact_vocabulary: CanonicalFactVocabulary | None = None\n'''
if new not in s:
    if old not in s:
        raise SystemExit('ERROR: reasoned interpreter field anchor missing')
    s = s.replace(old, new, 1)

old = '''        return ResourceInquiry(\n            resource_type=resource_type,\n            resource_selector=normalized_selector,\n            requested_facts=tuple(str(item).strip() for item in requested_facts),\n            execution_mode=str(proposed.get("execution_mode", "deterministic")).strip(),\n'''
new = '''        normalized_requested_facts = tuple(str(item).strip() for item in requested_facts)\n        if self.fact_vocabulary is not None:\n            normalized_requested_facts = tuple(\n                self.fact_vocabulary.normalize(\n                    item,\n                    resource_type=resource_type,\n                )\n                for item in normalized_requested_facts\n            )\n\n        return ResourceInquiry(\n            resource_type=resource_type,\n            resource_selector=normalized_selector,\n            requested_facts=normalized_requested_facts,\n            execution_mode=str(proposed.get("execution_mode", "deterministic")).strip(),\n'''
if new not in s:
    if old not in s:
        raise SystemExit('ERROR: requested fact construction anchor missing')
    s = s.replace(old, new, 1)

p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 4: WIRE VOCABULARY INTO PRODUCTION COMPOSITION =========="
python3 - <<'PY'
from pathlib import Path
p = Path('implementation/runtime_service/src/jason_runtime/composition.py')
s = p.read_text(encoding='utf-8')

anchor = 'from orchestrator.authority import JKD001OrchestrationContextEnforcer\n'
insert = (
    'from orchestrator.canonical_fact_vocabulary import (\n'
    '    DEFAULT_CANONICAL_FACT_VOCABULARY,\n'
    ')\n'
)
if insert not in s:
    if anchor not in s:
        raise SystemExit('ERROR: composition import anchor missing')
    s = s.replace(anchor, anchor + insert, 1)

old = '''            fallback=ReasonedResourceInquiryInterpreter(\n                reasoner=OllamaResourceInquiryReasoner(\n                    ollama_client,\n                    resource_types=resource_types,\n                    selector_keys=selector_keys,\n                    fact_hints=fact_hints,\n                )\n            ),\n'''
new = '''            fallback=ReasonedResourceInquiryInterpreter(\n                reasoner=OllamaResourceInquiryReasoner(\n                    ollama_client,\n                    resource_types=resource_types,\n                    selector_keys=selector_keys,\n                    fact_hints=tuple(\n                        dict.fromkeys(\n                            (\n                                *fact_hints,\n                                *DEFAULT_CANONICAL_FACT_VOCABULARY.aliases_for_resource_types(\n                                    resource_types\n                                ),\n                            )\n                        )\n                    ),\n                ),\n                fact_vocabulary=DEFAULT_CANONICAL_FACT_VOCABULARY,\n            ),\n'''
if new not in s:
    if old not in s:
        raise SystemExit('ERROR: production reasoned interpreter anchor missing')
    s = s.replace(old, new, 1)

p.write_text(s, encoding='utf-8')
print('UPDATED:', p)
PY

echo "========== SECTION 5: ADD REGRESSION TESTS =========="
cat > implementation/orchestrator/tests/test_canonical_fact_vocabulary.py <<'PY'
from orchestrator.canonical_fact_vocabulary import DEFAULT_CANONICAL_FACT_VOCABULARY


def normalize(value: str) -> str:
    return DEFAULT_CANONICAL_FACT_VOCABULARY.normalize(
        value,
        resource_type="endpoint",
    )


def test_processor_and_cpu_default_to_processor_model() -> None:
    assert normalize("processor") == "processor model"
    assert normalize("CPU") == "processor model"
    assert normalize("cpu model") == "processor model"


def test_processor_count_language_remains_distinct_from_model() -> None:
    assert normalize("processor count") == "logical processor count"
    assert normalize("logical processors") == "logical processor count"
    assert normalize("threads") == "logical processor count"


def test_memory_aliases_and_bounded_typo_normalize_to_total_memory() -> None:
    assert normalize("RAM") == "total memory"
    assert normalize("memory") == "total memory"
    assert normalize("physical memory") == "total memory"
    assert normalize("memore") == "total memory"


def test_windows_display_version_is_not_treated_as_graphics_display() -> None:
    assert normalize("Windows Display Version") == "operating system display version"
    assert normalize("display version") == "operating system display version"
    assert normalize("display") == "display"


def test_unknown_or_ambiguous_fact_is_preserved_for_bounded_fallback() -> None:
    assert normalize("battery chemistry") == "battery chemistry"
PY

cat >> implementation/orchestrator/tests/test_conversation_resource_intent.py <<'PY'


def test_reasoned_endpoint_facts_are_normalized_through_canonical_vocabulary():
    from orchestrator.canonical_fact_vocabulary import DEFAULT_CANONICAL_FACT_VOCABULARY
    from orchestrator.conversation_resource_intent import ReasonedResourceInquiryInterpreter

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
PY

echo "Tests added."

echo "========== SECTION 6: STATIC VALIDATION =========="
git diff --check
python3 -m py_compile \
  implementation/orchestrator/canonical_fact_vocabulary.py \
  implementation/orchestrator/conversation_resource_intent.py \
  implementation/runtime_service/src/jason_runtime/composition.py

echo "========== SECTION 7: FOCUSED TESTS =========="
pytest -q \
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
