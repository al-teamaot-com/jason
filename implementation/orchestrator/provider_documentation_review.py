from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .provider_capability_discovery import ProviderCapabilityDiscoveryAssessment


@dataclass(frozen=True, slots=True)
class ProviderDocumentationReviewTarget:
    provider_id: str
    documentation_source: str
    unsupported_facts: tuple[str, ...]
    resource_authority: str | None = None
    connector_id: str | None = None

    def as_context(self) -> Mapping[str, object]:
        return {
            "provider_id": self.provider_id,
            "documentation_source": self.documentation_source,
            "unsupported_facts": self.unsupported_facts,
            "resource_authority": self.resource_authority,
            "connector_id": self.connector_id,
        }


@dataclass(frozen=True, slots=True)
class ProviderDocumentationReviewPlan:
    targets: tuple[ProviderDocumentationReviewTarget, ...]
    review_only: bool = True
    governance_owner: str = "technology-steward"
    interpretation_rule: str = (
        "Documented provider fields, schemas, and operations may be proposed as candidate evidence only. "
        "No semantic mapping, derivation, capability registration, provider selection, or execution authority "
        "is created by documentation review."
    )

    def as_context(self) -> Mapping[str, object]:
        return {
            "review_only": self.review_only,
            "governance_owner": self.governance_owner,
            "interpretation_rule": self.interpretation_rule,
            "targets": tuple(item.as_context() for item in self.targets),
        }


@dataclass(frozen=True, slots=True)
class GovernedProviderDocumentationReviewPlanner:
    """Turn registered-provider discovery into bounded documentation review targets.

    This planner does not fetch documentation, call providers, inspect credentials, infer mappings,
    or modify registries. It only creates the review workload that a governed documentation reader
    may later execute under Technology Steward authority.
    """

    def plan(
        self,
        *,
        discovery: ProviderCapabilityDiscoveryAssessment,
    ) -> ProviderDocumentationReviewPlan:
        targets: list[ProviderDocumentationReviewTarget] = []
        for candidate in discovery.candidates:
            for source in candidate.vendor_change_sources:
                source_text = str(source).strip()
                if not source_text:
                    continue
                targets.append(
                    ProviderDocumentationReviewTarget(
                        provider_id=candidate.provider_id,
                        documentation_source=source_text,
                        unsupported_facts=tuple(discovery.unsupported_facts),
                        resource_authority=candidate.resource_authority,
                        connector_id=candidate.connector_id,
                    )
                )
        targets.sort(
            key=lambda item: (
                item.provider_id.casefold(),
                item.documentation_source.casefold(),
            )
        )
        return ProviderDocumentationReviewPlan(targets=tuple(targets))
