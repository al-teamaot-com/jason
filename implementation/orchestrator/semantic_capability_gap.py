from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class SemanticCapabilityGapAssessment:
    unsupported_facts: tuple[str, ...]
    inspected_context_views: tuple[str, ...]
    gap_type: str = "capability_registry_gap"
    governance_owner: str = "technology-steward"
    recommended_next_action: str = (
        "Review registered execution providers and their authoritative documentation for an existing "
        "read-only capability that can satisfy the unsupported facts. If support exists, expand the "
        "provider-neutral capability/evidence metadata through normal governance. If support does not "
        "exist, record the gap without inventing a provider mapping or one-off workflow."
    )

    def as_context(self) -> Mapping[str, Any]:
        return {
            "gap_type": self.gap_type,
            "unsupported_facts": self.unsupported_facts,
            "inspected_context_views": self.inspected_context_views,
            "governance_owner": self.governance_owner,
            "recommended_next_action": self.recommended_next_action,
        }


@dataclass(frozen=True, slots=True)
class GovernedSemanticCapabilityGapAssessor:
    """Translate a conclusive fulfillment failure into a governed expansion work item."""

    inspected_context_views: tuple[str, ...] = (
        "capability_registry",
        "evidence_catalog",
        "derivation_registry",
    )

    def assess(self, *, feasibility_result: Any) -> SemanticCapabilityGapAssessment | None:
        if not bool(getattr(feasibility_result, "conclusive", False)):
            return None
        if bool(getattr(feasibility_result, "feasible", False)):
            return None
        unsupported = tuple(
            str(item).strip()
            for item in getattr(feasibility_result, "unsupported_facts", ())
            if str(item).strip()
        )
        if not unsupported:
            return None
        return SemanticCapabilityGapAssessment(
            unsupported_facts=unsupported,
            inspected_context_views=self.inspected_context_views,
        )
