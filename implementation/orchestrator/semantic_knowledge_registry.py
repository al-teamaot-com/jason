from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Iterable


class SemanticLifecycleState(str, Enum):
    CANDIDATE = "candidate"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


_ALLOWED_TRANSITIONS = {
    SemanticLifecycleState.CANDIDATE: {SemanticLifecycleState.REVIEWED},
    SemanticLifecycleState.REVIEWED: {
        SemanticLifecycleState.APPROVED,
        SemanticLifecycleState.CANDIDATE,
    },
    SemanticLifecycleState.APPROVED: {
        SemanticLifecycleState.ACTIVE,
        SemanticLifecycleState.REVIEWED,
    },
    SemanticLifecycleState.ACTIVE: {SemanticLifecycleState.DEPRECATED},
    SemanticLifecycleState.DEPRECATED: set(),
}


def normalize_semantic_term(value: str) -> str:
    return " ".join(
        "".join(character if character.isalnum() else " " for character in value.casefold()).split()
    )


@dataclass(frozen=True, slots=True)
class SemanticProvenance:
    source: str
    evidence: str
    observed_at: str | None = None

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("semantic provenance source is required")
        if not self.evidence.strip():
            raise ValueError("semantic provenance evidence is required")


@dataclass(frozen=True, slots=True)
class SemanticConcept:
    concept_id: str
    canonical_label: str
    kind: str
    expected_shape: str | None = None
    canonical_unit: str | None = None
    evidence_contexts: tuple[str, ...] = ()
    state: SemanticLifecycleState = SemanticLifecycleState.CANDIDATE
    provenance: SemanticProvenance | None = None
    review_interval_days: int | None = None
    retirement_criteria: str | None = None

    def __post_init__(self) -> None:
        if not self.concept_id.strip():
            raise ValueError("semantic concept_id is required")
        if not self.canonical_label.strip():
            raise ValueError("semantic canonical_label is required")
        if self.kind not in {"fact", "entity", "relationship", "temporal", "unit"}:
            raise ValueError("semantic concept kind is invalid")
        if any(not item.strip() for item in self.evidence_contexts):
            raise ValueError("semantic evidence contexts must be non-empty")
        if self.review_interval_days is not None and self.review_interval_days <= 0:
            raise ValueError("semantic review interval must be positive")


@dataclass(frozen=True, slots=True)
class SemanticTermBinding:
    term: str
    concept_id: str
    scope: str = "global"
    state: SemanticLifecycleState = SemanticLifecycleState.CANDIDATE
    provenance: SemanticProvenance | None = None

    def __post_init__(self) -> None:
        if not normalize_semantic_term(self.term):
            raise ValueError("semantic term is required")
        if not self.concept_id.strip():
            raise ValueError("semantic term concept_id is required")
        if not self.scope.strip():
            raise ValueError("semantic term scope is required")


@dataclass(frozen=True, slots=True)
class SemanticProviderFieldBinding:
    provider: str
    resource_type: str
    provider_field: str
    concept_id: str
    state: SemanticLifecycleState = SemanticLifecycleState.CANDIDATE
    provenance: SemanticProvenance | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("provider", self.provider),
            ("resource_type", self.resource_type),
            ("provider_field", self.provider_field),
            ("concept_id", self.concept_id),
        ):
            if not value.strip():
                raise ValueError(f"semantic provider binding {name} is required")


@dataclass(frozen=True, slots=True)
class SemanticRelationshipDefinition:
    relationship_id: str
    subject_type: str
    target_type: str
    temporal_semantics: tuple[str, ...] = ("unspecified",)
    state: SemanticLifecycleState = SemanticLifecycleState.CANDIDATE
    provenance: SemanticProvenance | None = None

    def __post_init__(self) -> None:
        if not self.relationship_id.strip():
            raise ValueError("semantic relationship_id is required")
        if not self.subject_type.strip() or not self.target_type.strip():
            raise ValueError("semantic relationship subject/target types are required")
        allowed = {"unspecified", "current", "most_recent", "historical"}
        if not self.temporal_semantics or not set(self.temporal_semantics).issubset(allowed):
            raise ValueError("semantic relationship temporal semantics are invalid")


class SemanticKnowledgeRegistry:
    """Governed, versioned, provider-neutral semantic knowledge.

    Unknown or non-active knowledge never becomes operational truth. Candidate
    generation may be AI-assisted outside this class, but activation is an explicit
    lifecycle transition. Runtime resolution consumes ACTIVE knowledge only.
    """

    def __init__(self) -> None:
        self._concepts: dict[str, SemanticConcept] = {}
        self._terms: list[SemanticTermBinding] = []
        self._provider_fields: list[SemanticProviderFieldBinding] = []
        self._relationships: dict[str, SemanticRelationshipDefinition] = {}
        self._version = 0

    @property
    def version(self) -> int:
        return self._version

    def _bump(self) -> None:
        self._version += 1

    @staticmethod
    def _transition_state(current: SemanticLifecycleState, target: SemanticLifecycleState) -> None:
        if target not in _ALLOWED_TRANSITIONS[current]:
            raise ValueError(f"invalid semantic lifecycle transition: {current.value} -> {target.value}")

    def add_concept(self, concept: SemanticConcept) -> None:
        if concept.concept_id in self._concepts:
            raise ValueError(f"semantic concept already exists: {concept.concept_id}")
        self._concepts[concept.concept_id] = concept
        self._bump()

    def transition_concept(self, concept_id: str, target: SemanticLifecycleState) -> SemanticConcept:
        current = self._concepts[concept_id]
        self._transition_state(current.state, target)
        updated = replace(current, state=target)
        self._concepts[concept_id] = updated
        self._bump()
        return updated

    def add_term(self, binding: SemanticTermBinding) -> None:
        if binding.concept_id not in self._concepts:
            raise KeyError(f"unknown semantic concept: {binding.concept_id}")
        normalized = normalize_semantic_term(binding.term)
        for existing in self._terms:
            if normalize_semantic_term(existing.term) == normalized and existing.scope == binding.scope:
                if existing.concept_id != binding.concept_id:
                    raise ValueError(
                        f"semantic term is ambiguous in scope {binding.scope}: {binding.term!r}"
                    )
                raise ValueError(f"semantic term already exists: {binding.term!r}")
        self._terms.append(binding)
        self._bump()

    def transition_term(
        self,
        *,
        term: str,
        scope: str,
        target: SemanticLifecycleState,
    ) -> SemanticTermBinding:
        normalized = normalize_semantic_term(term)
        for index, current in enumerate(self._terms):
            if normalize_semantic_term(current.term) == normalized and current.scope == scope:
                self._transition_state(current.state, target)
                updated = replace(current, state=target)
                self._terms[index] = updated
                self._bump()
                return updated
        raise KeyError(f"unknown semantic term: {term!r} in scope {scope!r}")

    def add_provider_field(self, binding: SemanticProviderFieldBinding) -> None:
        if binding.concept_id not in self._concepts:
            raise KeyError(f"unknown semantic concept: {binding.concept_id}")
        normalized_field = normalize_semantic_term(binding.provider_field)
        for existing in self._provider_fields:
            if (
                existing.provider == binding.provider
                and existing.resource_type == binding.resource_type
                and normalize_semantic_term(existing.provider_field) == normalized_field
            ):
                if existing.concept_id != binding.concept_id:
                    raise ValueError("semantic provider field mapping is ambiguous")
                # Provider schemas commonly expose case/style aliases such as
                # displayVersion and DisplayVersion. After normalization these are
                # the same governed binding, so repeated registration is idempotent
                # rather than a second semantic fact. Conflicting concept mappings
                # still fail closed above.
                return
        self._provider_fields.append(binding)
        self._bump()

    def transition_provider_field(
        self,
        *,
        provider: str,
        resource_type: str,
        provider_field: str,
        target: SemanticLifecycleState,
    ) -> SemanticProviderFieldBinding:
        normalized_field = normalize_semantic_term(provider_field)
        for index, current in enumerate(self._provider_fields):
            if (
                current.provider == provider
                and current.resource_type == resource_type
                and normalize_semantic_term(current.provider_field) == normalized_field
            ):
                self._transition_state(current.state, target)
                updated = replace(current, state=target)
                self._provider_fields[index] = updated
                self._bump()
                return updated
        raise KeyError("unknown semantic provider field mapping")

    def add_relationship(self, relationship: SemanticRelationshipDefinition) -> None:
        if relationship.relationship_id in self._relationships:
            raise ValueError(f"semantic relationship already exists: {relationship.relationship_id}")
        self._relationships[relationship.relationship_id] = relationship
        self._bump()

    def transition_relationship(
        self,
        relationship_id: str,
        target: SemanticLifecycleState,
    ) -> SemanticRelationshipDefinition:
        current = self._relationships[relationship_id]
        self._transition_state(current.state, target)
        updated = replace(current, state=target)
        self._relationships[relationship_id] = updated
        self._bump()
        return updated

    def resolve_term(self, term: str, *, scopes: Iterable[str] = ("global",)) -> SemanticConcept | None:
        normalized = normalize_semantic_term(term)
        allowed_scopes = tuple(scopes)
        matches = []
        for binding in self._terms:
            if binding.state is not SemanticLifecycleState.ACTIVE:
                continue
            if binding.scope not in allowed_scopes:
                continue
            if normalize_semantic_term(binding.term) != normalized:
                continue
            concept = self._concepts.get(binding.concept_id)
            if concept is not None and concept.state is SemanticLifecycleState.ACTIVE:
                matches.append(concept)
        unique = {item.concept_id: item for item in matches}
        if len(unique) > 1:
            raise LookupError(f"active semantic term is ambiguous: {term!r}")
        return next(iter(unique.values())) if unique else None

    def resolve_provider_field(
        self,
        *,
        provider: str,
        resource_type: str,
        provider_field: str,
    ) -> SemanticConcept | None:
        normalized_field = normalize_semantic_term(provider_field)
        matches = []
        for binding in self._provider_fields:
            if binding.state is not SemanticLifecycleState.ACTIVE:
                continue
            if binding.provider != provider or binding.resource_type != resource_type:
                continue
            if normalize_semantic_term(binding.provider_field) != normalized_field:
                continue
            concept = self._concepts.get(binding.concept_id)
            if concept is not None and concept.state is SemanticLifecycleState.ACTIVE:
                matches.append(concept)
        unique = {item.concept_id: item for item in matches}
        if len(unique) > 1:
            raise LookupError("active semantic provider field mapping is ambiguous")
        return next(iter(unique.values())) if unique else None

    def get_concept(self, concept_id: str) -> SemanticConcept:
        return self._concepts[concept_id]

    def active_relationship(self, relationship_id: str) -> SemanticRelationshipDefinition | None:
        relationship = self._relationships.get(relationship_id)
        if relationship is None or relationship.state is not SemanticLifecycleState.ACTIVE:
            return None
        return relationship


def promote_concept_to_active(registry: SemanticKnowledgeRegistry, concept_id: str) -> None:
    for state in (
        SemanticLifecycleState.REVIEWED,
        SemanticLifecycleState.APPROVED,
        SemanticLifecycleState.ACTIVE,
    ):
        registry.transition_concept(concept_id, state)


def promote_term_to_active(registry: SemanticKnowledgeRegistry, *, term: str, scope: str = "global") -> None:
    for state in (
        SemanticLifecycleState.REVIEWED,
        SemanticLifecycleState.APPROVED,
        SemanticLifecycleState.ACTIVE,
    ):
        registry.transition_term(term=term, scope=scope, target=state)
