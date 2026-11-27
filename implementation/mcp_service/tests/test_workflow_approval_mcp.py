from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from types import SimpleNamespace as NS

import pytest
from jason_mcp import server
from jason_runtime.teams_workflow_configuration import TeamsWorkflowConfiguration
from jason_runtime.procurement_teams_flow import ProcurementApprovalInteractionFlow, ConfiguredProcurementApprovalAuthority
from connectors.src.jason_connectors.approval_requests import (
    ApprovalRequest, ApprovalPresentation, ApprovalRequestService, InMemoryApprovalRequestRepository,
)
from pathlib import Path


def wire(monkeypatch):
    raw=json.loads((Path(__file__).resolve().parents[3]/'config/communications/teams-workflow-policy-v1.json').read_text())
    raw['enabled']=True
    config=TeamsWorkflowConfiguration.parse(raw)
    now=datetime.now(timezone.utc)
    req=ApprovalRequest(approval_id='procapproval-fixture',request_id='request-fixture',
        correlation_id='correlation-fixture',organization_id='aot',client_id=None,
        requested_by='person-requester',capability='procurement.submission.execute',
        requested_mode='purchase',requested_at=now-timedelta(minutes=1),expires_at=now+timedelta(minutes=30),
        authorized_approver_ids=('person-supervisor',),metadata={'submission_id':'submission-fixture',
            'submission_digest':'a'*64,'supervisor_policy_digest':'owner-udf-only',
            'card_instance_challenge':'b'*48,'card_instance_challenge_sha256':sha256(('b'*48).encode()).hexdigest(),
            'workflow_configuration_digest':config.approval_scope_digest},
        presentation=ApprovalPresentation('Purchase approval','Review purchase',facts=(
            ('Submitted by','Technician'),('Vendor','Fixture supplier'),('Product','Fixture item'),
            ('Quantity','1'),('Total Commitment','$325.00'))))
    repo=InMemoryApprovalRequestRepository()
    svc=ApprovalRequestService(repo,ConfiguredProcurementApprovalAuthority(frozenset({'person-supervisor'})))
    svc.create(req,now=now)
    class Store:
        body={'submission_id':'submission-fixture','digest':'a'*64,'approval_id':req.approval_id,
            'requester_principal_id':req.requested_by,'status':'approval_required',
            'vendor':{'name':'Fixture supplier'},'product':{'name':'Fixture item'},
            'workflow_configuration_digest':config.approval_scope_digest}
        def get(self,key):return dict(self.body) if key=='submission-fixture' else None
        def update(self,key,value):self.body=dict(value)
    calls=[]; audit=[]
    processor=NS(workflow_configuration=NS(load=lambda:config),supervisor_policy=None,
        revalidate_supervisor_contact_route=lambda *args,**kwargs:None,
        notify_approval_event=lambda *args:None,
        execute_submission_with_retry_state=lambda *args,**kwargs: calls.append(kwargs) or {'summary':'PO readback verified'})
    binding=NS(status='active',jason_identity_id='person-supervisor',client_id=None)
    handler=ProcurementApprovalInteractionFlow(bindings=NS(find=lambda **kwargs:binding),
        identities=NS(get=lambda who:NS(identity_id=who,status='active',organization_id='aot')),
        approval_service=svc,submissions=Store(),processor=processor)
    app=NS(identity_authority=NS(audit=NS(append_authority_audit=lambda **kwargs:audit.append(kwargs))))
    monkeypatch.setattr(server,'_runtime',lambda:app)
    monkeypatch.setattr(server,'_runtime_procurement_approval_flow',lambda:handler)
    monkeypatch.setattr(server,'_authenticated_identity',lambda:('person-supervisor','aot','entra-oauth-bearer',None))
    token=NS(token='synthetic-fixture-bearer',claims={'tid':server.JASON_ENTRA_TENANT_ID,'oid':'fixture-oid'})
    monkeypatch.setattr(server,'get_access_token',lambda:token)
    return handler,repo,calls,audit,token


def test_review_and_explicit_decision_use_existing_receipt_and_no_raw_bearer_in_audit(monkeypatch):
    handler,repo,calls,audit,token=wire(monkeypatch)
    preview=server.workflow_approval('procapproval-fixture')
    assert preview['can_decide'] and preview['review']['actions']==[] and calls==[]
    assert 'Fixture item' in json.dumps(preview['review'])
    result=server.workflow_approval('procapproval-fixture','approve',preview['reviewed_scope_sha256'])
    assert result['status']=='completed' and len(calls)==1
    decision=result['approval_decision']
    assert decision['status']=='approved' and decision['card']['actions']==[]
    assert decision['card']['body'][0]['text']=='Purchase approved'
    receipt=repo.accepted_decision('procapproval-fixture')
    assert receipt.channel=='jason_mcp_entra'
    evidence=json.loads(audit[0]['reason_codes'][1])
    assert receipt.authentication_evidence_hash==sha256(json.dumps(evidence,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    assert token.token not in json.dumps(audit)
    reviewed_again=server.workflow_approval('procapproval-fixture')
    assert reviewed_again['status']=='approved' and not reviewed_again['can_decide']
    assert reviewed_again['review']['body'][0]['text']=='Purchase approved'
    # A repeated tool decision cannot execute the purchase again.
    assert server.workflow_approval('procapproval-fixture','approve','a'*64)['status']=='blocked'
    assert len(calls)==1


@pytest.mark.parametrize('change',[{'tid':'other-tenant'}, {'oid':None}])
def test_mcp_fallback_rejects_untrusted_identity_before_ledger(monkeypatch,change):
    handler,repo,calls,audit,token=wire(monkeypatch)
    token.claims.update(change)
    assert server.workflow_approval('procapproval-fixture','approve','a'*64)['status']=='denied'
    assert not repo.decisions and calls==[] and audit==[]


def test_changed_scope_and_missing_audit_fail_closed(monkeypatch):
    handler,repo,calls,audit,token=wire(monkeypatch)
    assert server.workflow_approval('procapproval-fixture','approve','b'*64)['status']=='denied'
    assert not repo.decisions and calls==[]
    monkeypatch.setattr(server,'_runtime',lambda:NS(identity_authority=NS(audit=None)))
    assert server.workflow_approval('procapproval-fixture','approve','a'*64)['status']=='denied'
    assert not repo.decisions and calls==[]


def test_recorded_decision_survives_purchase_failure_without_second_consent(monkeypatch):
    handler,repo,calls,audit,token=wire(monkeypatch)
    def failed(*args,**kwargs):raise OSError('provider outcome unknown')
    handler.processor.execute_submission_with_retry_state=failed
    result=server.workflow_approval('procapproval-fixture','approve','a'*64)
    assert result['status']=='blocked' and result['approval_decision']['status']=='approved'
    assert repo.accepted_decision('procapproval-fixture').status=='approved'
    assert 'recorded' in result['reply']['text']


def test_denial_notification_failure_preserves_terminal_receipt(monkeypatch):
    handler,repo,calls,audit,token=wire(monkeypatch)
    def failed(*args,**kwargs):raise OSError('Teams unavailable')
    handler.processor.notify_approval_event=failed
    result=server.workflow_approval('procapproval-fixture','deny','a'*64)
    assert result['status']=='completed' and result['approval_decision']['status']=='denied'
    assert result['notification_state']=='reconciliation_required'
    assert repo.accepted_decision('procapproval-fixture').status=='denied' and calls==[]


def test_mcp_decision_updates_existing_card_without_sending_new_approval(monkeypatch):
    handler,repo,calls,audit,token=wire(monkeypatch)
    updates=[]
    handler.processor.approval_sender=NS(update_decision=lambda *args,**kwargs:updates.append((args,kwargs)))
    result=server.workflow_approval('procapproval-fixture','approve','a'*64)
    assert result['original_card_state']=='provider_updated'
    assert len(updates)==1 and updates[0][1]['status']=='approved'
    assert updates[0][1]['card']['actions']==[] and len(calls)==1
