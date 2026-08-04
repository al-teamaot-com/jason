from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Mapping, Sequence


class ExecutionMode(str, Enum):
    DETERMINISTIC = "deterministic"
    LOCAL_AI = "local_ai"
    HOSTED_AI = "hosted_ai"
    HUMAN = "human"
    NONE = "none"


class DecisionOutcome(str, Enum):
    ALLOWED = "allowed"
    ALLOWED_LIMITED = "allowed_limited"
    APPROVAL_REQUIRED = "approval_required"
    HUMAN_REQUIRED = "human_required"
    DENIED = "denied"


class PriceConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ExecutionBudget:
    maximum_estimated_cost: Decimal
    currency: str = "USD"
    maximum_input_tokens: int = 0
    maximum_output_tokens: int = 0
    maximum_attempts: int = 1

    def __post_init__(self) -> None:
        if self.maximum_estimated_cost < 0:
            raise ValueError("maximum_estimated_cost must be non-negative.")
        if not self.currency.strip():
            raise ValueError("currency must be non-empty.")
        if self.maximum_input_tokens < 0:
            raise ValueError("maximum_input_tokens must be non-negative.")
        if self.maximum_output_tokens < 0:
            raise ValueError("maximum_output_tokens must be non-negative.")
        if self.maximum_attempts < 1:
            raise ValueError("maximum_attempts must be at least one.")


@dataclass(frozen=True, slots=True)
class DataHandlingPolicy:
    classification: str
    hosted_processing_allowed: bool
    redaction_profile: str | None = None
    retention_allowed: bool = False

    def __post_init__(self) -> None:
        if not self.classification.strip():
            raise ValueError("classification must be non-empty.")


@dataclass(frozen=True, slots=True)
class ExecutionCandidate:
    execution_mode: ExecutionMode
    provider_id: str | None = None
    model_id: str | None = None
    region: str | None = None
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    estimated_attempts: int = 1
    fixed_estimated_cost: Decimal | None = None
    deterministic_quality_sufficient: bool = False
    approved: bool = True
    healthy: bool = True
    supports_classifications: frozenset[str] = field(
        default_factory=frozenset
    )

    def __post_init__(self) -> None:
        if self.estimated_input_tokens < 0:
            raise ValueError("estimated_input_tokens must be non-negative.")
        if self.estimated_output_tokens < 0:
            raise ValueError("estimated_output_tokens must be non-negative.")
        if self.estimated_attempts < 1:
            raise ValueError("estimated_attempts must be at least one.")
        if self.fixed_estimated_cost is not None and self.fixed_estimated_cost < 0:
            raise ValueError("fixed_estimated_cost must be non-negative.")


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    execution_id: str
    correlation_id: str
    capability: str
    capability_version: str
    tenant_id: str
    client_id: str | None
    requested_mode: str
    authority_allowed: bool
    approval_present: bool
    risk: str
    data_handling: DataHandlingPolicy
    budget: ExecutionBudget
    candidates: Sequence[ExecutionCandidate]
    policy_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        required = {
            "execution_id": self.execution_id,
            "correlation_id": self.correlation_id,
            "capability": self.capability,
            "capability_version": self.capability_version,
            "tenant_id": self.tenant_id,
            "requested_mode": self.requested_mode,
            "risk": self.risk,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(
                f"Required execution fields are empty: {', '.join(sorted(missing))}"
            )


@dataclass(frozen=True, slots=True)
class ExecutionCostEstimate:
    provider_cost: Decimal
    internal_compute_cost: Decimal
    infrastructure_cost: Decimal
    operational_cost: Decimal
    total_estimated_cost: Decimal
    currency: str
    pricing_version: str
    confidence: PriceConfidence
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    execution_id: str
    correlation_id: str
    capability: str
    capability_version: str
    execution_mode: ExecutionMode
    tenant_id: str
    client_id: str | None
    provider_id: str | None
    model_id: str | None
    region: str | None
    budget: ExecutionBudget
    data_handling: DataHandlingPolicy
    estimated_cost: ExecutionCostEstimate
    maximum_attempts: int
    policy_ids: tuple[str, ...]
    audit_required: bool = True


@dataclass(frozen=True, slots=True)
class ExecutionDecision:
    execution_id: str
    correlation_id: str
    outcome: DecisionOutcome
    execution_mode: ExecutionMode
    reason_codes: tuple[str, ...]
    policy_ids: tuple[str, ...]
    plan: ExecutionPlan | None
    audit_required: bool = True


@dataclass(frozen=True, slots=True)
class ExecutionUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    reasoning_tokens: int = 0
    tool_calls: int = 0
    attempts: int = 1
    execution_seconds: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class ExecutionAttemptCost:
    attempt_number: int
    execution_mode: ExecutionMode
    provider_id: str | None
    model_id: str | None
    estimated_cost: Decimal
    status: str
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class CostRecord:
    cost_record_id: str
    execution_id: str
    correlation_id: str
    tenant_id: str
    client_id: str | None
    capability: str
    execution_mode: ExecutionMode
    provider_id: str | None
    model_id: str | None
    usage: ExecutionUsage
    provider_cost: Decimal
    internal_compute_cost: Decimal
    infrastructure_cost: Decimal
    operational_cost: Decimal
    total_estimated_cost: Decimal
    currency: str
    pricing_version: str
    confidence: PriceConfidence
    attempts: tuple[ExecutionAttemptCost, ...]
    limitations: tuple[str, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)
