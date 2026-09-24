from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ReflectionSignalKind(str, Enum):
    SEARCH_BROADENING_SUCCESS = "search_broadening_success"
    EXCESSIVE_PAGINATION = "excessive_pagination"
    EXCESSIVE_PROVIDER_CALLS = "excessive_provider_calls"
    REPEATED_FALLBACKS = "repeated_fallbacks"
    USER_CORRECTION = "user_correction"


class CandidateActorKind(str, Enum):
    HUMAN = "human"
    SYSTEM = "system"
    CI = "ci"
    RELEASE = "release"


class CandidateLifecycle(str, Enum):
    OBSERVED = "observed"
    PROPOSED = "proposed"
    TESTED = "tested"
    APPROVED = "approved"
    PROMOTED = "promoted"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class ReflectionRecord:
    record_id: str
    execution_id: str
    correlation_id: str
    organization_id: str
    capability_name: str
    outcome: str
    provider_id: str | None = None
    client_id: str | None = None
    normalized_intent: str = ""
    selector_strategy: str = ""
    requested_result_scope: str = "unknown"
    result_count: int | None = None
    candidate_count: int | None = None
    provider_call_count: int = 0
    pagination_count: int = 0
    fallback_count: int = 0
    evidence_item_count: int = 0
    duration_ms: float | None = None
    search_strategies: tuple[str, ...] = ()
    search_result_counts: tuple[int, ...] = ()
    warning_codes: tuple[str, ...] = ()
    user_correction_category: str | None = None
    observed_at: datetime = field(default_factory=_utcnow)
    schema_version: str = "1.0"

    def validate(self) -> None:
        required = {
            "record_id": self.record_id,
            "execution_id": self.execution_id,
            "correlation_id": self.correlation_id,
            "organization_id": self.organization_id,
            "capability_name": self.capability_name,
            "outcome": self.outcome,
            "schema_version": self.schema_version,
        }
        missing = sorted(name for name, value in required.items() if not value.strip())
        if missing:
            raise ValueError("reflection record missing required fields: " + ", ".join(missing))
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        for name, value in (
            ("result_count", self.result_count),
            ("candidate_count", self.candidate_count),
            ("provider_call_count", self.provider_call_count),
            ("pagination_count", self.pagination_count),
            ("fallback_count", self.fallback_count),
            ("evidence_item_count", self.evidence_item_count),
        ):
            if value is not None and value < 0:
                raise ValueError(f"{name} must not be negative")
        if self.duration_ms is not None and self.duration_ms < 0:
            raise ValueError("duration_ms must not be negative")
        if len(self.search_strategies) != len(self.search_result_counts):
            raise ValueError("search strategy and result-count sequences must align")
        if len(self.search_strategies) > 32:
            raise ValueError("search strategy sequence is unbounded")
        if len(self.warning_codes) > 64:
            raise ValueError("warning code sequence is unbounded")
        bounded = (
            ("normalized_intent", self.normalized_intent, 256),
            ("selector_strategy", self.selector_strategy, 128),
            ("requested_result_scope", self.requested_result_scope, 64),
            ("user_correction_category", self.user_correction_category or "", 128),
        )
        for name, value, maximum in bounded:
            if len(value) > maximum:
                raise ValueError(f"{name} exceeds bounded reflection length")
        for value in (*self.search_strategies, *self.warning_codes):
            if len(value) > 128:
                raise ValueError("reflection sequence value exceeds bounded length")


@dataclass(frozen=True, slots=True)
class ImprovementCandidateDraft:
    signal_kind: ReflectionSignalKind
    capability_name: str
    title: str
    proposal: str
    rationale: str
    provider_id: str | None = None

    def validate(self) -> None:
        if not self.capability_name.strip():
            raise ValueError("candidate capability_name is required")
        if not self.title.strip() or len(self.title) > 160:
            raise ValueError("candidate title must be bounded and non-empty")
        if not self.proposal.strip() or len(self.proposal) > 1200:
            raise ValueError("candidate proposal must be bounded and non-empty")
        if not self.rationale.strip() or len(self.rationale) > 1200:
            raise ValueError("candidate rationale must be bounded and non-empty")

    def candidate_key(self, organization_id: str) -> str:
        self.validate()
        if not organization_id.strip():
            raise ValueError("organization_id is required")
        material = json.dumps(
            {
                "organization_id": organization_id,
                "signal_kind": self.signal_kind.value,
                "capability_name": self.capability_name,
                "provider_id": self.provider_id or "",
                "proposal": self.proposal,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return "reflect-" + sha256(material.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True, slots=True)
class ImprovementCandidate:
    candidate_key: str
    organization_id: str
    signal_kind: ReflectionSignalKind
    capability_name: str
    title: str
    proposal: str
    rationale: str
    state: CandidateLifecycle
    source_record_ids: tuple[str, ...]
    provider_id: str | None = None
    created_at: datetime = field(default_factory=_utcnow)

    def validate(self) -> None:
        if not self.candidate_key.strip() or not self.organization_id.strip():
            raise ValueError("candidate identity and organization are required")
        if not self.source_record_ids:
            raise ValueError("candidate requires at least one source reflection record")
        ImprovementCandidateDraft(
            signal_kind=self.signal_kind,
            capability_name=self.capability_name,
            provider_id=self.provider_id,
            title=self.title,
            proposal=self.proposal,
            rationale=self.rationale,
        ).validate()
        if self.created_at.tzinfo is None:
            raise ValueError("candidate created_at must be timezone-aware")
