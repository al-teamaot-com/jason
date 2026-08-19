from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from orchestrator.canonical_fact_vocabulary import (
    CanonicalFactDefinition,
    CanonicalFactVocabulary,
    DEFAULT_CANONICAL_FACT_VOCABULARY,
)
from orchestrator.semantic_knowledge_registry import SemanticConcept, SemanticKnowledgeRegistry
from orchestrator.semantic_knowledge_seed import build_trusted_semantic_registry
from orchestrator.semantic_security_extension import extend_trusted_security_semantics


@dataclass(frozen=True, slots=True)
class SemanticFactResolution:
    canonical_fact: str
    expected_shape: str | None
    evidence_contexts: tuple[str, ...]
    source: str
    concept_id: str | None = None

    @property
    def canonical_label(self) -> str:
        return self.canonical_fact


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
        registry: SemanticKnowledgeRegistry | None = None,
        legacy_vocabulary: CanonicalFactVocabulary | None = DEFAULT_CANONICAL_FACT_VOCABULARY,
        vocabulary: CanonicalFactVocabulary | None = None,
    ) -> None:
        # ``vocabulary`` is retained as a temporary compatibility alias for older
        # composition/tests. New construction should use ``legacy_vocabulary``.
        if vocabulary is not None:
            if legacy_vocabulary is not DEFAULT_CANONICAL_FACT_VOCABULARY:
                raise ValueError("specify either legacy_vocabulary or vocabulary, not both")
            legacy_vocabulary = vocabulary
        if registry is None:
            registry = extend_trusted_security_semantics(
                build_trusted_semantic_registry()
            )
        self._registry = registry
        self._vocabulary = legacy_vocabulary

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

    def _resolve_canonical_label(self, value: str) -> SemanticConcept | None:
        """Resolve an ACTIVE concept by its canonical label without alias tables.

        Canonical labels are Jason's provider-neutral semantic identifiers once a
        human request has been normalized. Downstream consumers must therefore be
        able to resolve those labels even when the seed registry does not repeat the
        canonical label as an explicit term binding. Only ACTIVE terms can expose an
        ACTIVE concept here, preserving the registry lifecycle gate. Conflicting
        canonical labels fail closed rather than selecting an arbitrary concept.
        """

        normalized = self._registry.normalize_text(value)
        if not normalized:
            return None

        matches: dict[str, SemanticConcept] = {}
        for term in self._registry.active_terms():
            concept = self._registry.resolve_term(term)
            if concept is None:
                continue
            if self._registry.normalize_text(concept.canonical_label) != normalized:
                continue
            matches[concept.concept_id] = concept

        if len(matches) > 1:
            raise LookupError(f"active semantic canonical label is ambiguous: {value!r}")
        return next(iter(matches.values())) if matches else None

    def resolve(self, value: str) -> SemanticFactResolution | None:
        concept = self._registry.resolve_term(value)
        if concept is None:
            concept = self._resolve_canonical_label(value)
        if concept is not None:
            return self._from_registry(concept)

        if self._vocabulary is not None:
            definition = self._vocabulary.resolve(value)
            if definition is not None:
                return self._from_legacy(definition)
        return None

    def match_explicit_facts(self, human_text: str) -> tuple[SemanticFactResolution, ...]:
        """Return the most-specific active registry concepts explicitly named in text.

        This is deterministic semantic recognition only. It grants no capability,
        provider, credential, or execution authority. Longest matching active terms
        win so a phrase such as ``bitlocker unlock code`` is not diluted into a more
        generic overlapping concept.
        """

        normalized_text = self._registry.normalize_text(human_text)
        if not normalized_text:
            return ()

        padded = f" {normalized_text} "
        candidates: list[tuple[int, SemanticFactResolution]] = []
        for term in self._registry.active_terms():
            normalized_term = self._registry.normalize_text(term)
            if not normalized_term or f" {normalized_term} " not in padded:
                continue
            resolution = self.resolve(term)
            if resolution is None or resolution.source != "semantic_knowledge_registry":
                continue
            candidates.append((len(normalized_term), resolution))

        if not candidates:
            return ()

        longest = max(length for length, _ in candidates)
        result: list[SemanticFactResolution] = []
        seen: set[str] = set()
        for length, resolution in candidates:
            if length != longest or resolution.canonical_fact in seen:
                continue
            seen.add(resolution.canonical_fact)
            result.append(resolution)
        return tuple(result)

    def canonicalize(self, value: str) -> str:
        resolution = self.resolve(value)
        return resolution.canonical_fact if resolution is not None else value.strip()

    def resolve_requested_facts(
        self,
        *,
        human_text: str,
        requested_facts: Iterable[str],
    ) -> tuple[SemanticFactResolution, ...]:
        canonical = self.canonicalize_requested_facts(
            human_text=human_text,
            requested_facts=requested_facts,
        )
        resolved: list[SemanticFactResolution] = []
        for fact in canonical:
            resolution = self.resolve(fact)
            if resolution is None:
                resolution = SemanticFactResolution(
                    canonical_fact=str(fact).strip(),
                    expected_shape=None,
                    evidence_contexts=(),
                    source="unresolved_passthrough",
                    concept_id=None,
                )
            resolved.append(resolution)
        return tuple(resolved)

    def canonicalize_requested_facts(
        self,
        *,
        human_text: str,
        requested_facts: Iterable[str],
    ) -> tuple[str, ...]:
        requested = tuple(str(item) for item in requested_facts)

        matches = self.match_explicit_facts(human_text)
        if len(matches) == 1:
            resolution = matches[0]
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
        if self._vocabulary is None:
            return tuple(self.canonicalize(item) for item in requested)

        legacy = self._vocabulary.canonicalize_requested_facts(
            human_text=human_text,
            requested_facts=requested,
        )
        return tuple(self.canonicalize(item) for item in legacy)


DEFAULT_SEMANTIC_FACT_RESOLVER = SemanticFactResolver()
