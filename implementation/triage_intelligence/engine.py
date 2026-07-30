"""Orchestration scaffold for read-only ticket triage intelligence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from .contracts import (
    EvidenceItem,
    FindingRanker,
    IntelligenceProvider,
    SymptomNormalizer,
    TicketContext,
    TriageAssessment,
)


class ScopeViolationError(RuntimeError):
    """Raised when evidence does not belong to the permitted organization/client scope."""


class TriageIntelligenceEngine:
    """Collect, validate, and rank evidence without mutating external systems."""

    def __init__(
        self,
        *,
        normalizer: SymptomNormalizer,
        providers: Iterable[IntelligenceProvider],
        ranker: FindingRanker,
    ) -> None:
        self._normalizer = normalizer
        self._providers = tuple(providers)
        self._ranker = ranker

    def assess(self, ticket: TicketContext) -> TriageAssessment:
        symptoms = self._normalizer.normalize(ticket)
        evidence: list[EvidenceItem] = []
        provider_failures: list[str] = []

        for provider in self._providers:
            try:
                provider_items = provider.search(ticket=ticket, symptoms=symptoms)
                for item in provider_items:
                    self._validate_scope(ticket=ticket, evidence=item)
                    if item.is_fresh():
                        evidence.append(item)
            except ScopeViolationError:
                raise
            except Exception as exc:  # Provider failures are reported, not hidden.
                provider_failures.append(f"{provider.provider_name}: {type(exc).__name__}")

        findings = tuple(
            self._ranker.rank(ticket=ticket, symptoms=symptoms, evidence=tuple(evidence))
        )

        missing: list[str] = list(provider_failures)
        if not evidence:
            missing.append("No current, scoped evidence was returned.")
        if not findings:
            missing.append("No supported triage finding could be produced.")

        return TriageAssessment(
            ticket_id=ticket.ticket_id,
            generated_at=datetime.now(timezone.utc),
            findings=findings,
            evidence=tuple(evidence),
            insufficient_evidence=tuple(missing),
            requires_human_review=True,
        )

    @staticmethod
    def _validate_scope(*, ticket: TicketContext, evidence: EvidenceItem) -> None:
        if evidence.organization_id not in (None, ticket.organization_id):
            raise ScopeViolationError(
                f"Evidence {evidence.evidence_id} belongs to another organization."
            )
        if evidence.client_id not in (None, ticket.client_id):
            raise ScopeViolationError(
                f"Evidence {evidence.evidence_id} belongs to another client."
            )
