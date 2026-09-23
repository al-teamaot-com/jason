"""Governed reflection and continuous-improvement foundation."""

from .collector import reflection_record_from_events
from .contracts import (
    CandidateActorKind,
    CandidateLifecycle,
    ImprovementCandidate,
    ImprovementCandidateDraft,
    ReflectionRecord,
    ReflectionSignalKind,
)
from .detectors import detect_candidate_drafts
from .service import ReflectionObservationResult, ReflectionService
from .store import SQLiteReflectionStore

__all__ = [
    "CandidateActorKind",
    "CandidateLifecycle",
    "ImprovementCandidate",
    "ImprovementCandidateDraft",
    "ReflectionObservationResult",
    "ReflectionRecord",
    "ReflectionService",
    "ReflectionSignalKind",
    "SQLiteReflectionStore",
    "detect_candidate_drafts",
    "reflection_record_from_events",
]
