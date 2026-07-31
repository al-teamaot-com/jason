from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Mapping, Sequence


class MemoryClass(str, Enum):
    EXACT = "exact"
    PATTERN = "pattern"
    SIMILAR_CASE = "similar_case"


class MemoryStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"


class MatchDisposition(str, Enum):
    REUSE = "reuse"
    REVIEW = "review"
    REJECT = "reject"


@dataclass(frozen=True)
class NormalizedFacts:
    organization_id: str
    client_id: str
    ticket_id: str
    alert_type: str
    device_role: str
    platform: str
    platform_version: str
    attributes: Mapping[str, str] = field(default_factory=dict)

    def fingerprint_fields(self) -> Mapping[str, str]:
        base = {
            "alert_type": self.alert_type,
            "device_role": self.device_role,
            "platform": self.platform,
            "platform_version": self.platform_version,
        }
        return {**base, **dict(self.attributes)}


@dataclass(frozen=True)
class ApplicabilityRule:
    required: Mapping[str, str] = field(default_factory=dict)
    allowed_values: Mapping[str, Sequence[str]] = field(default_factory=dict)
    excluded: Mapping[str, Sequence[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class VerificationRecipe:
    capability: str
    success_conditions: Mapping[str, str]


@dataclass
class DecisionMemoryRecord:
    memory_id: str
    memory_class: MemoryClass
    title: str
    status: MemoryStatus
    organization_scope: str
    client_scope: str | None
    fingerprint: str | None
    applicability: ApplicabilityRule
    decision: str
    approved_capability: str | None
    verification: VerificationRecipe
    source_ticket_ids: list[str]
    created_at: datetime
    last_verified_at: datetime
    expires_at: datetime
    owner: str
    success_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0
    version: int = 1
    invalidation_reason: str | None = None

    @property
    def success_rate(self) -> float:
        attempts = self.success_count + self.failure_count
        return self.success_count / attempts if attempts else 0.0

    def is_current(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return self.status is MemoryStatus.ACTIVE and now < self.expires_at


@dataclass(frozen=True)
class MemoryMatch:
    memory_id: str
    disposition: MatchDisposition
    score: float
    reasons: tuple[str, ...]
    decision: str | None = None
    approved_capability: str | None = None
