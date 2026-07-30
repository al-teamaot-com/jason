"""Provider-neutral contracts for Jason's Triage Intelligence Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence


class EvidenceKind(str, Enum):
    PLATFORM_CHANGE = "platform_change"
    KNOWN_ISSUE = "known_issue"
    INTERNAL_HISTORY = "internal_history"
    ENVIRONMENT = "environment"
    RECENT_CHANGE = "recent_change"
    KNOWLEDGE = "knowledge"
    RISK = "risk"


class TriageOutcome(str, Enum):
    EXPECTED_BEHAVIOR = "expected_behavior"
    KNOWN_VENDOR_ISSUE = "known_vendor_issue"
    KNOWN_INTERNAL_PATTERN = "known_internal_pattern"
    ENVIRONMENT_CHANGE = "environment_change"
    PROBABLE_FAULT = "probable_fault"
    SECURITY_OR_COMPLIANCE_RISK = "security_or_compliance_risk"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass(frozen=True)
class TicketContext:
    ticket_id: str
    title: str
    description: str
    organization_id: str
    client_id: str
    device_ids: tuple[str, ...] = ()
    product_hints: tuple[str, ...] = ()
    created_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedSymptoms:
    summary: str
    symptoms: tuple[str, ...]
    products: tuple[str, ...]
    versions: Mapping[str, str] = field(default_factory=dict)
    time_hints: tuple[str, ...] = ()
    change_hints: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str
    kind: EvidenceKind
    source_name: str
    source_reference: str
    title: str
    summary: str
    observed_at: datetime
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    organization_id: str | None = None
    client_id: str | None = None
    product: str | None = None
    version: str | None = None
    confidence: float = 0.0
    authoritative: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def is_fresh(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        return True


@dataclass(frozen=True)
class RankedFinding:
    outcome: TriageOutcome
    confidence: float
    explanation: str
    evidence_ids: tuple[str, ...]
    recommended_action: str
    technician_verification: tuple[str, ...] = ()
    cautions: tuple[str, ...] = ()


@dataclass(frozen=True)
class TriageAssessment:
    ticket_id: str
    generated_at: datetime
    findings: tuple[RankedFinding, ...]
    evidence: tuple[EvidenceItem, ...]
    insufficient_evidence: tuple[str, ...] = ()
    requires_human_review: bool = True


class SymptomNormalizer(Protocol):
    def normalize(self, ticket: TicketContext) -> NormalizedSymptoms:
        """Return structured symptoms without changing the source ticket."""


class IntelligenceProvider(Protocol):
    provider_name: str

    def search(
        self,
        *,
        ticket: TicketContext,
        symptoms: NormalizedSymptoms,
    ) -> Sequence[EvidenceItem]:
        """Return scoped evidence. Providers must fail closed on scope ambiguity."""


class FindingRanker(Protocol):
    def rank(
        self,
        *,
        ticket: TicketContext,
        symptoms: NormalizedSymptoms,
        evidence: Sequence[EvidenceItem],
    ) -> Sequence[RankedFinding]:
        """Rank supported findings and preserve evidence references."""
