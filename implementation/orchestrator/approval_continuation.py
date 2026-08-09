"""Provider-neutral continuation of an approval-authorized orchestration request.

Approval channels may produce a freshly JKD-001-authorized request, but only the
Central Orchestrator may resume execution. This boundary makes that handoff explicit,
claims the approval continuation before execution to prevent replay, and records the
resume event only after the orchestrator has actually been invoked.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol
from uuid import uuid4

from .approval_audit import ApprovalAuditEvent, ApprovalAuditEventType, ApprovalAuditRecorder
from .approval_continuation_guard import ApprovalContinuationClaim, ApprovalContinuationGuard
from .contracts import OrchestrationRequest, OrchestrationResult


class OrchestratorExecutor(Protocol):
    def execute(self, request: OrchestrationRequest) -> OrchestrationResult: ...


@dataclass(frozen=True, slots=True)
class ApprovalExecutionContinuation:
    orchestrator: OrchestratorExecutor
    audit: ApprovalAuditRecorder
    continuation_guard: ApprovalContinuationGuard
    event_id_factory: Callable[[], str] = lambda: str(uuid4())
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)

    def execute(
        self,
        *,
        approval_id: str,
        approved_by: str,
        request: OrchestrationRequest,
        channel: str | None = None,
        channel_reference_id: str | None = None,
    ) -> OrchestrationResult:
        if not approval_id.strip() or not approved_by.strip():
            raise ValueError("approval continuation identifiers must be non-empty")
        if not request.approval_present:
            raise PermissionError("approval-authorized continuation requires approval evidence")
        if not request.authority_allowed or not request.authority_context_id:
            raise PermissionError("approval-authorized continuation requires fresh JKD-001 authority")

        now = self._now()
        self.continuation_guard.claim(
            ApprovalContinuationClaim(
                approval_id=approval_id,
                organization_id=request.organization_id,
                request_id=request.execution_id,
                correlation_id=request.correlation_id,
                capability=request.capability_name,
                authority_context_id=request.authority_context_id,
                claimed_at=now,
            )
        )

        result = self.orchestrator.execute(request)
        self.audit.record(
            ApprovalAuditEvent(
                event_id=self.event_id_factory(),
                event_type=ApprovalAuditEventType.ORCHESTRATOR_RESUMED,
                occurred_at=self._now(),
                approval_id=approval_id,
                request_id=request.execution_id,
                correlation_id=request.correlation_id,
                organization_id=request.organization_id,
                client_id=request.client_id,
                actor_identity_id=request.principal_id,
                capability=request.capability_name,
                channel=channel,
                channel_reference_id=channel_reference_id,
                authority_context_id=request.authority_context_id,
                metadata={
                    "approved_by": approved_by,
                    "orchestration_status": result.status.value,
                    "orchestration_stage": result.stage.value,
                },
            )
        )
        return result

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            raise ValueError("approval continuation clock must be timezone-aware")
        return value.astimezone(timezone.utc)
