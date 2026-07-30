"""Safety-focused tests for the remediation orchestration scaffold."""

from types import SimpleNamespace

import pytest

from .orchestrator import ApprovalRecord, RemediationOrchestrator, WorkflowRequest, WorkflowState


class StubAutotask:
    def __init__(self, ticket):
        self.ticket = ticket
        self.notes = []

    def get_ticket(self, ticket_id):
        return self.ticket

    def add_internal_note(self, ticket_id, body):
        self.notes.append(body)
        return "note-1"

    def add_client_note(self, ticket_id, body):
        return "client-note-1"


class StubTriage:
    def assess(self, ticket):
        return {"outcome": "known_vendor_issue", "confidence": 0.98}


class StubPolicy:
    def __init__(self, outcome="approval_required"):
        self.outcome = outcome

    def evaluate(self, *, request, assessment):
        return {
            "outcome": self.outcome,
            "reason": "pilot policy",
            "plan": {
                "plan_hash": "hash-1",
                "device_id": "device-1",
                "component_id": "approved-qb-update",
                "summary": "Update QuickBooks",
            },
        }

    def validate_approval(self, *, approval, plan_hash):
        return approval.approved and approval.approved_plan_hash == plan_hash


class StubApprovals:
    def request(self, *, request, plan):
        return "approval-1"

    def get(self, approval_id):
        return None


class StubDrmm:
    def __init__(self):
        self.calls = 0

    def run_component(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(job_id="job-1", status="success", output_reference="evidence://drmm/job-1", started_at="now", completed_at="now")


class StubVerification:
    def __init__(self, passed=True):
        self.passed = passed

    def verify(self, *, plan, execution):
        return SimpleNamespace(passed=self.passed, checks=("version updated", "service healthy"), evidence_references=("evidence://verify/1",), failure_reason=None if self.passed else "version unchanged")


class StubCommunications:
    def request_follow_up(self, **kwargs):
        return "follow-up-1"


class StubAudit:
    def record(self, **kwargs):
        return "audit-1"


def build(ticket=None, policy_outcome="approval_required", verification_passed=True):
    autotask = StubAutotask(ticket or {"organization_id": "org-1", "client_id": "client-1"})
    drmm = StubDrmm()
    engine = RemediationOrchestrator(
        autotask=autotask,
        triage=StubTriage(),
        policy=StubPolicy(policy_outcome),
        approvals=StubApprovals(),
        drmm=drmm,
        verification=StubVerification(verification_passed),
        communications=StubCommunications(),
        audit=StubAudit(),
    )
    return engine, autotask, drmm


def request():
    return WorkflowRequest("ticket-1", "org-1", "client-1", "tech-1", "corr-1")


def test_prepare_requests_approval_and_does_not_execute():
    engine, _, drmm = build()
    result = engine.prepare(request())
    assert result.state == WorkflowState.AWAITING_APPROVAL
    assert drmm.calls == 0


def test_cross_client_ticket_is_blocked_before_triage_or_execution():
    engine, _, drmm = build(ticket={"organization_id": "org-1", "client_id": "other-client"})
    with pytest.raises(PermissionError):
        engine.prepare(request())
    assert drmm.calls == 0


def test_mismatched_approval_cannot_execute():
    engine, _, drmm = build()
    plan = {"plan_hash": "hash-1", "device_id": "device-1", "component_id": "approved-qb-update"}
    approval = ApprovalRecord("approval-1", True, "tech-1", "different-hash")
    result = engine.execute(request(), plan=plan, approval=approval)
    assert result.state == WorkflowState.BLOCKED
    assert drmm.calls == 0


def test_failed_verification_escalates_and_preserves_evidence():
    engine, autotask, drmm = build(verification_passed=False)
    plan = {"plan_hash": "hash-1", "device_id": "device-1", "component_id": "approved-qb-update", "summary": "Update QuickBooks"}
    approval = ApprovalRecord("approval-1", True, "tech-1", "hash-1")
    result = engine.execute(request(), plan=plan, approval=approval)
    assert result.state == WorkflowState.ESCALATED
    assert drmm.calls == 1
    assert "evidence://drmm/job-1" in result.evidence_references
    assert autotask.notes


def test_successful_execution_verifies_documents_and_requests_follow_up():
    engine, autotask, drmm = build(verification_passed=True)
    plan = {
        "plan_hash": "hash-1",
        "device_id": "device-1",
        "component_id": "approved-qb-update",
        "summary": "Update QuickBooks",
        "client_follow_up_message": "Please confirm QuickBooks now opens correctly.",
        "channel_preferences": ("phone", "email"),
    }
    approval = ApprovalRecord("approval-1", True, "tech-1", "hash-1")
    result = engine.execute(request(), plan=plan, approval=approval)
    assert result.state == WorkflowState.COMPLETED
    assert drmm.calls == 1
    assert autotask.notes
