from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from orchestrator.approval_plan_grants import PlanGrantLedger
from orchestrator.approval_plan_scope import ApprovedPlanScope, ProposedPlanStep
from orchestrator.teams_plan_approval_service import UniversalTeamsPlanApprovalService
from orchestrator.teams_plan_grant_bridge import ServerOwnedPlanProposal

NOW = datetime(2026, 10, 16, tzinfo=timezone.utc)

class VerifiedFlow:
    def __init__(self, *, status='approved'):
        self.calls = 0
        self.status = status
    def handle_response(self, **kwargs):
        self.calls += 1
        approved = SimpleNamespace(approval_id='approval', status=self.status,
            organization_id='aot', client_id='c1', requested_by='requester',
            capability='build', decided_by='reviewer', decided_at=NOW,
            expires_at=NOW + timedelta(minutes=10))
        return SimpleNamespace(accepted_approval=approved,
            resumed_request=SimpleNamespace(authority_context_id='fresh-authority') if self.status == 'approved' else None)


def setup(tmp_path, status='approved'):
    scope=ApprovedPlanScope('plan', 'aot', 'policy', frozenset({'build','test'}), frozenset({'c1'}), 2, False, NOW + timedelta(hours=1))
    proposal=ServerOwnedPlanProposal('approval','aot','c1','requester','build','digest',scope)
    original=SimpleNamespace(organization_id='aot',client_id='c1',principal_id='requester',capability_name='build')
    flow=VerifiedFlow(status=status)
    ledger=PlanGrantLedger(tmp_path / 'ledger.sqlite3')
    return UniversalTeamsPlanApprovalService(flow,ledger), flow, proposal, original


def test_approved_flow_grants_multiple_bound_steps(tmp_path):
    service,flow,proposal,request=setup(tmp_path)
    service.handle_response(token='signed',payload={'approval_id':'approval'},original_request=request,proposal=proposal,decided_at=NOW)
    assert flow.calls == 1
    for capability in ('build','test'):
        service.ledger.require_grant(ProposedPlanStep('plan','aot','policy',capability,'c1',1,False),plan_fingerprint='digest',now=NOW)


def test_denial_never_creates_grant(tmp_path):
    service,flow,proposal,request=setup(tmp_path,status='denied')
    service.handle_response(token='signed',payload={'approval_id':'approval'},original_request=request,proposal=proposal,decided_at=NOW)
    with pytest.raises(PermissionError):
        service.ledger.require_grant(ProposedPlanStep('plan','aot','policy','build','c1',1,False),plan_fingerprint='digest',now=NOW)


def test_changed_original_request_rejected_before_consuming_decision(tmp_path):
    service,flow,proposal,request=setup(tmp_path)
    request.organization_id='different'
    with pytest.raises(PermissionError):
        service.handle_response(token='signed',payload={'approval_id':'approval'},original_request=request,proposal=proposal,decided_at=NOW)
    assert flow.calls == 0


def test_repeated_decision_cannot_issue_new_grant(tmp_path):
    service,flow,proposal,request=setup(tmp_path)
    kw=dict(token='signed',payload={'approval_id':'approval'},original_request=request,proposal=proposal,decided_at=NOW)
    service.handle_response(**kw)
    with pytest.raises(Exception):
        service.handle_response(**kw)
