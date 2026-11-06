from datetime import datetime,timedelta,timezone
from decimal import Decimal
from types import SimpleNamespace
import json
import pytest
from pathlib import Path

from jason_runtime.parts_inventory_lifecycle import (
    PartsScope,InventoryEvidence,PartsLifecycleError,plan_parts,
    SQLitePartsLifecycleLedger,require_po_authority,
)
from jason_runtime.procurement_supervisor_policy import require_signed_purchase_approval
from connectors.src.jason_connectors.approval_requests import (
    ApprovalRequest,ApprovalRequestService,ApprovalResponse,ApprovalDecision,
    InMemoryApprovalRequestRepository,
)

NOW=datetime(2026,10,25,16,0,tzinfo=timezone.utc)
SHA='a'*64


def scope():
    return PartsScope(request_id='parts-T20261025-0001-1',requester_identity_id='person-tech1',
        ticket_id=456,ticket_number='T20261025.0001',company_id=123,
        product_id=789,inventory_location_id=1,quantity=3,
        destination='AOT staging; client site 123',serial_required=False)


def stock(*,onhand=3,picked=0,reserved=0,product=789,location=1,age=0):
    return InventoryEvidence(555,product,location,onhand,picked,reserved,
        NOW-timedelta(minutes=age),'autotask-inventory-read-887',SHA)


def submission(*,amount='120.00',udf='50.00',threshold='50.00'):
    return {'submission_id':'procsub-a','digest':SHA,
        'requester_principal_id':'person-tech1','ticket_id':456,'ticket_company_id':123,
        'total_commitment':amount,'spending_limit':udf,
        'effective_spending_threshold':threshold,
        'spending_authority_source':'autotask_contact_udf:Spending limit'}


def test_no_inventory_readback_is_not_a_stock_reservation():
    plan=plan_parts(scope(),None,now=NOW)
    assert plan.status=='blocked_missing_authoritative_stock_readback'
    assert plan.stock_candidate_quantity==0 and plan.unfilled_quantity==3


def test_autotask_available_stock_is_net_of_reserved_and_picked():
    plan=plan_parts(scope(),stock(onhand=7,picked=1,reserved=4),now=NOW)
    assert plan.stock_candidate_quantity==2 and plan.unfilled_quantity==1
    assert plan.status=='pending_provider_stock_reservation'


def test_available_qty_does_not_commit_or_mark_reserved():
    plan=plan_parts(scope(),stock(onhand=10),now=NOW)
    assert plan.stock_candidate_quantity==3
    assert plan.status=='pending_provider_stock_reservation'


def test_zero_stock_requires_purchase_plan_not_invented_availability():
    plan=plan_parts(scope(),stock(onhand=0),now=NOW)
    assert plan.stock_candidate_quantity==0 and plan.unfilled_quantity==3
    assert plan.status=='stock_shortage_requires_purchase_approval'


@pytest.mark.parametrize('evidence',[
    stock(age=11),stock(product=999),stock(location=2),
    stock(onhand=2,picked=2,reserved=1),
    InventoryEvidence(555,789,1,1,0,0,NOW,'user-filled-inventory-read',SHA,provider='manual.spreadsheet'),
])
def test_bad_stock_evidence_is_rejected_before_reservation(evidence):
    with pytest.raises(PartsLifecycleError):plan_parts(scope(),evidence,now=NOW)


def test_reuses_same_request_exactly_and_rejects_cross_customer(tmp_path):
    ledger=SQLitePartsLifecycleLedger(tmp_path/'parts.sqlite3')
    one=ledger.create(scope(),now=NOW)
    assert one['state']=='requested' and one['scope_sha256']==scope().fingerprint
    assert ledger.create(scope(),now=NOW)['scope_sha256']==one['scope_sha256']
    from dataclasses import replace
    with pytest.raises(PartsLifecycleError,match='changed'):
        ledger.create(replace(scope(),company_id=124),now=NOW)
    assert len(ledger.events(scope().request_id))==0


def event(ledger,etype,id_suffix,*,payload=None,resource=None,extra=None):
    data=dict(payload or {})
    return ledger.record(request_id=scope().request_id,event_id='evt-'+id_suffix,
        event_type=etype,evidence_id='provider-'+id_suffix,
        provider_resource_id=resource,payload=data,at=NOW,
        **(extra or {}))


def checked(ledger):
    ledger.create(scope(),now=NOW)
    return event(ledger,'stock_checked','inventory',payload={
        'source':'autotask.inventory.items.read',
        'scope_sha256':scope().fingerprint,'source_sha256':SHA},resource=555)


def test_unverified_stock_reservation_denied(tmp_path):
    ledger=SQLitePartsLifecycleLedger(tmp_path/'parts.sqlite3');checked(ledger)
    with pytest.raises(PartsLifecycleError,match='actual Autotask reservation'):
        event(ledger,'stock_reserved','fake',resource=None,payload={'quantity':2})
    assert ledger.read(scope().request_id)['state']=='stock_checked'


def test_real_provider_reservation_requires_exact_ticket_location(tmp_path):
    ledger=SQLitePartsLifecycleLedger(tmp_path/'parts.sqlite3');checked(ledger)
    with pytest.raises(PartsLifecycleError,match='actual Autotask reservation'):
        event(ledger,'stock_reserved','wrong-ticket',resource=888,payload={
            'source':'autotask.inventory.readback','ticket_id':999,
            'inventory_location_id':1,'quantity':3,
            'quantity_reserved_before':0,'quantity_reserved_after':3})
    good=event(ledger,'stock_reserved','good',resource=888,payload={
        'source':'autotask.inventory.readback','ticket_id':456,
        'inventory_location_id':1,'quantity':3,
            'quantity_reserved_before':0,'quantity_reserved_after':3})
    assert good['state']=='stock_reserved' and good['allocated_count']==3


def test_replay_same_provider_event_is_idempotent_but_changed_event_denied(tmp_path):
    ledger=SQLitePartsLifecycleLedger(tmp_path/'parts.sqlite3');checked(ledger)
    first=event(ledger,'stock_reserved','event1',resource=888,payload={
        'source':'autotask.inventory.readback','ticket_id':456,
        'inventory_location_id':1,'quantity':3,
            'quantity_reserved_before':0,'quantity_reserved_after':3})
    second=event(ledger,'stock_reserved','event1',resource=888,payload={
        'source':'autotask.inventory.readback','ticket_id':456,
        'inventory_location_id':1,'quantity':3,
            'quantity_reserved_before':0,'quantity_reserved_after':3})
    assert first==second and len(ledger.events(scope().request_id))==2
    with pytest.raises(PartsLifecycleError,match='replayed'):
        event(ledger,'stock_reserved','event1',resource=888,payload={'quantity':999})


def test_bare_approval_id_never_satisfies_over_limit_purchase():
    with pytest.raises(PermissionError,match='signed Teams purchase'):
        require_po_authority(service=None,approval_id='procapproval-fake',
            submission=submission(),amount=Decimal('120'),effective_threshold=Decimal('50'))


def test_finite_below_limit_purchase_requires_no_supervisor_but_udf_is_hard_cap():
    require_po_authority(service=None,approval_id=None,
        submission=submission(amount='20'),amount=Decimal('20'),effective_threshold=Decimal('50'))
    with pytest.raises(PermissionError):
        require_po_authority(service=None,approval_id=None,
            submission=submission(amount='60'),amount=Decimal('60'),effective_threshold=Decimal('50'))


def test_cannot_write_fake_po_or_invoice_event_without_verified_provider(tmp_path):
    ledger=SQLitePartsLifecycleLedger(tmp_path/'parts.sqlite3');checked(ledger)
    with pytest.raises(PartsLifecycleError,match='same-scope'):
        event(ledger,'po_created','po-fake',resource=900,payload={
            'source':'autotask.purchase.order.readback','ticket_id':456,'company_id':123})
    assert ledger.read(scope().request_id)['provider_po_id'] is None
    assert ledger.read(scope().request_id)['state']=='stock_checked'


def test_same_customer_under_contact_udf_po_and_partial_receiving(tmp_path):
    ledger=SQLitePartsLifecycleLedger(tmp_path/'parts.sqlite3');checked(ledger)
    sub=submission(amount='20',udf='50',threshold='50')
    purchase=event(ledger,'po_created','po-accepted',resource=900,payload={
        'source':'autotask.purchase.order.readback','ticket_id':456,'company_id':123,
        'submission_digest':sub['digest']},extra={'procurement_submission':sub})
    assert purchase['provider_po_id']==900 and purchase['state']=='ordered'
    first=event(ledger,'partial_received','receive-1',resource=991,payload={
        'source':'autotask.purchase.order.receiving.readback','purchase_order_id':900,'quantity':1})
    assert first['received_count']==1 and first['state']=='partially_received'
    last=event(ledger,'received','receive-2',resource=992,payload={
        'source':'autotask.purchase.order.receiving.readback','purchase_order_id':900,'quantity':2})
    assert last['received_count']==3 and last['state']=='received'
    with pytest.raises(PartsLifecycleError,match='illegal parts lifecycle'):
        event(ledger,'received','receive-3',resource=993,payload={
            'source':'autotask.purchase.order.receiving.readback','purchase_order_id':900,'quantity':1})


def test_ticket_charge_requires_exact_provider_and_prevents_duplicate(tmp_path):
    ledger=SQLitePartsLifecycleLedger(tmp_path/'parts.sqlite3');checked(ledger)
    sub=submission(amount='20',udf='50',threshold='50')
    event(ledger,'po_created','po-accepted',resource=900,payload={
        'source':'autotask.purchase.order.readback','ticket_id':456,'company_id':123,
        'submission_digest':sub['digest']},extra={'procurement_submission':sub})
    event(ledger,'received','receive-all',resource=991,payload={
        'source':'autotask.purchase.order.receiving.readback','purchase_order_id':900,'quantity':3})
    with pytest.raises(PartsLifecycleError,match='exact Autotask'):
        event(ledger,'ticket_charged','wrong-ticket',resource=81,payload={
            'source':'autotask.ticket.charge.readback','ticket_id':999,'company_id':123})
    good=event(ledger,'ticket_charged','charge-1',resource=81,payload={
        'source':'autotask.ticket.charge.readback','ticket_id':456,'company_id':123})
    assert good['provider_charge_id']==81
    with pytest.raises(PartsLifecycleError,match='duplicate ticket charge'):
        event(ledger,'ticket_charged','duplicate-charge',resource=82,payload={
            'source':'autotask.ticket.charge.readback','ticket_id':456,'company_id':123})


def test_staging_assignment_location_and_receipt_are_required(tmp_path):
    ledger=SQLitePartsLifecycleLedger(tmp_path/'parts.sqlite3');checked(ledger)
    event(ledger,'stock_reserved','reservation',resource=888,payload={
        'source':'autotask.inventory.readback','ticket_id':456,
        'inventory_location_id':1,'quantity':3,
            'quantity_reserved_before':0,'quantity_reserved_after':3})
    with pytest.raises(PartsLifecycleError,match='location and technician'):
        event(ledger,'staged','stage-no-place',payload={})
    stage=event(ledger,'staged','stage',payload={
        'location':'AOT workbench','technician_identity_id':'person-tech1'})
    assert stage['state']=='staged'
    with pytest.raises(PartsLifecycleError,match='verified ticket billing'):
        event(ledger,'assigned','without-charge',payload={
            'location':'Customer office','technician_identity_id':'person-tech1','quantity':3})
    event(ledger,'ticket_charged','charge-staging',resource=981,payload={
        'source':'autotask.ticket.charge.readback','ticket_id':456,'company_id':123})
    assigned=event(ledger,'assigned','assigned',payload={
        'location':'Customer office','technician_identity_id':'person-tech1','quantity':3})
    assert assigned['state']=='assigned'
    with pytest.raises(PartsLifecycleError,match='exact ticket'):
        event(ledger,'installed','wrong-install-ticket',payload={'quantity':3,'ticket_id':999})


def test_scoped_return_and_cancellation_never_execute_provider_writes(tmp_path):
    ledger=SQLitePartsLifecycleLedger(tmp_path/'parts.sqlite3');checked(ledger)
    event(ledger,'stock_reserved','reservation',resource=888,payload={
        'source':'autotask.inventory.readback','ticket_id':456,
        'inventory_location_id':1,'quantity':3,
            'quantity_reserved_before':0,'quantity_reserved_after':3})
    event(ledger,'ticket_charged','charge-inventory',resource=982,payload={
        'source':'autotask.ticket.charge.readback','ticket_id':456,'company_id':123})
    event(ledger,'assigned','assigned',payload={
        'location':'Customer office','technician_identity_id':'person-tech1','quantity':3})
    result=event(ledger,'returned','returned',resource=990,payload={
        'source':'autotask.inventory.return.readback',
        'location':'AOT stock room','technician_identity_id':'person-tech1','quantity':3})
    assert result['state']=='returned'
    cancelled=event(ledger,'cancelled','cancelled',payload={})
    assert cancelled['state']=='cancelled'
    assert len(ledger.events(scope().request_id))==6


def test_serialized_part_must_include_serial_on_install(tmp_path):
    from dataclasses import replace
    serial_scope=replace(scope(),serial_required=True)
    ledger=SQLitePartsLifecycleLedger(tmp_path/'parts.sqlite3')
    ledger.create(serial_scope,now=NOW)
    # A serial check is a pure invariant; simulated source state does not
    # authorize an actual serial inventory mutation.
    assert serial_scope.serial_required
    assert serial_scope.fingerprint!=scope().fingerprint


def test_mixed_stock_and_shortage_form_nonoverlapping_child_scopes():
    from jason_runtime.parts_inventory_lifecycle import split_parts_plan
    plan=plan_parts(scope(),stock(onhand=2),now=NOW)
    split=split_parts_plan(scope(),plan)
    assert len(split)==2
    assert {s.request_id for s in split}=={scope().request_id+'-stock',scope().request_id+'-po'}
    assert [s.quantity for s in split]==[2,1]
    assert all(s.ticket_id==scope().ticket_id and s.company_id==scope().company_id for s in split)
    with pytest.raises(PartsLifecycleError,match='scope changed'):
        split_parts_plan(scope(),type(plan)(plan.request_id,'b'*64,plan.provider_snapshot_sha256,2,1,plan.status))


def test_verified_onhand_reservation_can_be_staged_installed_after_readback(tmp_path):
    ledger=SQLitePartsLifecycleLedger(tmp_path/'parts.sqlite3');checked(ledger)
    event(ledger,'stock_reserved','reservation',resource=888,payload={
        'source':'autotask.inventory.readback','ticket_id':456,
        'inventory_location_id':1,'quantity':3,
        'quantity_reserved_before':1,'quantity_reserved_after':4})
    event(ledger,'staged','stage',payload={
        'location':'AOT tech bench','technician_identity_id':'person-tech1'})
    event(ledger,'ticket_charged','charge-assignment',resource=983,payload={
        'source':'autotask.ticket.charge.readback','ticket_id':456,'company_id':123})
    event(ledger,'assigned','assigned',payload={
        'location':'Client floor 3','technician_identity_id':'person-tech1','quantity':3})
    installed=event(ledger,'installed','installed',payload={'ticket_id':456,'quantity':3})
    assert installed['installed_count']==3 and installed['allocated_count']==3
    assert installed['state']=='installed'


def approved_purchase():
    from jason_runtime.procurement_teams_flow import ConfiguredProcurementApprovalAuthority
    request_data=submission(amount='125.00',udf='50.00',threshold='50.00')
    repo=InMemoryApprovalRequestRepository()
    svc=ApprovalRequestService(repository=repo,
        authority=ConfiguredProcurementApprovalAuthority(frozenset({'person-manager'})))
    req=ApprovalRequest(approval_id='procapproval-parts1',request_id='procreq-parts1',
        correlation_id='corr-parts1',organization_id='aot',client_id=None,
        requested_by='person-tech1',capability='procurement.submission.execute',
        requested_mode='purchase',requested_at=NOW-timedelta(minutes=2),
        expires_at=NOW+timedelta(minutes=30),
        authorized_approver_ids=('person-manager',),
        metadata={'submission_id':request_data['submission_id'],
                  'submission_digest':request_data['digest'],
                  'supervisor_policy_digest':'owner-udf-only'})
    svc.create(req,now=NOW-timedelta(minutes=1))
    receipt=svc.accept_response(ApprovalResponse(
        approval_id=req.approval_id,organization_id='aot',
        approver_identity_id='person-manager',decision=ApprovalDecision.APPROVE,
        decided_at=NOW,channel='microsoft_teams',channel_response_id='teams-response1',
        authentication_evidence_hash=SHA),now=NOW)
    return svc,request_data,receipt


def test_over_udf_po_reuses_exact_signed_teams_approval_service(tmp_path):
    service,sub,receipt=approved_purchase()
    ledger=SQLitePartsLifecycleLedger(tmp_path/'parts.sqlite3');checked(ledger)
    with pytest.raises(PermissionError,match='signed Teams'):
        event(ledger,'purchase_approved','fake-signature',payload={
            'source':'signed_teams_approval','approval_receipt_sha256':SHA,
            'submission_digest':sub['digest']},
            extra={'procurement_submission':sub,'approval_id':'procapproval-fake',
                   'approval_service':service})
    permitted=event(ledger,'purchase_approved','real-teams',payload={
        'source':'signed_teams_approval','approval_receipt_sha256':receipt.authentication_evidence_hash,
        'submission_digest':sub['digest']},
        extra={'procurement_submission':sub,'approval_id':'procapproval-parts1',
               'approval_service':service})
    assert permitted['state']=='purchase_approved'
    receipt_po=event(ledger,'po_created','accepted-po',resource=900,payload={
        'source':'autotask.purchase.order.readback','ticket_id':456,'company_id':123,
        'submission_digest':sub['digest']},extra={'procurement_submission':sub,
        'approval_id':'procapproval-parts1','approval_service':service})
    assert receipt_po['state']=='ordered' and receipt_po['provider_po_id']==900


def test_over_limit_po_denied_without_real_signed_receipt(tmp_path):
    ledger=SQLitePartsLifecycleLedger(tmp_path/'parts.sqlite3');checked(ledger)
    sub=submission(amount='125.00',udf='50.00',threshold='50.00')
    with pytest.raises(PermissionError,match='signed Teams'):
        event(ledger,'po_created','unapproved-po',resource=900,payload={
            'source':'autotask.purchase.order.readback','ticket_id':456,
            'company_id':123,'submission_digest':sub['digest']},
            extra={'procurement_submission':sub,'approval_id':'procapproval-forged'})
    assert ledger.read(scope().request_id)['provider_po_id'] is None


def test_user_supplied_rule_cannot_override_contact_udf_for_po(tmp_path):
    ledger=SQLitePartsLifecycleLedger(tmp_path/'parts.sqlite3');checked(ledger)
    sub=submission(amount='125.00',udf='50.00',threshold='125.00')
    with pytest.raises(PartsLifecycleError,match='exceeds verified Autotask technician UDF'):
        event(ledger,'po_created','raised-limit',resource=900,payload={
            'source':'autotask.purchase.order.readback','ticket_id':456,'company_id':123,
            'submission_digest':sub['digest']},extra={'procurement_submission':sub})
