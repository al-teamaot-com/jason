from __future__ import annotations

from datetime import datetime
from typing import Any

from .resolution_ingestion import ConfirmedResolutionIngestion
from .resolution_memory import (
    ResolutionCase,
    ResolutionMemoryMatcher,
    ResolutionSearchResult,
    ResolutionSignature,
)
from .resolution_sqlite import SQLiteResolutionMemoryStore


class ResolutionMemoryService:
    """Provider-neutral facade for durable operational resolution memory.

    This service stores and retrieves evidence. It deliberately exposes no method
    that executes a provider action or grants approval/authority.
    """

    def __init__(
        self,
        *,
        store: SQLiteResolutionMemoryStore,
        matcher: ResolutionMemoryMatcher | None = None,
    ) -> None:
        self.store = store
        self.matcher = matcher or ResolutionMemoryMatcher()

    def initialize(self) -> None:
        self.store.initialize()

    def record_case(self, case: ResolutionCase) -> None:
        self.store.add_case(case)

    def ingest_confirmed_resolution(self, candidate: ConfirmedResolutionIngestion) -> ResolutionCase:
        case = candidate.to_case()
        self.store.add_case(case)
        return case

    def search_similar(
        self,
        *,
        signature: ResolutionSignature,
        organization_id: str,
        client_id: str,
        now: datetime | None = None,
        limit: int = 10,
    ) -> ResolutionSearchResult:
        cases = self.store.list_cases(
            organization_id=organization_id,
            client_id=client_id,
        )
        return self.matcher.search(
            signature=signature,
            organization_id=organization_id,
            client_id=client_id,
            cases=cases,
            now=now,
            limit=limit,
        )

    def summary(
        self,
        *,
        organization_id: str,
        client_id: str,
    ) -> dict[str, Any]:
        return {
            "organization_id": organization_id,
            "client_id": client_id,
            "case_count": self.store.count_cases(
                organization_id=organization_id,
                client_id=client_id,
            ),
            "grants_authority": False,
        }

    def summary_global(
        self,
        *,
        organization_id: str,
        client_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "organization_id": organization_id,
            "client_id": client_id,
            "case_count": self.store.count_cases_global(
                organization_id=organization_id,
                client_id=client_id,
            ),
            "scope": "client" if client_id else "organization_aggregate",
            "raw_cases_exposed": False,
            "grants_authority": False,
        }

    @staticmethod
    def project_search_result(
        result: ResolutionSearchResult,
    ) -> dict[str, Any]:
        """Return a JSON-safe bounded evidence projection for reasoning layers."""

        matches = []
        for item in result.matches:
            matches.append(
                {
                    "case_id": item.case_id,
                    "score": item.score,
                    "similarity": item.similarity,
                    "recency_factor": item.recency_factor,
                    "outcome_factor": item.outcome_factor,
                    "reasons": list(item.reasons),
                    "root_cause": item.root_cause,
                    "final_resolution": item.final_resolution,
                    "outcome": item.outcome.value,
                    "technician_confirmed": item.technician_confirmed,
                    "evidence_only": True,
                    "grants_authority": False,
                }
            )

        steps = []
        for item in result.step_evidence:
            steps.append(
                {
                    "action_key": item.action_key,
                    "action_summary": item.action_summary,
                    "kind": item.kind.value,
                    "attempts": item.attempts,
                    "successes": item.successes,
                    "failures": item.failures,
                    "confidence": item.confidence,
                    "read_only": item.read_only,
                    "approval_required": item.approval_required,
                    "disruptive": item.disruptive,
                    "disposition": item.disposition,
                    "supporting_case_ids": list(item.supporting_case_ids),
                    "grants_authority": False,
                }
            )

        return {
            "matches": matches,
            "step_evidence": steps,
            "grants_authority": False,
            "execution_authority_source": "current_jason_governance_only",
        }
