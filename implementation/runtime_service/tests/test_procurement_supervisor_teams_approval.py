from __future__ import annotations
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import json
from hashlib import sha256
import pytest

from connectors.src.jason_connectors.approval_requests import (
    ApprovalRequest, ApprovalRequestStatus, ApprovalRequestService,
    ApprovalPresentation, InMemoryApprovalRequestRepository,
)
from jason_runtime.procurement_teams_flow import (
    ProcurementApprovalInteractionFlow, ConfiguredProcurementApprovalAuthority,
)
from jason_runtime.playbook_autonomy_review import TeamsGatewayPlaybookApprovalSender
from connectors.microsoft_graph.teams_approval_channel import render_approval_card

NOW=datetime(2026,10,25,15,45,tzinfo=timezone.utc)

class Store:
    def __init__(self,body): self.record=body
    def get(self,submission_id):
        return self.record if self.record['submission_id']==submission_id else None
    def update(self,submission_id,body):
        assert submission_id==self.record['submission_id']
        self.record=dict(body)


def setup(*, actor='person-supervisor', requester='person-tech', org='aot', deadline=None):
    body={'submission_id':'procsub-example','digest':'a'*64,'status':'approval_required',
          'requester_principal_id':requester,'supervisor_policy_digest':None,
          'approval_id':'procapproval-test',
          'total_commitment':'325.00','spending_limit':'200.00','create_po':True,
          'vendor':{'name':'Test vendor'},'product':{'name':'Test widget'}}
    store=Store(body)
    repo=InMemoryApprovalRequestRepository()
    svc=ApprovalRequestService(repository=repo,
        authority=ConfiguredProcurementApprovalAuthority(frozenset({'person-supervisor','person-owner'})))
    challenge = 'b'*48
    req=ApprovalRequest(approval_id='procapproval-test',request_id='procreq-test',
        correlation_id='corr-test',organization_id=org,client_id=None,
        requested_by=requester,capability='procurement.submission.execute',
        requested_mode='purchase',requested_at=NOW-timedelta(minutes=1),
        expires_at=deadline or NOW+timedelta(hours=1),
        authorized_approver_ids=('person-supervisor',),
        metadata={'submission_id':body['submission_id'],
                  'submission_digest':body['digest'],'supervisor_policy_digest':'owner-udf-only',
                  'card_instance_challenge':challenge,
                  'card_instance_challenge_sha256':sha256(challenge.encode()).hexdigest()},
        presentation=ApprovalPresentation(title='Purchase Approval',summary='Exact purchase',facts=(('Total Commitment','$325.00'),('Vendor','Test vendor'))))
    svc.create(req,now=NOW)
    calls=[]
    class Processor:
        supervisor_policy=None
        def execute_submission_with_retry_state(self, approved, *, owner_approval_id):
            calls.append((approved,owner_approval_id))
            return {'summary':'Successfully completed', 'result':{}}
    binding=SimpleNamespace(jason_identity_id=actor,status='active')
    bindings=SimpleNamespace(find=lambda **kwargs: binding if kwargs['microsoft_object_id']=='valid-user' else None)
    def signed_parse(token):
        signed=json.loads(token)
        return 'registered-teams-gateway',SimpleNamespace(
            microsoft_tenant_id='microsoft-tenant-aot', microsoft_object_id='valid-user',
            conversation_id='teams-thread',
            issued_at=datetime.fromisoformat(signed.get('issued_at',NOW.isoformat())),documents=(),
            approval_submit=SimpleNamespace(approval_id=req.approval_id,
                decision=signed.get('decision','approve'),
                channel_response_id='signed-gateway-receipt',
                selections={'card_challenge':signed.get('card_challenge',challenge)}),
        )
    verifier=SimpleNamespace(
        parse=signed_parse,
        verify=lambda token:SimpleNamespace(tenant_id='microsoft-tenant-aot',
            object_id='valid-user',authentication_evidence_hash='e'*64),
    )
    identities=SimpleNamespace(get=lambda identity:SimpleNamespace(
        identity_id=identity,status='active',organization_id='aot'))
    flow=ProcurementApprovalInteractionFlow(bindings=bindings,approval_service=svc,
       submissions=store,processor=Processor(),signed_verifier=verifier,identities=identities)
    kwargs=dict(approval_id=req.approval_id,decision='approve',selections={'card_challenge':challenge},
       signed_envelope={'test_signed_gateway':'not_a_production_token'},
        microsoft_tenant_id='microsoft-tenant-aot',microsoft_object_id='valid-user',
        conversation_id='teams-thread',channel_response_id='signed-gateway-receipt',
        decided_at=NOW)
    return flow,repo,store,calls,kwargs


def test_approved_supervisor_receipt_executes_exactly_once():
    flow,repo,store,calls,kwargs=setup()
    result=flow.handle(**kwargs)
    assert result['status']=='completed'
    assert len(calls)==1
    assert calls[0][1]=='procapproval-test'
    assert repo.accepted_decision('procapproval-test').channel=='microsoft_teams'
    assert repo.accepted_decision('procapproval-test').decided_by=='person-supervisor'
    assert repo.accepted_decision('procapproval-test').authentication_evidence_hash=='e'*64
    with pytest.raises(ValueError,match='no longer pending'):
        flow.handle(**kwargs)
    assert len(calls)==1


def test_denied_approval_performs_no_purchase():
    flow,repo,store,calls,kwargs=setup()
    result=flow.handle(**(kwargs|{'decision':'deny','signed_envelope':{'decision':'deny'}}))
    assert 'No procurement write' in result['reply']['text']
    assert store.record['status']=='denied'
    assert repo.get('procapproval-test').status is ApprovalRequestStatus.DENIED
    assert calls==[]


def test_unapproved_or_cross_tenant_actor_cannot_act():
    flow,repo,store,calls,kwargs=setup(actor='person-intruder')
    with pytest.raises(PermissionError,match='authorized approver'):
        flow.handle(**kwargs)
    with pytest.raises(PermissionError,match='does not match signed gateway'):
        flow.handle(**(kwargs|{'microsoft_object_id':'wrong-tenant'}))
    assert calls==[] and not repo.decisions


def test_requester_cannot_self_approve_even_if_misconfigured_approver_set():
    flow,repo,store,calls,kwargs=setup(actor='person-supervisor',requester='person-supervisor')
    with pytest.raises(PermissionError,match='self-approval'):
        flow.handle(**kwargs)
    assert calls==[] and not repo.decisions


def test_mutated_purchase_digest_invalidates_approval_before_consumption():
    flow,repo,store,calls,kwargs=setup()
    store.record['digest']='b'*64
    with pytest.raises(PermissionError,match='scope changed'):
        flow.handle(**kwargs)
    assert repo.get('procapproval-test').status is ApprovalRequestStatus.PENDING
    assert calls==[]


def test_approver_cannot_edit_amount_through_teams_callback():
    flow,repo,store,calls,kwargs=setup()
    with pytest.raises(PermissionError,match='does not match signed gateway'):
        flow.handle(**(kwargs|{'selections':{'total_commitment':'100'}}))
    assert calls==[]


def test_expires_and_does_not_call_executor():
    flow,repo,store,calls,kwargs=setup(deadline=NOW+timedelta(seconds=10))
    kwargs['decided_at']=NOW+timedelta(seconds=20)
    kwargs['signed_envelope']={'issued_at':kwargs['decided_at'].isoformat()}
    with pytest.raises(PermissionError,match='expired'):
        flow.handle(**kwargs)
    assert calls==[]


def test_only_approve_deny_actions_possible():
    flow,repo,store,calls,kwargs=setup()
    with pytest.raises(PermissionError,match='only Approve or Deny'):
        flow.handle(**(kwargs|{'decision':'request_changes','signed_envelope':{'decision':'request_changes'}}))
    assert calls==[] and not repo.decisions


def test_procurement_card_uses_production_focused_ui_and_exact_gateway_actions():
    flow,repo,store,calls,kwargs=setup()
    card=TeamsGatewayPlaybookApprovalSender._adaptive_card(render_approval_card(repo.get('procapproval-test')))
    assert card['body'][0]['text']=='JASON · AOT'
    assert card['body'][1]['text']=='Approval required'
    assert any(x.get('type')=='Container' and x.get('id')=='jason_purchase_technical_details' for x in card['body'])
    assert [a['title'] for a in card['actions']]==['Approve','Deny']
    assert [a['data']['decision'] for a in card['actions']]==['approve','deny']
    assert all(a['data']['approval_id']=='procapproval-test' for a in card['actions'])
    assert any(item.get('type')=='FactSet' for item in card['body'])
    assert 'microsoft' not in json.dumps(card).lower()
    assert card['actions'][0]['data']['card_challenge']=='b'*48


def test_unsigned_procurement_callback_cannot_authorize_purchase():
    flow,repo,store,calls,kwargs=setup()
    with pytest.raises(PermissionError,match='signed Teams purchase'):
        flow.handle(**(kwargs|{'signed_envelope':None}))
    assert calls==[] and not repo.decisions


def test_borrowed_or_replayed_card_nonce_is_not_accepted():
    flow,repo,store,calls,kwargs=setup()
    with pytest.raises(PermissionError,match='issued card challenge'):
        flow.handle(**(kwargs|{'selections':{'card_challenge':'f'*48},
            'signed_envelope':{'card_challenge':'f'*48}}))
    assert calls==[] and not repo.decisions
