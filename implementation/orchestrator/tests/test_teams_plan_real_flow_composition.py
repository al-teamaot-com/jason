"""Exercise actual TeamsApprovalFlow composition with deterministic boundary stubs."""
from datetime import timedelta
import pytest
from orchestrator.approval_audit import ApprovalAuditRecorder, InMemoryApprovalAuditSink
from orchestrator.approval_plan_grants import PlanGrantLedger
from orchestrator.approval_plan_scope import ApprovedPlanScope, ProposedPlanStep
from orchestrator.teams_approval_flow import TeamsApprovalFlow
from orchestrator.teams_plan_approval_service import UniversalTeamsPlanApprovalService
from orchestrator.teams_plan_grant_bridge import ServerOwnedPlanProposal
from test_teams_approval_flow import (NOW, OriginalRequest, ResumedRequest,
    StubTokenVerifier, StubIngress, StubApprovalService, StubResumeBridge, TeamsApprovalFlowTests)


def test_actual_teams_flow_composes_and_audits_grant(tmp_path):
    helper=TeamsApprovalFlowTests()
    original=OriginalRequest()
    scope=ApprovedPlanScope('plan-1','org-1','policy-v1',frozenset({'capability.read','capability.verify'}),frozenset({'client-1'}),2,False,NOW+timedelta(hours=1))
    proposal=ServerOwnedPlanProposal('approval-1','org-1','client-1','requester-1','capability.read','fingerprint-1',scope)
    sink=InMemoryApprovalAuditSink()
    flow=TeamsApprovalFlow(StubTokenVerifier(helper.principal()),StubIngress(object()),
        StubApprovalService(helper.accepted()),StubResumeBridge(ResumedRequest()),
        ApprovalAuditRecorder(sink),event_id_factory=iter(f'event-{i}' for i in range(20)).__next__)
    ledger=PlanGrantLedger(tmp_path/'plans.sqlite3')
    service=UniversalTeamsPlanApprovalService(flow,ledger)
    service.handle_response(token='signed-token',payload={'approval_id':'approval-1'},
        original_request=original,proposal=proposal,decided_at=NOW,now=NOW)
    assert len(sink.events)==4
    assert ApprovalAuditRecorder.verify_chain(sink.events)
    ledger.require_grant(ProposedPlanStep('plan-1','org-1','policy-v1','capability.verify','client-1',1,False),plan_fingerprint='fingerprint-1',now=NOW)
    with pytest.raises(PermissionError):
        ledger.require_grant(ProposedPlanStep('plan-1','org-1','policy-v1','capability.verify','another-client',1,False),plan_fingerprint='fingerprint-1',now=NOW)
