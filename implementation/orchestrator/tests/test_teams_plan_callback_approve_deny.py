"""Controlled callback contract, not a real Microsoft Teams provider interaction."""
from dataclasses import replace
from types import SimpleNamespace
import pytest
from orchestrator.approval_plan_scope import ProposedPlanStep
from orchestrator.teams_plan_proposal_repository import PlanProposalRepository
from orchestrator.teams_plan_response_dispatch import UniversalPlanResponseDispatch
from test_teams_plan_approval_service import setup, NOW
from orchestrator.teams_plan_approval_service import UniversalTeamsPlanApprovalService

class TrustedSource:
    def require(self, approval_id, *, tenant_id, object_id):
        if approval_id != 'planapproval-1' or (tenant_id, object_id) != ('tenant', 'actor'):
            raise PermissionError('actor not recognized')
        return 'verified-token'

class StoredRequest:
    def __init__(self, request):
        self.request=request
    def require(self, approval_id):
        assert approval_id == 'planapproval-1'
        return self.request

@pytest.mark.parametrize('decision,status,expect_grant', [
    ('approve', 'approved', True), ('deny', 'denied', False)])
def test_full_callback_contract_with_durable_scope(tmp_path, decision, status, expect_grant):
    service, flow, proposal, request = setup(tmp_path, status=status)
    proposal = replace(proposal, approval_id='planapproval-1')
    repository = PlanProposalRepository(tmp_path/'proposals.db')
    repository.store(proposal)
    # Stub for cryptographic Microsoft verification; live provider proof is separate.
    verifier = SimpleNamespace(verify=lambda token: SimpleNamespace(tenant_id='tenant',object_id='actor'))
    def verified_response(**kwargs):
        result = flow.handle_response(**kwargs)
        result.accepted_approval.approval_id = 'planapproval-1'
        return result
    service = UniversalTeamsPlanApprovalService(SimpleNamespace(token_verifier=verifier, handle_response=verified_response), service.ledger)
    adapter = UniversalPlanResponseDispatch(service, repository, StoredRequest(request), TrustedSource())
    result=adapter.handle(approval_id='planapproval-1', decision=decision,
        microsoft_tenant_id='tenant', microsoft_object_id='actor',
        channel_response_id='receipt-'+decision)
    assert result.accepted_approval.status == status
    step=ProposedPlanStep('plan','aot','policy','build','c1',1,False)
    if expect_grant:
        # Fixture approval ID must match durable plan proposal in approval evidence.
        service.ledger.require_grant(step, plan_fingerprint='digest', now=NOW)
    else:
        with pytest.raises(PermissionError):
            service.ledger.require_grant(step, plan_fingerprint='digest', now=NOW)
