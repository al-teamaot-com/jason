from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

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
class ProviderDocumentationReviewFinding:
    provider_id: str
    documentation_source: str
    evidence_reference: str
    finding_type: str
    summary: str
    evidence: Mapping[str, object]

    def as_context(self) -> Mapping[str, object]:
        return {
            "provider_id": self.provider_id,
            "documentation_source": self.documentation_source,
            "evidence_reference": self.evidence_reference,
            "finding_type": self.finding_type,
            "summary": self.summary,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class ProviderDocumentationReviewReport:
    review_only: bool
    governance_owner: str
    deterministic_source_inventory: tuple[Mapping[str, object], ...]
    findings: tuple[ProviderDocumentationReviewFinding, ...]
    interpretation_rule: str

    def as_context(self) -> Mapping[str, object]:
        return {
            "review_only": self.review_only,
            "governance_owner": self.governance_owner,
            "deterministic_source_inventory": self.deterministic_source_inventory,
            "findings": tuple(item.as_context() for item in self.findings),
            "interpretation_rule": self.interpretation_rule,
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


@dataclass(frozen=True, slots=True)
class GovernedTechnologyStewardReviewRunner:
    """Read-only Technology Steward review runner.

    The runner consumes a bounded inventory of review targets and emits an advisory report.
    It does not mutate providers, credentials, registries, or client systems.
    """

    governance_owner: str = "technology-steward"

    def run(
        self,
        *,
        review_plan: ProviderDocumentationReviewPlan,
    ) -> ProviderDocumentationReviewReport:
        inventory = tuple(
            {
                "provider_id": target.provider_id,
                "documentation_source": target.documentation_source,
                "evidence_reference": self._evidence_reference(target),
            }
            for target in review_plan.targets
        )
        findings = tuple(
            ProviderDocumentationReviewFinding(
                provider_id=target.provider_id,
                documentation_source=target.documentation_source,
                evidence_reference=self._evidence_reference(target),
                finding_type="candidate_evidence",
                summary=(
                    "Documentation review identified a candidate source for advisory analysis only."
                ),
                evidence={
                    "unsupported_facts": target.unsupported_facts,
                    "resource_authority": target.resource_authority,
                    "connector_id": target.connector_id,
                },
            )
            for target in review_plan.targets
        )
        return ProviderDocumentationReviewReport(
            review_only=True,
            governance_owner=self.governance_owner,
            deterministic_source_inventory=inventory,
            findings=findings,
            interpretation_rule=review_plan.interpretation_rule,
        )

    @staticmethod
    def _evidence_reference(target: ProviderDocumentationReviewTarget) -> str:
        return f"{target.provider_id}::{target.documentation_source}"
