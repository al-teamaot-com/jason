from datetime import datetime, timezone

import pytest

from orchestrator.approval_audit import InMemoryApprovalAuditRecorder
from orchestrator.approval_continuation import ApprovalExecutionContinuation
from orchestrator.contracts import (
    ExecutionStage,
    OrchestrationRequest,
    OrchestrationResult,
    OrchestrationStatus,
)


class RecordingOrchestrator:
    def __init__(self):
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return OrchestrationResult(
            execution_id=request.execution_id,
            correlation_id=request.correlation_id,
            capability_name=request.capability_name,
            status=OrchestrationStatus.SUCCEEDED,
            stage=ExecutionStage.COMPLETED,
            reason_codes=("capability_completed",),
            resolution=None,
            artifact_references=request.artifact_references,
            attempts=1,
        )


def request(**overrides):
    values = dict(
        execution_id="exec-1",
        correlation_id="corr-1",
        principal_id="user-1",
        organization_id="org-1",
        client_id="client-1",
        capability_name="autotask.resource.read",
        capability_version="1.0.0",
        requested_mode="execute",
        authority_allowed=True,
        approval_present=True,
        authority_context_id="ctx-fresh",
    )
    values.update(overrides)
    return OrchestrationRequest(**values)


def test_continuation_invokes_orchestrator_then_records_resume():
    orchestrator = RecordingOrchestrator()
    audit = InMemoryApprovalAuditRecorder()
    continuation = ApprovalExecutionContinuation(
        orchestrator=orchestrator,
        audit=audit,
        event_id_factory=lambda: "evt-resume",
        clock=lambda: datetime(2026, 8, 9, 18, 0, tzinfo=timezone.utc),
    )

    result = continuation.execute(
        approval_id="approval-1",
        approved_by="approver-1",
        request=request(),
        channel="microsoft_teams",
        channel_reference_id="message-1",
    )

    assert result.status is OrchestrationStatus.SUCCEEDED
    assert len(orchestrator.requests) == 1
    assert len(audit.events) == 1
    event = audit.events[0]
    assert event.event_type.value == "orchestrator_resumed"
    assert event.authority_context_id == "ctx-fresh"
    assert event.organization_id == "org-1"
    assert event.metadata["approved_by"] == "approver-1"
    assert event.metadata["orchestration_status"] == "succeeded"


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"approval_present": False}, "approval evidence"),
        ({"authority_allowed": False}, "fresh JKD-001 authority"),
        ({"authority_context_id": None}, "fresh JKD-001 authority"),
    ],
)
def test_continuation_fails_closed_before_orchestrator(changes, message):
    orchestrator = RecordingOrchestrator()
    audit = InMemoryApprovalAuditRecorder()
    continuation = ApprovalExecutionContinuation(orchestrator=orchestrator, audit=audit)

    with pytest.raises(PermissionError, match=message):
        continuation.execute(
            approval_id="approval-1",
            approved_by="approver-1",
            request=request(**changes),
        )

    assert orchestrator.requests == []
    assert audit.events == []


def test_audit_failure_does_not_create_orchestration_authority():
    class FailingAudit:
        def record(self, event):
            raise RuntimeError("audit unavailable")

    orchestrator = RecordingOrchestrator()
    continuation = ApprovalExecutionContinuation(orchestrator=orchestrator, audit=FailingAudit())

    with pytest.raises(RuntimeError, match="audit unavailable"):
        continuation.execute(
            approval_id="approval-1",
            approved_by="approver-1",
            request=request(),
        )

    # The orchestrator already independently validates the JKD-001 context. Audit
    # failure cannot mint or broaden authority, but the caller receives failure and
    # must not treat the continuation as successfully completed.
    assert len(orchestrator.requests) == 1


def test_identifiers_are_required_before_execution():
    orchestrator = RecordingOrchestrator()
    continuation = ApprovalExecutionContinuation(
        orchestrator=orchestrator,
        audit=InMemoryApprovalAuditRecorder(),
    )
    with pytest.raises(ValueError, match="identifiers"):
        continuation.execute(approval_id=" ", approved_by="approver-1", request=request())
    assert orchestrator.requests == []
