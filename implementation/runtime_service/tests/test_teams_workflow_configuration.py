from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from jason_runtime.teams_workflow_configuration import (
    TeamsWorkflowConfiguration, TeamsWorkflowConfigurationFile, TeamsConfigurationError,
)
from jason_runtime.supervisor_contact_routing import resolve_supervisor_contacts
from jason_runtime.procurement_teams_flow import SQLiteProcurementSubmissionStore

ROOT = Path(__file__).resolve().parents[3]
POLICY = ROOT / 'config/communications/teams-workflow-policy-v1.json'


def config(**updates):
    raw = json.loads(POLICY.read_text())
    raw.update(enabled=True, **updates)
    return TeamsWorkflowConfiguration.parse(raw)


def instant(s):
    return datetime.fromisoformat(s)


def test_hourly_reminders_and_ten_business_hour_escalation_across_weekend():
    p = config()
    friday = instant('2026-11-20T17:30:00-05:00')
    monday = instant('2026-11-23T08:30:00-05:00')
    assert p.calendar.minutes_between(friday, monday) == 60
    assert p.due(since=friday, now=monday) == 'reminder'
    assert p.due(since=friday, now=instant('2026-11-23T17:30:00-05:00')) == 'escalated'
    assert p.due(since=friday, now=instant('2026-11-21T12:00:00-05:00')) is None
    assert p.due(since=friday, now=instant('2026-11-23T18:00:00-05:00')) is None


def test_holidays_and_dst_use_the_configured_local_calendar():
    raw = json.loads(POLICY.read_text())
    raw['enabled'] = True
    raw['calendar']['holidays'] = ['2026-11-23']
    p = TeamsWorkflowConfiguration.parse(raw)
    assert p.calendar.minutes_between(instant('2026-11-20T17:30:00-05:00'),
        instant('2026-11-24T08:30:00-05:00')) == 60
    # Sunday DST change contributes no business time.
    assert p.calendar.minutes_between(instant('2026-10-30T17:30:00-04:00'),
        instant('2026-11-02T08:30:00-05:00')) == 60
    with pytest.raises(TeamsConfigurationError):
        p.calendar.is_open(datetime(2026, 11, 23))


def card():
    return SimpleNamespace(capability='procurement.submission.execute', requested_mode='purchase',
        approval_id='procapproval-test', card_instance_challenge='a'*48,
        expires_at='2026-11-23T20:00:00+00:00',
        facts=(('Submitted by', 'Technician'), ('Vendor', 'Supplier'), ('Product', 'Laptop'),
               ('Quantity', '1'), ('Total Commitment', '$999.00'),
               ('internal_scope_fingerprint', 'do-not-display')))


def test_configuration_renders_material_facts_and_preserves_original_signed_actions():
    result = config().render_approval(card())
    text = json.dumps(result)
    assert 'Total including tax and shipping' in text and '$999.00' in text
    assert 'do-not-display' not in text and 'internal_scope_fingerprint' not in text
    assert [a['data'] for a in result['actions']] == [
        {'approval_id': 'procapproval-test', 'card_challenge': 'a'*48, 'decision': d}
        for d in ('approve', 'deny')]
    assert config().render_approval(card(), actionable=False)['actions'] == []
    incomplete = card()
    incomplete.facts = tuple(f for f in incomplete.facts if f[0] != 'Total Commitment')
    with pytest.raises(TeamsConfigurationError, match='required persisted'):
        config().render_approval(incomplete)


def test_second_existing_approval_type_requires_only_a_configuration_entry():
    p = config()
    raw = json.loads(json.dumps(p.raw))
    raw['templates'].append(dict(capability='existing.device.action', mode='review',
        title='Device change approval', explanation='Review the device and change.',
        primary=[dict(source='Device', label='Computer', required=True),
                 dict(source='Change', label='Requested change', required=True)], details=[]))
    p = TeamsWorkflowConfiguration.parse(raw)
    c = card()
    c.capability, c.requested_mode = 'existing.device.action', 'review'
    c.facts = (('Device', 'Test-01'), ('Change', 'Approved existing action'))
    rendered = p.render_approval(c)
    assert rendered['body'][0]['text'] == 'Device change approval'
    assert rendered['actions'][0]['data']['approval_id'] == c.approval_id
    # This registers presentation only, no callback, grants or execution.
    assert 'capability' not in rendered['actions'][0]['data']


def test_reload_picks_up_atomic_configuration_update_and_rejects_invalid_replacement(tmp_path):
    path = tmp_path / 'policy.json'
    raw = json.loads(POLICY.read_text())
    path.write_text(json.dumps(raw))
    source = TeamsWorkflowConfigurationFile(path)
    assert not source.load().enabled
    raw['enabled'] = True
    raw['reminder_business_minutes'] = 120
    replacement = tmp_path / 'new.json'
    replacement.write_text(json.dumps(raw))
    replacement.replace(path)
    assert source.load().raw['reminder_business_minutes'] == 120
    raw['grant_execute'] = True
    path.write_text(json.dumps(raw))
    with pytest.raises(TeamsConfigurationError):
        source.load()


def test_card_configuration_cannot_omit_required_purchase_scope():
    p = json.loads(POLICY.read_text())
    p['templates'][0]['primary'] = []
    with pytest.raises(TeamsConfigurationError, match='material purchase'):
        TeamsWorkflowConfiguration.parse(p)


def contact(ident, email, supervisor='', limit='0', company=0):
    return dict(id=ident, emailAddress=email, companyID=company, isActive=True,
                udf={'Supervisor': supervisor, 'Spending limit': limit})


def route(contacts, requester=None, amount='300'):
    return resolve_supervisor_contacts(requester_id='person-tech',
        requester_contact=requester or contact(1,'tech@example.test','lead@example.test'),
        amount=amount, fallback_id='person-owner',
        allowed_approvers=frozenset({'person-lead', 'person-manager', 'person-owner'}),
        lookup_contact=lambda email: contacts.get(email),
        resolve_identity=lambda email: {'lead@example.test':'person-lead',
            'manager@example.test':'person-manager'}.get(email),
        udf=lambda c, name:c['udf'].get(name))


def test_supervisor_chain_skips_insufficient_spending_authority():
    contacts = {'lead@example.test':contact(2,'lead@example.test','manager@example.test','100'),
                'manager@example.test':contact(3,'manager@example.test','','500')}
    assert route(contacts).approvers == ('person-manager','person-owner')
    assert route(contacts,amount='75').approvers == ('person-lead','person-manager','person-owner')


@pytest.mark.parametrize('case', ['cycle', 'cross_company', 'inactive', 'missing', 'bad_limit'])
def test_bad_supervisor_relationship_routes_safely_to_owner(case):
    c = contact(2,'lead@example.test','','500')
    contacts = {'lead@example.test':c}
    if case == 'cycle': c['udf']['Supervisor']='lead@example.test'
    if case == 'cross_company': c['companyID']=42
    if case == 'inactive': c['isActive']=False
    if case == 'missing': contacts={}
    if case == 'bad_limit': c['udf']['Spending limit']='not a number'
    assert route(contacts).approvers == ('person-owner',)


def test_concurrent_notification_claims_survive_restart_and_unknown_outcome(tmp_path):
    path = tmp_path/'submissions.sqlite3'
    store = SQLiteProcurementSubmissionStore(path)
    store.put_new('s1', dict(submission_id='s1', approval_id='procapproval-1', status='approval_required'))
    def attempt(_):
        return SQLiteProcurementSubmissionStore(path).claim_communication('s1',
            approval_id='procapproval-1', event_key='reminder:1')
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(attempt, range(8))) == 1
    assert not attempt(0)
    with pytest.raises(RuntimeError, match='provider evidence'):
        store.complete_communication('s1', approval_id='procapproval-1',
                                     event_key='reminder:1', receipts=('accepted:synthetic',))
    store.complete_communication('s1', approval_id='procapproval-1',
                                 event_key='reminder:1', receipts=('real-provider-id',))
    assert not attempt(0)
    assert not store.claim_communication('s1', approval_id='old-request', event_key='reminder:2')


def configured_maintenance(tmp_path):
    from connectors.src.jason_connectors.approval_requests import (
        ApprovalRequest, ApprovalPresentation, ApprovalRequestService, InMemoryApprovalRequestRepository,
    )
    from jason_runtime.procurement_approval_maintenance import ProcurementApprovalMaintenance
    from jason_runtime.procurement_teams_flow import ConfiguredProcurementApprovalAuthority
    from datetime import timedelta
    from uuid import uuid4
    p = config()
    path = tmp_path/'policy.json'
    path.write_text(json.dumps(p.raw))
    source = TeamsWorkflowConfigurationFile(path)
    store = SQLiteProcurementSubmissionStore(tmp_path/'s.sqlite3')
    svc = ApprovalRequestService(InMemoryApprovalRequestRepository(),
        ConfiguredProcurementApprovalAuthority(frozenset({'person-lead','person-owner'})))
    start = instant('2026-11-20T17:30:00-05:00')
    request = ApprovalRequest(approval_id='procapproval-original',request_id='request-1',
        correlation_id='corr-1',organization_id='aot',client_id=None,requested_by='person-tech',
        capability='procurement.submission.execute',requested_mode='purchase',
        requested_at=start,expires_at=start+timedelta(minutes=60),
        authorized_approver_ids=('person-lead',),
        presentation=ApprovalPresentation(title='Purchase',summary='Review the purchase'),
        metadata={'submission_id':'s1','submission_digest':'a'*64,
                  'supervisor_policy_digest':'owner-udf-only',
                  'card_instance_challenge':'a'*48,
                  'card_instance_challenge_sha256':__import__('hashlib').sha256(('a'*48).encode()).hexdigest()})
    svc.create(request,now=start)
    store.put_new('s1',dict(submission_id='s1',approval_id=request.approval_id,
        digest='a'*64,status='approval_required',workflow_configuration_digest=p.approval_scope_digest,
        workflow_requested_at=start.isoformat(),supervisor_chain_ids=['person-lead','person-owner']))
    class Processor:
        supervisor_policy=None
        def _create_owner_approval(self,submission,*,approver_override,escalation_from,approval_now):
            from dataclasses import replace
            new = replace(request,approval_id='procapproval-'+uuid4().hex,
                requested_at=approval_now,expires_at=approval_now+timedelta(hours=1),
                authorized_approver_ids=approver_override,
                metadata=request.metadata|{'escalated_from':escalation_from})
            return svc.create(new,now=approval_now)
    class Sender:
        def __init__(self):self.events=[];self.cards=[]
        def send(self, req):
            self.cards.append(req)
            return ('real-card-id',)
        def send_event(self,req,*,event,requester_only=False):
            self.events.append((req,event))
            return ('real-requester-id','real-approver-id')
    sender=Sender()
    m = ProcurementApprovalMaintenance(approval_service=svc,submissions=store,
        processor=Processor(),sender=sender,workflow_configuration=source)
    return m,svc,store,sender,source


def test_expired_button_is_renewed_without_resetting_business_deadline(tmp_path):
    m,svc,store,sender,_ = configured_maintenance(tmp_path)
    monday=instant('2026-11-23T08:30:00-05:00')
    assert m.run_once(now=monday)['reminded']==1
    assert sender.cards[0].authorized_approver_ids==('person-lead',)
    assert svc.repository.get('procapproval-original').status.value=='cancelled'
    assert store.get('s1')['workflow_requested_at']=='2026-11-20T17:30:00-05:00'
    assert m.run_once(now=monday)['reminded']==0
    assert m.run_once(now=instant('2026-11-23T17:30:00-05:00'))['escalated']==1
    assert sender.cards[-1].authorized_approver_ids==('person-owner',)
    assert all(r.metadata['submission_digest']=='a'*64 for r in sender.cards)


def test_owner_gets_hourly_reminders_without_self_escalation(tmp_path):
    m,svc,store,sender,_ = configured_maintenance(tmp_path)
    now=instant('2026-11-23T17:30:00-05:00')
    assert m.run_once(now=now)['escalated']==1
    next_day=instant('2026-11-24T08:30:00-05:00')
    assert m.run_once(now=next_day)['reminded']==1
    assert sender.cards[-1].authorized_approver_ids==('person-owner',)
    assert m.run_once(now=next_day)['reminded']==0


def test_changed_routing_policy_does_not_silently_reauthorize_pending_work(tmp_path):
    m,svc,store,sender,source = configured_maintenance(tmp_path)
    raw=json.loads(source.path.read_text())
    raw['fallback_email']='different-owner@example.test'
    source.path.write_text(json.dumps(raw))
    result=m.run_once(now=instant('2026-11-23T17:30:00-05:00'))
    assert result['blocked']==1
    assert not sender.cards and not sender.events


def test_denial_stops_future_reminders(tmp_path):
    from connectors.src.jason_connectors.approval_requests import ApprovalRequestStatus
    m,svc,store,sender,_ = configured_maintenance(tmp_path)
    req=svc.repository.get('procapproval-original')
    svc.repository.transition_pending(req,status=ApprovalRequestStatus.DENIED)
    assert m.run_once(now=instant('2026-11-23T17:30:00-05:00'))['checked']==0
    assert not sender.cards and not sender.events


def test_presentation_and_reminder_edits_do_not_demand_new_purchase_consent():
    p=config()
    raw=json.loads(json.dumps(p.raw))
    raw['reminder_business_minutes']=120
    raw['templates'][0]['title']='Please review this purchase'
    changed=TeamsWorkflowConfiguration.parse(raw)
    assert changed.digest != p.digest
    assert changed.approval_scope_digest == p.approval_scope_digest


def test_uncertain_reminder_send_is_not_replayed_on_next_hour(tmp_path):
    m,svc,store,sender,_=configured_maintenance(tmp_path)
    def failed(*args,**kwargs):raise OSError('unknown provider result')
    sender.send=failed
    now=instant('2026-11-23T08:30:00-05:00')
    assert m.run_once(now=now)['blocked']==1
    # Old request is cancelled and its one-use attempt claim remains. No
    # pretend decision or second replacement send is created after restart.
    assert svc.repository.get('procapproval-original').status.value=='cancelled'
    assert any(c['state']=='claimed_reconciliation_required'
               for c in store.get('s1')['communication_claims'].values())
    assert m.run_once(now=instant('2026-11-23T09:30:00-05:00'))['blocked']==1


def test_requester_receives_notification_without_approval_buttons(tmp_path,monkeypatch):
    from jason_runtime.playbook_autonomy_review import TeamsGatewayPlaybookApprovalSender
    from jason_runtime.teams_communication_service import TeamsDeliveryReceipt
    from connectors.src.jason_connectors.approval_requests import ApprovalPresentation
    m,svc,store,_,source=configured_maintenance(tmp_path)
    req=replace(svc.repository.get('procapproval-original'),
        presentation=ApprovalPresentation('Purchase','Review the purchase',
            facts=card().facts))
    bindings={p:SimpleNamespace(jason_identity_id=p,status='active',
                microsoft_tenant_id='same-tenant') for p in ('person-tech','person-lead')}
    sender=TeamsGatewayPlaybookApprovalSender(gateway_url='https://unused.example.test',
        token_file=tmp_path/'unused',owner_identity_ids=('person-lead',),
        bindings=SimpleNamespace(find_active_by_jason_identity=lambda **kw:bindings.get(kw['jason_identity_id'])),
        workflow_configuration=source)
    calls=[]
    class Transport:
        def send(self,**kwargs):
            calls.append(kwargs)
            return TeamsDeliveryReceipt('real-id',None,kwargs['binding'].jason_identity_id)
    monkeypatch.setattr(sender,'_existing_transport',lambda:Transport())
    sender.send_event(req,event='approval_required',requester_only=True)
    assert len(calls)==1 and calls[0]['binding'].jason_identity_id=='person-tech'
    assert calls[0]['card']['actions']==[]
    sender.send_event(req,event='denied')
    assert [c['binding'].jason_identity_id for c in calls[1:]]==['person-tech','person-lead']


def test_expired_click_does_not_strand_business_request(tmp_path):
    m,svc,store,sender,_=configured_maintenance(tmp_path)
    now=instant('2026-11-23T08:30:00-05:00')
    assert svc.expire_if_due('procapproval-original',now=now)
    assert m.run_once(now=now)['reminded']==1
    assert store.get('s1')['approval_id']!='procapproval-original'
    assert svc.repository.get('procapproval-original').status.value=='expired'
    assert not svc.repository.accepted_decision('procapproval-original')
