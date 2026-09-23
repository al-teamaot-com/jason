from __future__ import annotations

from dataclasses import dataclass

from .contracts import ImprovementCandidate, ReflectionRecord
from .detectors import detect_candidate_drafts
from .store import SQLiteReflectionStore


@dataclass(frozen=True, slots=True)
class ReflectionObservationResult:
    record: ReflectionRecord
    candidates: tuple[ImprovementCandidate, ...]


class ReflectionService:
    """Record execution quality and surface review candidates.

    This service has no code-deployment, capability-registration, provider-access,
    policy-editing, or approval authority.
    """

    def __init__(self, store: SQLiteReflectionStore) -> None:
        self._store = store

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
