"""Provider-neutral attribution contracts for Jason resource consumption."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping


class ActorType(str, Enum):
    HUMAN = "human"
    SERVICE = "service"
    AGENT = "agent"
    SCHEDULED_PROCESS = "scheduled_process"
    SYSTEM = "system"
    UNKNOWN = "unknown"


class BillingClass(str, Enum):
    METERED = "metered"
    SUBSCRIPTION = "subscription"
    INCLUDED = "included"
    UNKNOWN = "unknown"


class TelemetryQuality(str, Enum):
    EXACT = "exact"
    CALCULATED = "calculated"
    INFERRED = "inferred"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class AttributionContext:
    organization_id: str
    correlation_id: str
    request_id: str
    actor_type: ActorType
    actor_id: str
    source_channel: str
    purpose: str
    capability: str
    client_id: str | None = None
    display_name: str | None = None
    email_address: str | None = None
    workload_name: str | None = None
    workflow_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        required = {
            "organization_id": self.organization_id,
            "correlation_id": self.correlation_id,
            "request_id": self.request_id,
            "actor_id": self.actor_id,
            "source_channel": self.source_channel,
            "purpose": self.purpose,
            "capability": self.capability,
        }
        missing = sorted(name for name, value in required.items() if not str(value).strip())
        if missing:
            raise ValueError(
                "Attribution context fields are empty: " + ", ".join(missing)
            )
        if self.email_address is not None:
            email = self.email_address.strip()
            if not email or "@" not in email or email.startswith("@") or email.endswith("@"):
                raise ValueError("email_address must be valid when supplied")


@dataclass(frozen=True, slots=True)
class UsageAttributionEntry:
    entry_id: str
    context: AttributionContext
    provider: str
    product: str
    service: str
    billing_class: BillingClass
    telemetry_quality: TelemetryQuality
    outcome: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    provider_request_id: str | None = None
    usage_quantity: Decimal | None = None
    usage_unit: str | None = None
    calculated_cost: Decimal | None = None
    provider_reported_cost: Decimal | None = None
    currency: str = "USD"
    model_or_sku: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        required = {
            "entry_id": self.entry_id,
            "provider": self.provider,
            "product": self.product,
            "service": self.service,
            "outcome": self.outcome,
            "currency": self.currency,
        }
        missing = sorted(name for name, value in required.items() if not str(value).strip())
        if missing:
            raise ValueError(
                "Usage attribution entry fields are empty: " + ", ".join(missing)
            )
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")
        for amount in (
            self.usage_quantity,
            self.calculated_cost,
            self.provider_reported_cost,
        ):
            if amount is not None and amount < 0:
                raise ValueError("usage quantities and cost values cannot be negative")
        if self.usage_quantity is not None and not (self.usage_unit or "").strip():
            raise ValueError("usage_unit is required when usage_quantity is supplied")
