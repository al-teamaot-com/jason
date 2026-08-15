from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .contracts import OrchestrationResult
from .resource_evidence import (
    GovernedResourceEvidenceInterpreter,
    VerifiedResourceFact,
    _evidence_matches_contexts,
    _value_matches_expected_shape,
)
from .semantic_fact_resolver import SemanticFactResolver


@dataclass(frozen=True, slots=True)
class GovernedSemanticEvidenceBoundary:
    """Apply canonical semantic constraints to verified provider evidence.

    The inner evidence interpreter may use bounded language reasoning to identify a
    JSON pointer, but that pointer is not sufficient authority to bind an arbitrary
    provider field to a known semantic concept. Known concepts must also satisfy their
    provider-neutral evidence contexts and expected value shape before the value may
    be rendered to a human.

    This prevents unrelated provider metadata such as a generic ``status`` field or
    discovery marker from being presented as a requested security fact simply because
    a language reasoner selected that location.
    """

    inner: GovernedResourceEvidenceInterpreter
    fact_resolver: SemanticFactResolver

    def interpret(
        self,
        *,
        result: OrchestrationResult,
        requested_facts: tuple[str, ...],
        evidence_contexts: Mapping[str, tuple[str, ...]] | None = None,
    ) -> tuple[VerifiedResourceFact, ...]:
        facts = self.inner.interpret(
            result=result,
            requested_facts=requested_facts,
            evidence_contexts=evidence_contexts,
        )

        supplied_contexts = evidence_contexts or {}

        for fact in facts:
            resolution = self.fact_resolver.resolve(fact.requested_fact)
            if resolution is None:
                continue

            contexts = tuple(
                supplied_contexts.get(
                    fact.requested_fact,
                    resolution.evidence_contexts,
                )
            )

            pointers = fact.json_pointers or (fact.json_pointer,)
            if contexts and any(
                not _evidence_matches_contexts(
                    pointer=pointer,
                    contexts=contexts,
                )
                for pointer in pointers
            ):
                raise LookupError(
                    "governed provider evidence did not satisfy the semantic "
                    f"context required for {fact.requested_fact}"
                )

            if (
                resolution.expected_shape
                and not _value_matches_expected_shape(
                    fact.value,
                    resolution.expected_shape,
                )
            ):
                raise LookupError(
                    "governed provider evidence did not satisfy the semantic "
                    f"shape required for {fact.requested_fact}"
                )

        return facts
