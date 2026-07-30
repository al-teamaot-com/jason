"""Provider-neutral contracts for governed remediation orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence


class AutonomyLevel(str, Enum):
    OBSERVE = "observe"
    RECOMMEND = "recommend"
    APPROVED_EXECUTE = "approved_execute"
    LOW_RISK_AUTONOMOUS = "low_risk_autonomous"
    PROHIBITED = "prohibited"


class PolicyOutcome(str, Enum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    BLOCK = "block"


class ExecutionState(str, Enum):
    PROPOSED = "proposed"
    APPROVAL_PENDING = "approval_pending"
    AUTHORIZED = "authorized"
    RUNNING = "running"
    SUCCEEDED_UNVERIFIED = "succeeded_unverified"
    VERIFIED = "verified"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    ESCALATED = "escalated"


@dataclass(frozen=True)
class RemediationTarget:
    organization_id: str
    client_id: str
    device_id: str
    device_role: str | None = None
    is_server: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RemediationPlan:
    plan_id: str
    plan_version: str
    ticket_id: str
    capability_name: str
    target: RemediationTarget
    reason: str
    evidence_ids: tuple[str, ...]
    requested_autonomy: AutonomyLevel
    expected_result: str
    verification_capability: str
    rollback_capability: str | None
    timeout_seconds: int
    idempotency_key: str
    parameters: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicyDecision:
    outcome: PolicyOutcome
    autonomy_level: AutonomyLevel
    reasons: tuple[str, ...]
    required_approver_roles: tuple[str, ...] = ()
    expires_at: datetime | None = None


@dataclass(frozen=True)
class ApprovalRecord:
    approval_id: str
    plan_id: str
    approver_id: str
    approver_role: str
    approved: bool
    decided_at: datetime
    comment: str | None = None


@dataclass(frozen=True)
class ExecutionEvidence:
    execution_id: str
    provider_name: str
    provider_job_id: str
    started_at: datetime
    completed_at: datetime | None
    exit_code: int | None
    state: ExecutionState
    output_artifact_ref: str | None
    summary: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VerificationResult:
    execution_id: str
    passed: bool
    checked_at: datetime
    summary: str
    evidence_refs: tuple[str, ...] = ()
    observed_state: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RemediationOutcome:
    plan: RemediationPlan
    policy: PolicyDecision
    approvals: tuple[ApprovalRecord, ...]
    execution: ExecutionEvidence | None
    verification: VerificationResult | None
    final_state: ExecutionState
    ticket_note_artifact_ref: str | None = None
    follow_up_communication_id: str | None = None


class RemediationPolicyEngine(Protocol):
    def evaluate(self, plan: RemediationPlan) -> PolicyDecision:
        """Return a deterministic allow, approval, or block decision."""


class CapabilityExecutor(Protocol):
    def execute(self, plan: RemediationPlan) -> ExecutionEvidence:
        """Execute only an already authorized, registered capability."""


class ResultVerifier(Protocol):
    def verify(
        self,
        *,
        plan: RemediationPlan,
        execution: ExecutionEvidence,
    ) -> VerificationResult:
        """Independently verify the expected state after execution."""


class AuditSink(Protocol):
    def append(self, event_name: str, payload: Mapping[str, Any]) -> None:
        """Append an immutable audit event."""


class OutcomeRecorder(Protocol):
    def record(self, outcome: RemediationOutcome) -> None:
        """Persist operational learning without self-promoting autonomy."""
