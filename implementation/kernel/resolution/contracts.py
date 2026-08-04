from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping

from kernel.execution_policy import (
    DataHandlingPolicy,
    DecisionOutcome,
    ExecutionBudget,
    ExecutionDecision,
    ExecutionPlan,
)


class ResolutionOutcome(str, Enum):
    RESOLVED = "resolved"
    APPROVAL_REQUIRED = "approval_required"
    HUMAN_REQUIRED = "human_required"
    DENIED = "denied"
    UNRESOLVED = "unresolved"


class CapabilityResolutionStatus(str, Enum):
    RESOLVED_EXACT = "resolved_exact"
    RESOLVED_CURRENT = "resolved_current"
    NOT_FOUND = "not_found"
    INELIGIBLE_LIFECYCLE = "ineligible_lifecycle"
    EXECUTION_MODE_PROHIBITED = "execution_mode_prohibited"
    ISOLATION_CONTEXT_MISSING = "isolation_context_missing"


@dataclass(frozen=True, slots=True)
class CapabilityResolutionRequest:
    execution_id: str
    correlation_id: str
    capability_name: str
    capability_version: str | None
    tenant_id: str
    client_id: str | None
    requested_mode: str
    authority_allowed: bool
    approval_present: bool
    risk: str
    data_handling: DataHandlingPolicy
    budget: ExecutionBudget
    region: str | None = None
    policy_ids: tuple[str, ...] = ()
    allow_pilot_capability: bool = False
    allow_pilot_provider: bool = False

    def __post_init__(self) -> None:
        required = {
            "execution_id": self.execution_id,
            "correlation_id": self.correlation_id,
            "capability_name": self.capability_name,
            "tenant_id": self.tenant_id,
            "requested_mode": self.requested_mode,
            "risk": self.risk,
        }

        missing = [
            name
            for name, value in required.items()
            if not value.strip()
        ]

        if missing:
            raise ValueError(
                "Required resolution fields are empty: "
                + ", ".join(sorted(missing))
            )

        if (
            self.capability_version is not None
            and not self.capability_version.strip()
        ):
            raise ValueError(
                "capability_version must be non-empty when provided."
            )

        if self.region is not None and not self.region.strip():
            raise ValueError(
                "region must be non-empty when provided."
            )


@dataclass(frozen=True, slots=True)
class CapabilityResolutionResult:
    execution_id: str
    correlation_id: str
    capability_name: str
    capability_version: str | None
    outcome: ResolutionOutcome
    capability_status: CapabilityResolutionStatus
    reason_codes: tuple[str, ...]
    eligible_provider_ids: tuple[str, ...] = ()
    selected_provider_id: str | None = None
    execution_decision: ExecutionDecision | None = None
    execution_plan: ExecutionPlan | None = None
    audit_required: bool = True
    limitations: tuple[str, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.execution_id.strip():
            raise ValueError("execution_id must be non-empty.")

        if not self.correlation_id.strip():
            raise ValueError("correlation_id must be non-empty.")

        if not self.capability_name.strip():
            raise ValueError("capability_name must be non-empty.")

        if not self.reason_codes:
            raise ValueError("reason_codes must not be empty.")

        if (
            self.execution_decision is not None
            and self.execution_plan is not self.execution_decision.plan
        ):
            raise ValueError(
                "execution_plan must match the policy decision plan."
            )

        if (
            self.execution_decision is not None
            and self.execution_decision.outcome
            in {
                DecisionOutcome.DENIED,
                DecisionOutcome.APPROVAL_REQUIRED,
                DecisionOutcome.HUMAN_REQUIRED,
            }
            and self.execution_plan is not None
        ):
            raise ValueError(
                "Non-allowing policy outcomes must not include a plan."
            )
