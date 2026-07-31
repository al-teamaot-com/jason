"""Provider-neutral contracts for Jason's model usage ledger."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence


class UsageSource(str, Enum):
    PROVIDER_REPORTED = "provider_reported"
    LOCAL_RUNTIME_REPORTED = "local_runtime_reported"
    RECONCILED = "reconciled"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"


class AttemptOutcome(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass(frozen=True)
class UsageContext:
    workflow_id: str
    request_id: str
    attempt_id: str
    organization_id: str
    client_id: str | None
    capability: str
    agent_name: str | None = None
    ticket_id: str | None = None
    parent_attempt_id: str | None = None
    routing_profile: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None

    def validate(self) -> None:
        values = (
            self.input_tokens,
            self.cached_input_tokens,
            self.output_tokens,
            self.reasoning_tokens,
            self.total_tokens,
        )
        if any(value is not None and value < 0 for value in values):
            raise ValueError("token counts cannot be negative")

        known_components = [
            value
            for value in (self.input_tokens, self.output_tokens)
            if value is not None
        ]
        if self.total_tokens is not None and len(known_components) == 2:
            minimum_total = sum(known_components)
            if self.total_tokens < minimum_total:
                raise ValueError("total tokens cannot be less than input plus output")


@dataclass(frozen=True)
class CostUsage:
    provider_reported_cost: Decimal | None = None
    calculated_cost: Decimal | None = None
    currency: str = "USD"

    def validate(self) -> None:
        if self.provider_reported_cost is not None and self.provider_reported_cost < 0:
            raise ValueError("provider-reported cost cannot be negative")
        if self.calculated_cost is not None and self.calculated_cost < 0:
            raise ValueError("calculated cost cannot be negative")
        if not self.currency:
            raise ValueError("currency is required")


@dataclass(frozen=True)
class UsageEntry:
    entry_id: str
    context: UsageContext
    provider: str
    model: str
    outcome: AttemptOutcome
    usage_source: UsageSource
    tokens: TokenUsage
    cost: CostUsage = field(default_factory=CostUsage)
    provider_request_id: str | None = None
    provider_usage_reference: str | None = None
    finish_reason: str | None = None
    started_at: datetime | None = None
    completed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: int | None = None
    time_to_first_token_ms: int | None = None
    local_eval_duration_ms: int | None = None
    confidence: float = 1.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        required = (
            self.entry_id,
            self.context.workflow_id,
            self.context.request_id,
            self.context.attempt_id,
            self.context.organization_id,
            self.context.capability,
            self.provider,
            self.model,
        )
        if any(not value for value in required):
            raise ValueError("usage entry is missing a required identifier")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        for duration in (
            self.duration_ms,
            self.time_to_first_token_ms,
            self.local_eval_duration_ms,
        ):
            if duration is not None and duration < 0:
                raise ValueError("durations cannot be negative")
        self.tokens.validate()
        self.cost.validate()


@dataclass(frozen=True)
class UsageAdjustment:
    adjustment_id: str
    original_entry_id: str
    organization_id: str
    reason: str
    created_at: datetime
    replacement_tokens: TokenUsage | None = None
    replacement_cost: CostUsage | None = None
    authoritative_reference: str | None = None


@dataclass(frozen=True)
class UsageTotals:
    attempts: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    total_tokens: int
    provider_reported_cost: Decimal
    calculated_cost: Decimal
    unknown_usage_attempts: int


class UsageLedger(Protocol):
    def append(self, entry: UsageEntry) -> None:
        """Append one immutable usage entry using attempt ID as an idempotency key."""

    def append_adjustment(self, adjustment: UsageAdjustment) -> None:
        """Append a correction without mutating the original usage entry."""

    def list_entries(
        self,
        *,
        organization_id: str,
        workflow_id: str | None = None,
        client_id: str | None = None,
        ticket_id: str | None = None,
    ) -> Sequence[UsageEntry]:
        """Return entries only within the validated organization scope."""

    def totals(
        self,
        *,
        organization_id: str,
        workflow_id: str | None = None,
        client_id: str | None = None,
        ticket_id: str | None = None,
    ) -> UsageTotals:
        """Aggregate all attempts, including failures and fallbacks."""
