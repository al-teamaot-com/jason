from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class SemanticEntityReference:
    """Human-grounded reference to an entity before provider resolution.

    This is deliberately provider-neutral. A person can later resolve through
    Microsoft, Datto, Autotask, IT Glue, or another governed resource without the
    human-language layer selecting that provider.
    """

    entity_type: str
    reference: str
    selector_kind: str = "natural_reference"

    def __post_init__(self) -> None:
        if not self.entity_type.strip():
            raise ValueError("semantic entity_type is required")
        if not self.reference.strip():
            raise ValueError("semantic entity reference is required")
        if not self.selector_kind.strip():
            raise ValueError("semantic selector_kind is required")


@dataclass(frozen=True, slots=True)
class SemanticRelationship:
    """Provider-neutral relationship requested by the human."""

    relationship_type: str
    target_resource_type: str
    temporal_semantics: str = "unspecified"

    def __post_init__(self) -> None:
        if not self.relationship_type.strip():
            raise ValueError("semantic relationship_type is required")
        if not self.target_resource_type.strip():
            raise ValueError("semantic target_resource_type is required")
        if self.temporal_semantics not in {
            "unspecified",
            "current",
            "most_recent",
            "historical",
        }:
            raise ValueError("semantic temporal_semantics is invalid")


@dataclass(frozen=True, slots=True)
class SemanticEvidenceConstraint:
    """Meaning-level evidence requirement, never a provider path."""

    contexts: tuple[str, ...] = ()
    expected_shape: str | None = None

    def __post_init__(self) -> None:
        if any(not item.strip() for item in self.contexts):
            raise ValueError("semantic evidence contexts must be non-empty")
        if self.expected_shape is not None and not self.expected_shape.strip():
            raise ValueError("semantic expected_shape must be non-empty when supplied")


@dataclass(frozen=True, slots=True)
class SemanticResourceRequest:
    """Canonical intermediate representation between human language and orchestration.

    The request states WHAT the human means: subject/entity, relationship, target
    resource, requested facts, outcome, temporal meaning, and semantic evidence
    constraints. It contains no provider, connector, API path, credential, or script.
    Provider/capability selection remains the Central Orchestrator's responsibility.
    """

    subject: SemanticEntityReference | None
    target_resource_type: str
    requested_facts: tuple[str, ...]
    relationship: SemanticRelationship | None = None
    evidence_constraints: Mapping[str, SemanticEvidenceConstraint] | None = None
    result_intent: str = "summary"
    completeness_requirement: str = "sufficient"
    permission_mode: str = "observe"

    def __post_init__(self) -> None:
        if not self.target_resource_type.strip():
            raise ValueError("semantic target_resource_type is required")
        if not self.requested_facts:
            raise ValueError("semantic requested_facts are required")
        if any(not fact.strip() for fact in self.requested_facts):
            raise ValueError("semantic requested facts must be non-empty")
        if self.permission_mode != "observe":
            raise PermissionError("semantic resource requests are read-only")
        if self.result_intent not in {
            "summary",
            "enumerate",
            "count",
            "search",
            "inspect",
        }:
            raise ValueError("semantic result_intent is invalid")
        if self.completeness_requirement not in {"sufficient", "complete"}:
            raise ValueError("semantic completeness_requirement is invalid")
        if self.relationship is not None:
            if self.subject is None:
                raise ValueError("semantic relationship requires a subject")
            if self.relationship.target_resource_type != self.target_resource_type:
                raise ValueError("semantic relationship target does not match request target")
        if self.evidence_constraints is not None:
            unknown = set(self.evidence_constraints).difference(self.requested_facts)
            if unknown:
                raise ValueError(
                    "semantic evidence constraints reference unrequested facts: "
                    + ", ".join(sorted(unknown))
                )
