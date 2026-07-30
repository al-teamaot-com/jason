"""Governed Autotask -> triage -> approval -> DRMM -> verification workflow.

This module is orchestration scaffolding only. Provider implementations must be
registered by the central Jason orchestrator. No connector is called directly by
an agent, and no action is executed without a deterministic policy decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence


class WorkflowState(str, Enum):
    RECEIVED = "received"
    TRIAGED = "triaged"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    DOCUMENTING = "documenting"
    FOLLOWING_UP = "following_up"
    COMPLETED = "completed"
    ESCALATED = "escalated"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class WorkflowRequest:
    ticket_id: str
    organization_id: str
    client_id: str
    requester_id: str
    correlation_id: str


@dataclass(frozen=True)
class ApprovalRecord:
    approval_id: str
    approved: bool
    approver_id: str
    approved_plan_hash: str
    expires_at: str | None = None


@dataclass(frozen=True)
class ExecutionResult:
    job_id: str
    status: str
    output_reference: str
    started_at: str
    completed_at: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    checks: tuple[str, ...]
    evidence_references: tuple[str, ...]
    failure_reason: str | None = None


@dataclass(frozen=True)
class WorkflowResult:
    ticket_id: str
    state: WorkflowState
    correlation_id: str
    messages: tuple[str, ...]
    evidence_references: tuple[str, ...] = ()
    requires_human_action: bool = True


class AutotaskPort(Protocol):
    def get_ticket(self, ticket_id: str) -> Mapping[str, Any]: ...
    def add_internal_note(self, ticket_id: str, body: str) -> str: ...
    def add_client_note(self, ticket_id: str, body: str) -> str: ...


class TriagePort(Protocol):
    def assess(self, ticket: Mapping[str, Any]) -> Mapping[str, Any]: ...


class PolicyPort(Protocol):
    def evaluate(self, *, request: WorkflowRequest, assessment: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def validate_approval(self, *, approval: ApprovalRecord, plan_hash: str) -> bool: ...


class ApprovalPort(Protocol):
    def request(self, *, request: WorkflowRequest, plan: Mapping[str, Any]) -> str: ...
    def get(self, approval_id: str) -> ApprovalRecord | None: ...


class DrmmPort(Protocol):
    def run_component(self, *, device_id: str, component_id: str, variables: Mapping[str, Any], idempotency_key: str) -> ExecutionResult: ...


class VerificationPort(Protocol):
    def verify(self, *, plan: Mapping[str, Any], execution: ExecutionResult) -> VerificationResult: ...


class CommunicationPort(Protocol):
    def request_follow_up(self, *, request: WorkflowRequest, message: str, channel_preferences: Sequence[str]) -> str: ...


class AuditPort(Protocol):
    def record(self, *, event_type: str, correlation_id: str, payload: Mapping[str, Any]) -> str: ...


class RemediationOrchestrator:
    """Coordinates registered capabilities; it does not implement connectors."""

    def __init__(
        self,
        *,
        autotask: AutotaskPort,
        triage: TriagePort,
        policy: PolicyPort,
        approvals: ApprovalPort,
        drmm: DrmmPort,
        verification: VerificationPort,
        communications: CommunicationPort,
        audit: AuditPort,
    ) -> None:
        self.autotask = autotask
        self.triage = triage
        self.policy = policy
        self.approvals = approvals
        self.drmm = drmm
        self.verification = verification
        self.communications = communications
        self.audit = audit

    def prepare(self, request: WorkflowRequest) -> WorkflowResult:
        ticket = self.autotask.get_ticket(request.ticket_id)
        self._validate_scope(request, ticket)
        assessment = self.triage.assess(ticket)
        decision = self.policy.evaluate(request=request, assessment=assessment)
        self.audit.record(event_type="remediation.plan.evaluated", correlation_id=request.correlation_id, payload=decision)

        outcome = decision.get("outcome")
        if outcome == "block":
            return WorkflowResult(request.ticket_id, WorkflowState.BLOCKED, request.correlation_id, (str(decision.get("reason", "Policy blocked execution.")),), requires_human_action=True)
        if outcome == "recommend_only":
            return WorkflowResult(request.ticket_id, WorkflowState.TRIAGED, request.correlation_id, ("Recommendation prepared; no execution authorized.",), requires_human_action=True)

        approval_id = self.approvals.request(request=request, plan=decision["plan"])
        return WorkflowResult(request.ticket_id, WorkflowState.AWAITING_APPROVAL, request.correlation_id, (f"Approval requested: {approval_id}",), requires_human_action=True)

    def execute(self, request: WorkflowRequest, *, plan: Mapping[str, Any], approval: ApprovalRecord) -> WorkflowResult:
        plan_hash = str(plan["plan_hash"])
        if not approval.approved or not self.policy.validate_approval(approval=approval, plan_hash=plan_hash):
            return WorkflowResult(request.ticket_id, WorkflowState.BLOCKED, request.correlation_id, ("Approval missing, expired, or does not match the plan.",), requires_human_action=True)

        execution = self.drmm.run_component(
            device_id=str(plan["device_id"]),
            component_id=str(plan["component_id"]),
            variables=dict(plan.get("variables", {})),
            idempotency_key=f"{request.correlation_id}:{plan_hash}",
        )
        self.audit.record(event_type="remediation.execution.completed", correlation_id=request.correlation_id, payload={"job_id": execution.job_id, "status": execution.status, "output_reference": execution.output_reference})

        verification = self.verification.verify(plan=plan, execution=execution)
        note = self._build_ticket_note(plan=plan, execution=execution, verification=verification)
        note_id = self.autotask.add_internal_note(request.ticket_id, note)

        if not verification.passed:
            return WorkflowResult(request.ticket_id, WorkflowState.ESCALATED, request.correlation_id, ("Execution completed but verification failed.", f"Autotask note: {note_id}"), (execution.output_reference, *verification.evidence_references), True)

        follow_up_id = self.communications.request_follow_up(
            request=request,
            message=str(plan.get("client_follow_up_message", "The approved remediation was completed. Please confirm the issue is resolved.")),
            channel_preferences=tuple(plan.get("channel_preferences", ("phone", "email"))),
        )
        return WorkflowResult(request.ticket_id, WorkflowState.COMPLETED, request.correlation_id, ("Remediation and verification completed.", f"Autotask note: {note_id}", f"Follow-up request: {follow_up_id}"), (execution.output_reference, *verification.evidence_references), False)

    @staticmethod
    def _validate_scope(request: WorkflowRequest, ticket: Mapping[str, Any]) -> None:
        if str(ticket.get("organization_id")) != request.organization_id or str(ticket.get("client_id")) != request.client_id:
            raise PermissionError("Ticket scope does not match the authorized organization and client.")

    @staticmethod
    def _build_ticket_note(*, plan: Mapping[str, Any], execution: ExecutionResult, verification: VerificationResult) -> str:
        checks = "; ".join(verification.checks) or "No checks reported"
        return (
            f"Jason governed remediation\n"
            f"Plan: {plan.get('summary', 'Approved remediation')}\n"
            f"DRMM job: {execution.job_id}\n"
            f"Status: {execution.status}\n"
            f"Output: {execution.output_reference}\n"
            f"Verification: {'PASSED' if verification.passed else 'FAILED'}\n"
            f"Checks: {checks}"
        )
