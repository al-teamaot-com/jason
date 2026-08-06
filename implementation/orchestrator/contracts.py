from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.resolution import CapabilityResolutionResult


class OrchestrationMode(str, Enum):
    CHECK_ONLY = "check_only"
    EXECUTE = "execute"


class OrchestrationStatus(str, Enum):
    VALIDATED = "validated"
    SUCCEEDED = "succeeded"
    APPROVAL_REQUIRED = "approval_required"
    HUMAN_REQUIRED = "human_required"
    DENIED = "denied"
    FAILED = "failed"


class ExecutionStage(str, Enum):
    RECEIVED = "received"
    RESOLVING = "resolving"
    POLICY_DECIDED = "policy_decided"
    INVOKING = "invoking"
    COMPLETED = "completed"
    DENIED = "denied"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    reference: str
    media_type: str | None = None
    sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.reference.strip():
            raise ValueError("artifact reference must be non-empty.")
        if self.media_type is not None and not self.media_type.strip():
            raise ValueError("media_type must be non-empty when provided.")
        if self.sha256 is not None and len(self.sha256) != 64:
            raise ValueError("sha256 must contain 64 hexadecimal characters.")


@dataclass(frozen=True, slots=True)
class OrchestrationRequest:
    execution_id: str
    correlation_id: str
    principal_id: str
    organization_id: str
    capability_name: str
    capability_version: str | None
    requested_mode: str
    orchestration_mode: OrchestrationMode
    authority_allowed: bool
    approval_present: bool
    risk: str
    data_handling: DataHandlingPolicy
    budget: ExecutionBudget
    arguments: Mapping[str, Any] = field(default_factory=dict)
    client_id: str | None = None
    region: str | None = None
    policy_ids: tuple[str, ...] = ()
    artifact_references: tuple[ArtifactReference, ...] = ()
    requester_kind: str = "human"
    allow_pilot_capability: bool = False
    allow_pilot_provider: bool = False

    def __post_init__(self) -> None:
        required = {
            "execution_id": self.execution_id,
            "correlation_id": self.correlation_id,
            "principal_id": self.principal_id,
            "organization_id": self.organization_id,
            "capability_name": self.capability_name,
            "requested_mode": self.requested_mode,
            "risk": self.risk,
            "requester_kind": self.requester_kind,
        }
        missing = sorted(
            name for name, value in required.items() if not value.strip()
        )
        if missing:
            raise ValueError(
                "Required orchestration fields are empty: "
                + ", ".join(missing)
            )
        if self.capability_version is not None and not self.capability_version.strip():
            raise ValueError("capability_version must be non-empty when provided.")
        if self.requester_kind not in {"human", "service", "agent"}:
            raise ValueError("requester_kind must be human, service, or agent.")
        forbidden = {
            "target_agent",
            "agent_endpoint",
            "invoke_agent",
            "recipient_agent",
        }
        present = sorted(forbidden.intersection(self.arguments))
        if present:
            raise ValueError(
                "Direct agent invocation is prohibited; request a named capability instead: "
                + ", ".join(present)
            )


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    execution_id: str
    correlation_id: str
    capability_name: str
    status: OrchestrationStatus
    stage: ExecutionStage
    reason_codes: tuple[str, ...]
    resolution: CapabilityResolutionResult
    output: Mapping[str, Any] = field(default_factory=dict)
    artifact_references: tuple[ArtifactReference, ...] = ()
    attempts: int = 0
    provider_id: str | None = None
    error_code: str | None = None

    def __post_init__(self) -> None:
        if not self.reason_codes:
            raise ValueError("reason_codes must not be empty.")
        if self.attempts < 0:
            raise ValueError("attempts must not be negative.")
