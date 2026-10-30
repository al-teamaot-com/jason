from __future__ import annotations
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace

from connectors.src.jason_connectors.approval_requests import (
    ApprovalRequest,ApprovalRequestService,InMemoryApprovalRequestRepository,
)
from jason_runtime.procurement_approval_maintenance import ProcurementApprovalMaintenance
from jason_runtime.procurement_teams_flow import ConfiguredProcurementApprovalAuthority

NOW=datetime(2026,10,25,16,0,tzinfo=timezone.utc)

class Submissions:
    def __init__(self,p):self.p=p
    def get(self,ident):return dict(self.p) if ident==self.p['submission_id'] else None
    def update(self,ident,body):
        assert ident==self.p['submission_id']
        self.p=dict(body)

class Processor:
    supervisor_policy=None
    def __init__(self,svc):self.svc=svc
    def _create_owner_approval(self,submission,*,approver_override,escalation_from,approval_now):
        previous=self.svc.repository.get(escalation_from)
        assert previous.metadata['submission_digest']==submission['digest']
        new=replace(previous,approval_id='procapproval-owner-fallback',
            requested_at=approval_now,expires_at=approval_now+timedelta(hours=1),
            authorized_approver_ids=tuple(approver_override),
            metadata=previous.metadata|{'escalated_from':escalation_from})
        return self.svc.create(new,now=approval_now)

class Sender:
    def __init__(self,*,fail=False):self.sent=[];self.fail=fail
    def send(self,req):
        if self.fail:raise PermissionError('no active Microsoft binding')
        self.sent.append(req)
        return ('signed-teams-id',)


def setup(*,expires_in_minutes=60,status='approval_required',fallback=('person-owner',),sender_fails=False):
    submission={'submission_id':'procsub-a','digest':'f'*64,'status':status,
        'approval_id':'procapproval-supervisor','requester_principal_id':'person-tech',
        'owner_escalation_ids':list(fallback),'supervisor_policy_digest':None}
    svc=ApprovalRequestService(InMemoryApprovalRequestRepository(),
        ConfiguredProcurementApprovalAuthority(frozenset({'person-supervisor','person-owner'})))
    request=ApprovalRequest(approval_id='procapproval-supervisor',
        request_id='procreq-a',correlation_id='corr-a',organization_id='aot',client_id=None,
        requested_by='person-tech',capability='procurement.submission.execute',
        requested_mode='purchase',requested_at=NOW-timedelta(hours=2),
        expires_at=NOW+timedelta(minutes=expires_in_minutes),
        authorized_approver_ids=('person-supervisor',),
        metadata={'submission_id':submission['submission_id'],
                  'submission_digest':submission['digest'],
                  'supervisor_policy_digest':'owner-udf-only'})
    svc.create(request,now=request.requested_at)
    sender=Sender(fail=sender_fails)
    store=Submissions(submission)
    maint=ProcurementApprovalMaintenance(approval_service=svc,submissions=store,
        processor=Processor(svc),sender=sender,now=lambda:NOW)
    return maint,svc,store,sender


def test_one_reminder_without_duplicate_message():
    m,svc,store,sender=setup()
    assert m.run_once(now=NOW)['reminded']==1
    assert m.run_once(now=NOW)['reminded']==0
    assert len(sender.sent)==1
    assert sender.sent[0].approval_id=='procapproval-supervisor'
    assert store.p['approval_id']=='procapproval-supervisor'


def test_supervisor_expiry_creates_new_exact_scope_owner_card():
    m,svc,store,sender=setup(expires_in_minutes=-1)
    result=m.run_once(now=NOW)
    assert result['escalated']==1
    assert store.p['approval_id']=='procapproval-owner-fallback'
    assert len(sender.sent)==1
    approved=sender.sent[0]
    assert approved.authorized_approver_ids==('person-owner',)
    assert approved.metadata['escalated_from']=='procapproval-supervisor'
    assert approved.metadata['submission_digest']==store.p['digest']
    assert m.run_once(now=NOW)['escalated']==0
    assert len(sender.sent)==1


def test_supervisor_unavailable_routes_to_owner_without_purchase():
    m,svc,store,sender=setup(status='approval_delivery_blocked')
    result=m.run_once(now=NOW)
    assert result['escalated']==1
    assert store.p['approval_id']=='procapproval-owner-fallback'
    assert svc.repository.get('procapproval-owner-fallback').status.value=='pending'


def test_owner_delivery_failed_stops_without_fabricating_approval():
    m,svc,store,sender=setup(status='approval_delivery_blocked',sender_fails=True)
    result=m.run_once(now=NOW)
    assert result['escalated']==0 and result['blocked']==1
    assert store.p['status']=='approval_delivery_blocked'
    assert svc.repository.get('procapproval-owner-fallback').status.value=='pending'
    assert not sender.sent


def test_no_owner_fallback_blocks_instead_of_approving():
    m,svc,store,sender=setup(expires_in_minutes=-1,fallback=())
    result=m.run_once(now=NOW)
    assert result['escalated']==0 and result['blocked']==1
    assert store.p['approval_id']=='procapproval-supervisor'
    assert not sender.sent
