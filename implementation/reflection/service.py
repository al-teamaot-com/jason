from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from uuid import uuid4

from .contracts import (
    CandidateActorKind,
    CandidateLifecycle,
    ImprovementCandidate,
    ReflectionRecord,
    RegressionEvidence,
    UserCorrectionAudit,
)
from .detectors import detect_candidate_drafts
from .store import SQLiteReflectionStore


@dataclass(frozen=True, slots=True)
class ReflectionObservationResult:
    record: ReflectionRecord
    candidates: tuple[ImprovementCandidate, ...]


@dataclass(frozen=True, slots=True)
class UserCorrectionIngestionResult:
    correction: UserCorrectionAudit
    observation: ReflectionObservationResult


class ReflectionService:
    """Governed reflection service with no production-change authority.

    Reflection may observe execution quality, record authenticated correction
    signals, and maintain a review lifecycle. It cannot edit code, capability
    registrations, provider access, policy, permissions, or execution authority.
    """

    def __init__(self, store: SQLiteReflectionStore) -> None:
        self._store = store

    @property
    def store(self) -> SQLiteReflectionStore:
        return self._store

    def observe(self, record: ReflectionRecord) -> ReflectionObservationResult:
        record.validate()
        self._store.append_record(record)
        candidates = tuple(
            self._store.observe_candidate(
                draft=draft,
                source_record=record,
            )
            for draft in detect_candidate_drafts(record)
        )
        return ReflectionObservationResult(record=record, candidates=candidates)

    def ingest_authenticated_user_correction(
        self,
        *,
        source_record_id: str,
        organization_id: str,
        principal_id: str,
        category: str,
        authenticated: bool,
        observed_at: datetime | None = None,
    ) -> UserCorrectionIngestionResult:
        if not authenticated:
            raise PermissionError("user correction ingestion requires authenticated human context")
        if not principal_id.strip():
            raise PermissionError("authenticated correction principal is required")
        category = category.strip()
        if not category or len(category) > 128:
            raise ValueError("correction category must be bounded and non-empty")
        source = self._store.get_record(
            source_record_id,
            organization_id=organization_id,
        )
        if source is None:
            raise ValueError("correction source reflection record not found in organization scope")

        when = observed_at or datetime.now(timezone.utc)
        derived = replace(
            source,
            record_id=str(uuid4()),
            outcome="user_corrected",
            selector_strategy="authenticated_user_correction",
            result_count=None,
            candidate_count=None,
            provider_call_count=0,
            pagination_count=0,
            fallback_count=0,
            evidence_item_count=0,
            duration_ms=None,
            search_strategies=(),
            search_result_counts=(),
            warning_codes=(),
            user_correction_category=category,
            observed_at=when,
        )
        observation = self.observe(derived)
        correction = UserCorrectionAudit(
            correction_id=str(uuid4()),
            organization_id=organization_id,
            source_record_id=source_record_id,
            correction_record_id=derived.record_id,
            principal_id=principal_id.strip(),
            category=category,
            observed_at=when,
        )
        self._store.append_user_correction_audit(correction)
        return UserCorrectionIngestionResult(
            correction=correction,
            observation=observation,
        )

    def record_regression_result(
        self,
        *,
        candidate_key: str,
        organization_id: str,
        test_reference: str,
        passed: bool,
        actor_id: str,
        reason: str,
    ) -> RegressionEvidence:
        return self._store.record_regression_result(
            candidate_key=candidate_key,
            organization_id=organization_id,
            test_reference=test_reference,
            passed=passed,
            actor_id=actor_id,
            actor_kind=CandidateActorKind.CI,
            reason=reason,
        )

    def transition_candidate(
        self,
        *,
        candidate_key: str,
        organization_id: str,
        new_state: CandidateLifecycle,
        actor_id: str,
        actor_kind: CandidateActorKind,
        reason: str,
    ) -> ImprovementCandidate:
        return self._store.transition_candidate(
            candidate_key,
            organization_id=organization_id,
            new_state=new_state,
            actor_id=actor_id,
            actor_kind=actor_kind,
            reason=reason,
        )

    def candidate_projection(
        self,
        *,
        candidate_key: str,
        organization_id: str,
    ) -> dict[str, object]:
        candidate = self._store.get_candidate(
            candidate_key,
            organization_id=organization_id,
        )
        if candidate is None:
            raise LookupError("reflection candidate not found in organization scope")
        regressions = self._store.list_regression_evidence(
            candidate_key=candidate_key,
            organization_id=organization_id,
        )
        return {
            "candidate_key": candidate.candidate_key,
            "organization_id": candidate.organization_id,
            "signal_kind": candidate.signal_kind.value,
            "capability_name": candidate.capability_name,
            "provider_id": candidate.provider_id,
            "title": candidate.title,
            "proposal": candidate.proposal,
            "rationale": candidate.rationale,
            "state": candidate.state.value,
            "source_record_count": len(candidate.source_record_ids),
            "regression_evidence": [
                {
                    "regression_id": item.regression_id,
                    "test_reference": item.test_reference,
                    "passed": item.passed,
                    "actor_id": item.actor_id,
                    "actor_kind": item.actor_kind.value,
                    "recorded_at": item.recorded_at.isoformat(),
                }
                for item in regressions
            ],
            "can_change_production": False,
            "grants_authority": False,
            "execution_authority_source": "current_jason_governance_only",
        }

    def list_candidate_projections(
        self,
        *,
        organization_id: str,
        state: CandidateLifecycle | None = None,
        limit: int = 100,
    ) -> tuple[dict[str, object], ...]:
        return tuple(
            self.candidate_projection(
                candidate_key=item.candidate_key,
                organization_id=organization_id,
            )
            for item in self._store.list_candidates(
                organization_id=organization_id,
                state=state,
                limit=limit,
            )
        )

    def summary(self, *, organization_id: str) -> dict[str, object]:
        return self._store.summary(organization_id=organization_id)
