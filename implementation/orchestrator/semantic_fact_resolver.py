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
