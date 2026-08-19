#!/usr/bin/env bash
set -euo pipefail

clear
cd /home/al/projects/jason

echo "========== START SEMANTIC REGISTRY REQUEST RESOLUTION INTEGRATION =========="
echo "========== SECTION 1: PRECONDITIONS =========="
echo "HEAD: $(git rev-parse --short HEAD)"

DIRTY="$(git status --porcelain | grep -v '^?? FETCH_HEAD$' || true)"
if [[ -n "$DIRTY" ]]; then
  echo "ERROR: worktree must be clean before request-resolution integration."
  printf '%s\n' "$DIRTY"
  exit 20
fi

echo "========== SECTION 2: ADD REGISTRY-BACKED FACT RESOLVER =========="
cat > implementation/orchestrator/semantic_fact_resolver.py <<'PY'
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from orchestrator.canonical_fact_vocabulary import (
    CanonicalFactDefinition,
    CanonicalFactVocabulary,
    DEFAULT_CANONICAL_FACT_VOCABULARY,
)
from orchestrator.semantic_knowledge_registry import SemanticConcept
from orchestrator.semantic_knowledge_seed import build_trusted_semantic_registry


@dataclass(frozen=True, slots=True)
class SemanticFactResolution:
    canonical_fact: str
    expected_shape: str | None
    evidence_contexts: tuple[str, ...]
    source: str
    concept_id: str | None = None


class SemanticFactResolver:
    """Resolve human fact wording through governed semantic knowledge first.

    The Semantic Knowledge Registry is authoritative for concepts it knows. The
    legacy CanonicalFactVocabulary remains a temporary compatibility fallback for
    concepts not yet migrated. This class does not invoke an LLM and does not select
    providers or capabilities.
    """

    def __init__(
        self,
        *,
        vocabulary: CanonicalFactVocabulary = DEFAULT_CANONICAL_FACT_VOCABULARY,
    ) -> None:
        self._registry = build_trusted_semantic_registry()
        self._vocabulary = vocabulary

    @staticmethod
    def _from_registry(concept: SemanticConcept) -> SemanticFactResolution:
        return SemanticFactResolution(
            canonical_fact=concept.canonical_label,
            expected_shape=concept.expected_shape,
            evidence_contexts=concept.evidence_contexts,
            source="semantic_knowledge_registry",
            concept_id=concept.concept_id,
        )

    @staticmethod
    def _from_legacy(definition: CanonicalFactDefinition) -> SemanticFactResolution:
        return SemanticFactResolution(
            canonical_fact=definition.canonical_fact,
            expected_shape=definition.expected_shape,
            evidence_contexts=(),
            source="canonical_fact_vocabulary_fallback",
            concept_id=None,
        )

    def resolve(self, value: str) -> SemanticFactResolution | None:
        concept = self._registry.resolve_term(value)
        if concept is not None:
            return self._from_registry(concept)

        definition = self._vocabulary.resolve(value)
        if definition is not None:
            return self._from_legacy(definition)
        return None

    def canonicalize(self, value: str) -> str:
        resolution = self.resolve(value)
        return resolution.canonical_fact if resolution is not None else value.strip()

    def canonicalize_requested_facts(
        self,
        *,
        human_text: str,
        requested_facts: Iterable[str],
    ) -> tuple[str, ...]:
        requested = tuple(str(item) for item in requested_facts)

        # First ask the authoritative registry whether the human text explicitly
        # contains one of the migrated concepts. Longest explicit matching term wins.
        normalized_text = self._registry.normalize_text(human_text)
        candidates: list[tuple[int, SemanticFactResolution]] = []
        for term in self._registry.active_terms():
            normalized_term = self._registry.normalize_text(term)
            if not normalized_term:
                continue
            padded = f" {normalized_text} "
            if f" {normalized_term} " in padded:
                resolution = self.resolve(term)
                if resolution is not None and resolution.source == "semantic_knowledge_registry":
                    candidates.append((len(normalized_term), resolution))

        if candidates:
            candidates.sort(key=lambda item: item[0], reverse=True)
            best_len = candidates[0][0]
            best = {item[1].canonical_fact: item[1] for item in candidates if item[0] == best_len}
            if len(best) == 1:
                resolution = next(iter(best.values()))
                requested_words = {
                    token
                    for fact in requested
                    for token in self._registry.normalize_text(fact).split()
                }
                concept_words = set(self._registry.normalize_text(resolution.canonical_fact).split())
                if requested_words and requested_words.issubset(concept_words | requested_words):
                    return (resolution.canonical_fact,)

        # Compatibility path preserves existing conservative explicit-fragment
        # handling for concepts that have not yet been migrated into the registry.
        legacy = self._vocabulary.canonicalize_requested_facts(
            human_text=human_text,
            requested_facts=requested,
        )
        return tuple(self.canonicalize(item) for item in legacy)


DEFAULT_SEMANTIC_FACT_RESOLVER = SemanticFactResolver()
PY

echo "WROTE: implementation/orchestrator/semantic_fact_resolver.py"

echo "========== SECTION 3: EXTEND REGISTRY READ API =========="
python3 - <<'PY'
from pathlib import Path
path = Path('implementation/orchestrator/semantic_knowledge_registry.py')
text = path.read_text()
needle = "    def get_concept(self, concept_id: str) -> SemanticConcept:\n        return self._concepts[concept_id]\n"
replacement = "    @staticmethod\n    def normalize_text(value: str) -> str:\n        return normalize_semantic_term(value)\n\n    def active_terms(self) -> tuple[str, ...]:\n        return tuple(\n            binding.term\n            for binding in self._terms\n            if binding.state is SemanticLifecycleState.ACTIVE\n            and self._concepts.get(binding.concept_id) is not None\n            and self._concepts[binding.concept_id].state is SemanticLifecycleState.ACTIVE\n        )\n\n    def get_concept(self, concept_id: str) -> SemanticConcept:\n        return self._concepts[concept_id]\n"
if needle not in text:
    raise SystemExit('ERROR: expected registry insertion point not found')
path.write_text(text.replace(needle, replacement, 1))
PY

echo "UPDATED: implementation/orchestrator/semantic_knowledge_registry.py"

echo "========== SECTION 4: ADD INTEGRATION TESTS =========="
cat > implementation/orchestrator/tests/test_semantic_fact_resolver.py <<'PY'
from orchestrator.semantic_fact_resolver import SemanticFactResolver


def test_registry_precedes_legacy_vocabulary_for_cpu():
    resolver = SemanticFactResolver()
    result = resolver.resolve("CPU")
    assert result is not None
    assert result.canonical_fact == "processor model"
    assert result.concept_id == "processor.model"
    assert result.source == "semantic_knowledge_registry"
    assert result.evidence_contexts == ("processor", "hardware_inventory")


def test_registry_precedes_legacy_vocabulary_for_ram():
    resolver = SemanticFactResolver()
    result = resolver.resolve("RAM")
    assert result is not None
    assert result.canonical_fact == "total memory"
    assert result.concept_id == "memory.total"
    assert result.source == "semantic_knowledge_registry"


def test_registry_supplies_windows_display_version_context():
    resolver = SemanticFactResolver()
    result = resolver.resolve("Windows Display Version")
    assert result is not None
    assert result.canonical_fact == "operating system display version"
    assert result.evidence_contexts == ("operating_system", "windows_release")


def test_unmigrated_concept_uses_legacy_compatibility_fallback():
    resolver = SemanticFactResolver()
    result = resolver.resolve("BIOS")
    assert result is not None
    assert result.canonical_fact == "bios version"
    assert result.source == "canonical_fact_vocabulary_fallback"


def test_unknown_term_remains_unresolved():
    resolver = SemanticFactResolver()
    assert resolver.resolve("absolutely unknown hardware frobnicator") is None


def test_registry_canonicalizes_reasoner_cpu_fragment():
    resolver = SemanticFactResolver()
    result = resolver.canonicalize_requested_facts(
        human_text="What CPU is in AOT-50282?",
        requested_facts=("cpu",),
    )
    assert result == ("processor model",)


def test_registry_canonicalizes_windows_display_version_fragment():
    resolver = SemanticFactResolver()
    result = resolver.canonicalize_requested_facts(
        human_text="What is the Windows Display Version for AOT-50282?",
        requested_facts=("display", "version"),
    )
    assert result == ("operating system display version",)
PY

echo "WROTE: implementation/orchestrator/tests/test_semantic_fact_resolver.py"

echo "========== SECTION 5: STATIC VALIDATION ==========" 
git diff --check

echo "========== SECTION 6: FOCUSED TESTS ==========" 
.venv/bin/python -m pytest -q \
  implementation/orchestrator/tests/test_semantic_fact_resolver.py \
  implementation/orchestrator/tests/test_semantic_knowledge_registry.py \
  implementation/orchestrator/tests/test_semantic_knowledge_seed.py \
  implementation/orchestrator/tests/test_canonical_fact_vocabulary.py \
  implementation/orchestrator/tests/test_semantic_resource_request.py

echo "========== SECTION 7: CHANGE STATE ==========" 
git status --short

echo "========== RESULT ==========" 
echo "Semantic request fact resolution now has a registry-first resolver with legacy fallback."
echo "No existing runtime call sites are replaced in this stage."
echo "NO DEPLOYMENT PERFORMED."
echo "NO COMMIT OR PUSH OF WORKTREE CHANGES PERFORMED."
echo "========== END SEMANTIC REGISTRY REQUEST RESOLUTION INTEGRATION =========="
