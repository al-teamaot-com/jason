from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from orchestrator.approval_audit import ApprovalAuditEventType, ApprovalAuditRecorder, InMemoryApprovalAuditSink
from orchestrator.approval_recovery import (
    ApprovalRecoveryDisposition,
    ApprovalRecoveryRecord,
    InMemoryApprovalRecoveryLedger,
)
from orchestrator.approval_recovery_retry import (
    GovernedApprovalRecoveryRetryExecutor,
    InMemoryApprovalRecoveryRetryGuard,
)
from orchestrator.contracts import (
    ExecutionStage,
    OrchestrationMode,
    OrchestrationRequest,
    OrchestrationResult,
    OrchestrationStatus,
)
from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget


NOW = datetime(2026, 8, 9, 18, 0, tzinfo=timezone.utc)


@dataclass
class FakeOrchestrator:
    calls: int = 0

    def execute(self, request: OrchestrationRequest) -> OrchestrationResult:
        self.calls += 1
        return OrchestrationResult(
            execution_id=request.execution_id,
            correlation_id=request.correlation_id,
            capability_name=request.capability_name,
            status=OrchestrationStatus.SUCCEEDED,
            stage=ExecutionStage.COMPLETED,
            reason_codes=("completed",),
            resolution=None,
        )


def request(*, organization_id: str = "org-1", authority_context_id: str = "ctx-fresh") -> OrchestrationRequest:
    return OrchestrationRequest(
        execution_id="req-1",
        correlation_id="corr-1",
        principal_id="operator-1",
        organization_id=organization_id,
        capability_name="resource.write",
        capability_version=None,
        requested_mode="execute",
        orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=True,
        approval_present=True,
        risk="high",
        data_handling=DataHandlingPolicy(),
        budget=ExecutionBudget(),
        authority_context_id=authority_context_id,
    )


def recovery(*, disposition: ApprovalRecoveryDisposition = ApprovalRecoveryDisposition.RETRY_AUTHORIZED) -> ApprovalRecoveryRecord:
    return ApprovalRecoveryRecord(
        recovery_id="recovery-1",
        approval_id="approval-1",
        organization_id="org-1",
        request_id="req-1",
        correlation_id="corr-1",
        capability="resource.write",
        decided_by="operator-1",
        disposition=disposition,
        reason="verified original execution did not complete",
        decided_at=NOW,
        evidence_references=("artifact://evidence-1",),
        fresh_authority_context_id="ctx-fresh" if disposition is ApprovalRecoveryDisposition.RETRY_AUTHORIZED else None,
    )


def build(record: ApprovalRecoveryRecord):
    ledger = InMemoryApprovalRecoveryLedger()
    ledger.record(record)
    sink = InMemoryApprovalAuditSink()
    orchestrator = FakeOrchestrator()
    executor = GovernedApprovalRecoveryRetryExecutor(
        recovery_ledger=ledger,
        retry_guard=InMemoryApprovalRecoveryRetryGuard(),
        orchestrator=orchestrator,
        audit=ApprovalAuditRecorder(sink),
        event_id_factory=lambda: "event-1",
        clock=lambda: NOW,
    )
    return executor, orchestrator, sink


def test_retry_executes_once_through_orchestrator_and_audits() -> None:
    executor, orchestrator, sink = build(recovery())
    result = executor.execute(recovery_id="recovery-1", request=request())
    assert result.status is OrchestrationStatus.SUCCEEDED
    assert orchestrator.calls == 1
    assert sink.events[-1].event_type is ApprovalAuditEventType.ORCHESTRATOR_RESUMED
    assert sink.events[-1].metadata["recovery_id"] == "recovery-1"
    assert sink.events[-1].metadata["recovery_retry"] == "true"

    with pytest.raises(PermissionError, match="already been consumed"):
        executor.execute(recovery_id="recovery-1", request=request())
    assert orchestrator.calls == 1


def test_retry_requires_retry_authorized_disposition() -> None:
    executor, orchestrator, _ = build(recovery(disposition=ApprovalRecoveryDisposition.ABANDONED))
    with pytest.raises(PermissionError, match="not authorized"):
        executor.execute(recovery_id="recovery-1", request=request())
    assert orchestrator.calls == 0


def test_retry_fails_closed_on_tenant_or_scope_mismatch() -> None:
    executor, orchestrator, _ = build(recovery())
    with pytest.raises(PermissionError, match="scope mismatch"):
        executor.execute(recovery_id="recovery-1", request=request(organization_id="org-2"))
    assert orchestrator.calls == 0


def test_retry_requires_exact_fresh_authority_context() -> None:
    executor, orchestrator, _ = build(recovery())
    with pytest.raises(PermissionError, match="fresh JKD-001 authority context mismatch"):
        executor.execute(recovery_id="recovery-1", request=request(authority_context_id="ctx-other"))
    assert orchestrator.calls == 0


def test_retry_requires_existing_recovery_record() -> None:
    ledger = InMemoryApprovalRecoveryLedger()
    orchestrator = FakeOrchestrator()
    executor = GovernedApprovalRecoveryRetryExecutor(
        recovery_ledger=ledger,
        retry_guard=InMemoryApprovalRecoveryRetryGuard(),
        orchestrator=orchestrator,
        audit=ApprovalAuditRecorder(InMemoryApprovalAuditSink()),
    )
    with pytest.raises(PermissionError, match="not found"):
        executor.execute(recovery_id="missing", request=request())
    assert orchestrator.calls == 0
