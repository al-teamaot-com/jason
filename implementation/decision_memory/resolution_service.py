from __future__ import annotations

from datetime import datetime
from typing import Any

from .pattern_memory import AOTPatternMemoryBuilder
from .pattern_sqlite import SQLiteAOTPatternStore
from .resolution_ingestion import ConfirmedResolutionIngestion
from .resolution_memory import (
    ResolutionCase,
    ResolutionMemoryMatcher,
    ResolutionSearchResult,
    ResolutionSignature,
)
from .resolution_sqlite import SQLiteResolutionMemoryStore


class ResolutionMemoryService:
    """Provider-neutral facade for client resolution memory + sanitized AOT patterns."""

    def __init__(
        self,
        *,
        store: SQLiteResolutionMemoryStore,
        matcher: ResolutionMemoryMatcher | None = None,
        pattern_store: SQLiteAOTPatternStore | None = None,
        pattern_builder: AOTPatternMemoryBuilder | None = None,
    ) -> None:
        self.store = store
        self.matcher = matcher or ResolutionMemoryMatcher()
        self.pattern_store = pattern_store or SQLiteAOTPatternStore(store.database_path)
        self.pattern_builder = pattern_builder or AOTPatternMemoryBuilder()

    def initialize(self) -> None:
        self.store.initialize()
        self.pattern_store.initialize()

    def record_case(self, case: ResolutionCase) -> None:
        self.store.add_case(case)
        self.refresh_aot_patterns(organization_id=case.organization_id)

    def ingest_confirmed_resolution(self, candidate: ConfirmedResolutionIngestion) -> ResolutionCase:
        case = candidate.to_case()
        existing = self.store.get_case(
            case_id=case.case_id,
            organization_id=case.organization_id,
            client_id=case.client_id,
        )
        if existing is not None:
            same_sources = {
                (item.source_type, item.source_id)
                for item in existing.source_references
            } == {
                (item.source_type, item.source_id)
                for item in case.source_references
            }
            semantically_equal = (
                existing.case_id == case.case_id
                and existing.organization_id == case.organization_id
                and existing.client_id == case.client_id
                and existing.signature.normalized() == case.signature.normalized()
                and existing.steps == case.steps
                and existing.root_cause == case.root_cause
                and existing.final_resolution == case.final_resolution
                and existing.outcome is case.outcome
                and existing.status is case.status
                and existing.technician_confirmed == case.technician_confirmed
                and same_sources
            )
            if semantically_equal:
                return existing
            raise ValueError("conflicting existing resolution case")
        self.store.add_case(case)
        self.refresh_aot_patterns(organization_id=case.organization_id)
        return case

    def refresh_aot_patterns(
        self,
        *,
        organization_id: str,
        technician_approved_case_ids: frozenset[str] = frozenset(),
        now: datetime | None = None,
    ) -> tuple[dict[str, object], ...]:
        cases = self.store.list_organization_cases_for_pattern_derivation(
            organization_id=organization_id,
        )
        patterns = self.pattern_builder.derive(
            organization_id=organization_id,
            cases=cases,
            now=now,
            technician_approved_case_ids=technician_approved_case_ids,
        )
        self.pattern_store.replace_organization_patterns(
            organization_id=organization_id,
            patterns=patterns,
        )
        return tuple(pattern.project() for pattern in patterns)

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

    def search_evidence(
        self,
        *,
        signature: ResolutionSignature,
        organization_id: str,
        client_id: str,
        now: datetime | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        same_client = self.search_similar(
            signature=signature,
            organization_id=organization_id,
            client_id=client_id,
            now=now,
            limit=limit,
        )
        same_client_projection = self.project_search_result(same_client)
        patterns = self.pattern_builder.search(
            signature=signature,
            patterns=self.pattern_store.list_patterns(
                organization_id=organization_id,
            ),
            limit=limit,
        )
        return {
            "retrieval_hierarchy": (
                "same_client_exact_or_similar",
                "aot_sanitized_patterns",
                "generic_playbook_vendor_reference",
            ),
            "current_live_evidence_precedence": True,
            "matches": same_client_projection["matches"],
            "step_evidence": same_client_projection["step_evidence"],
            "aot_patterns": list(patterns),
            "match_count": len(same_client_projection["matches"]),
            "pattern_count": len(patterns),
            "raw_cross_client_cases_exposed": False,
            "grants_authority": False,
            "execution_authority_source": "current_jason_governance_only",
        }

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
            "pattern_count": self.pattern_store.count_patterns(
                organization_id=organization_id,
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
            "pattern_count": self.pattern_store.count_patterns(
                organization_id=organization_id,
            ),
            "scope": "client" if client_id else "organization_aggregate",
            "raw_cases_exposed": False,
            "raw_cross_client_cases_exposed": False,
            "grants_authority": False,
        }

    @staticmethod
    def project_search_result(
        result: ResolutionSearchResult,
    ) -> dict[str, Any]:
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
