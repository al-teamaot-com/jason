from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .canonical_fact_vocabulary import CanonicalFactVocabulary
from .resource_inquiry import ResourceInquiry
from .semantic_resource_request import (
    SemanticEntityReference,
    SemanticEvidenceConstraint,
    SemanticRelationship,
    SemanticResourceRequest,
)


@dataclass(frozen=True, slots=True)
class SemanticRequestBridge:
    """Translate grounded human resource meaning into the legacy planner contract.

    This bridge is intentionally provider-neutral. It lets the conversation layer use
    a richer semantic IR now while the existing governed capability planner remains in
    place. Providers, connectors, API paths, credentials, and scripts never appear in
    this contract.
    """

    fact_vocabulary: CanonicalFactVocabulary | None = None

    def build(
        self,
        *,
        human_text: str,
        resource_type: str,
        resource_selector: Mapping[str, str],
        requested_facts: tuple[str, ...],
        result_intent: str,
        completeness_requirement: str,
        permission_mode: str = "observe",
    ) -> SemanticResourceRequest:
        facts = requested_facts
        if self.fact_vocabulary is not None:
            facts = self.fact_vocabulary.canonicalize_requested_facts(
                human_text=human_text,
                requested_facts=facts,
            )

        subject: SemanticEntityReference | None = None
        relationship: SemanticRelationship | None = None
        selector = dict(resource_selector)

        user_identity = str(selector.get("user_identity", "")).strip()
        if user_identity:
            temporal = self._temporal_semantics(human_text)
            subject = SemanticEntityReference(
                entity_type="person",
                reference=user_identity,
                selector_kind="human_identity",
            )
            relationship = SemanticRelationship(
                relationship_type="logged_in_to",
                target_resource_type=resource_type,
                temporal_semantics=temporal,
            )
        elif selector:
            # Preserve the human-grounded selector as an entity reference without
            # pretending the selector is durable identity.
            key, value = next(iter(selector.items()))
            subject = SemanticEntityReference(
                entity_type=resource_type,
                reference=str(value),
                selector_kind=str(key),
            )

        constraints: dict[str, SemanticEvidenceConstraint] = {}
        if self.fact_vocabulary is not None:
            for fact in facts:
                definition = self.fact_vocabulary.resolve(fact)
                if definition is None:
                    continue
                contexts = self._semantic_contexts(definition.canonical_fact)
                constraints[fact] = SemanticEvidenceConstraint(
                    contexts=contexts,
                    expected_shape=definition.expected_shape,
                )

        return SemanticResourceRequest(
            subject=subject,
            target_resource_type=resource_type,
            requested_facts=facts,
            relationship=relationship,
            evidence_constraints=constraints or None,
            result_intent=result_intent,
            completeness_requirement=completeness_requirement,
            permission_mode=permission_mode,
        )

    @staticmethod
    def lower(request: SemanticResourceRequest, *, selector: Mapping[str, str]) -> ResourceInquiry:
        """Lower semantic meaning into the existing governed planner contract."""
        return ResourceInquiry(
            resource_type=request.target_resource_type,
            resource_selector=dict(selector),
            requested_facts=request.requested_facts,
            execution_mode="deterministic",
            permission_mode=request.permission_mode,
            result_intent=request.result_intent,
            completeness_requirement=request.completeness_requirement,
        )

    @staticmethod
    def _temporal_semantics(human_text: str) -> str:
        normalized = " ".join(human_text.casefold().split())
        words = set(normalized.replace("?", " ").replace(".", " ").split())

        if any(phrase in normalized for phrase in (
            "last logged",
            "most recent",
            "last used",
            "last on",
        )):
            return "most_recent"

        # Current-state language is semantic rather than a fixed adjacent phrase.
        # "What device is Lindsey Collins on?" contains the relationship operator
        # as separated words, while "currently", "right now", "using", and
        # "logged into" are explicit current-state forms.
        if (
            "currently" in words
            or "right now" in normalized
            or "using" in words
            or "logged into" in normalized
            or ("is" in words and "on" in words)
        ):
            return "current"

        return "unspecified"

    @staticmethod
    def _semantic_contexts(canonical_fact: str) -> tuple[str, ...]:
        """Provider-neutral evidence domains, never provider field names or paths."""
        contexts = {
            "operating system display version": ("operating_system", "windows_release"),
            "operating system build": ("operating_system",),
            "operating system": ("operating_system",),
            "processor model": ("processor", "hardware_inventory"),
            "logical processor count": ("processor", "hardware_inventory"),
            "total memory": ("memory", "hardware_inventory"),
            "bios version": ("bios", "hardware_inventory"),
            "network adapters": ("network", "hardware_inventory"),
            "logical disks": ("storage", "hardware_inventory"),
            "display adapters": ("graphics", "hardware_inventory"),
        }
        return contexts.get(canonical_fact, ())
