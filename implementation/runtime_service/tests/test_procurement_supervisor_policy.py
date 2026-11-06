from decimal import Decimal
import pytest
from jason_runtime.procurement_supervisor_policy import (
    SupervisorPolicyError, SupervisorSpendingPolicy, money,
)


def rules():
    return {
        'schema_version':'1.0', 'policy_version':'aot-test-v1',
        'role_memberships':{'procurement-manager':['person-tech2']},
        'rules':[
            {'requester_id':'person-tech1', 'role':None,'purchase_type':'it',
             'maximum_without_approval':'150.00',
             'designated_supervisor_ids':['person-supervisor1'],
             'escalation_owner_ids':['person-owner1'],'ttl_minutes':60},
            {'requester_id':None, 'role':'procurement-manager','purchase_type':'copy_print',
             'maximum_without_approval':'550.00',
             'designated_supervisor_ids':['person-supervisor2'],
             'escalation_owner_ids':['person-owner1'],'ttl_minutes':180},
        ]
    }


def decide(*,amount='200.00',udf='300.00',who='person-tech1',ptype='it',roles=()):
    return SupervisorSpendingPolicy.from_mapping(rules()).decide(
        requester_id=who,authoritative_roles=roles,purchase_type=ptype,
        amount=Decimal(amount),autotask_udf_limit=Decimal(udf))


def test_spending_threshold_uses_stricter_udf_and_rule():
    approved=decide(amount='150.00')
    assert not approved.requires_approval and approved.approver_ids==()
    over=decide(amount='150.01')
    assert over.requires_approval and over.threshold==Decimal('150.00')
    assert over.approver_ids==('person-supervisor1',)
    assert over.fallback_approver_ids==('person-owner1',)
    assert over.ttl_minutes==60
    reduced=decide(amount='101.00',udf='100.00')
    assert reduced.requires_approval and reduced.threshold==Decimal('100.00')


def test_staff_specific_rule_vs_authoritative_role_and_contact_udf_cap():
    role=decide(amount='550',udf='600',who='person-tech2',ptype='copy_print',roles=('procurement-manager',))
    assert not role.requires_approval
    role=decide(amount='550.01',udf='600',who='person-tech2',ptype='copy_print',roles=('procurement-manager',))
    assert role.approver_ids==('person-supervisor2',)
    assert decide(amount='301',udf='300',who='person-tech2',ptype='copy_print',roles=('procurement-manager',)).requires_approval
    with pytest.raises(SupervisorPolicyError,match='missing or ambiguous'):
        decide(amount='1',who='person-tech2',ptype='copy_print',roles=())


def test_untrusted_role_string_cannot_be_used_without_authoritative_resolver():
    with pytest.raises(SupervisorPolicyError,match='missing or ambiguous'):
        decide(who='person-tech2',ptype='copy_print',roles=())


def test_approval_requires_distinct_requester_and_reachable_backup():
    p=rules();p['rules'][0]['requester_id']='person-supervisor1'
    with pytest.raises(SupervisorPolicyError,match='requester is the only'):
        SupervisorSpendingPolicy.from_mapping(p).decide(
            requester_id='person-supervisor1',authoritative_roles=(),
            purchase_type='it',amount=Decimal('500'),autotask_udf_limit=Decimal('100'))


def test_change_of_spending_policy_invalidates_old_decisions():
    first=SupervisorSpendingPolicy.from_mapping(rules())
    old=first.decide(requester_id='person-tech1',authoritative_roles=(),purchase_type='it',amount=Decimal('200'),autotask_udf_limit=Decimal('300'))
    revised=rules();revised['rules'][0]['maximum_without_approval']='160.00'
    second=SupervisorSpendingPolicy.from_mapping(revised)
    with pytest.raises(PermissionError,match='policy changed'):
        second.revalidate(digest=old.policy_digest)


def test_duplicate_or_ambiguous_rules_fail_closed():
    p=rules();p['rules'].append(dict(p['rules'][0]))
    with pytest.raises(SupervisorPolicyError,match='ambiguous'):
        SupervisorSpendingPolicy.from_mapping(p)


def test_over_precise_negative_nonfinite_monies_fail_closed():
    for amount in ('-1','1.001','NaN','Infinity',True,float('inf')):
        with pytest.raises(SupervisorPolicyError):money(amount)


def test_unreviewed_schema_fields_fail_closed():
    p=rules();p['allow_purchase_without_card']=True
    with pytest.raises(SupervisorPolicyError,match='reviewed'):
        SupervisorSpendingPolicy.from_mapping(p)


def test_no_missing_supervisor_or_owner():
    p=rules();p['rules'][0]['designated_supervisor_ids']=[]
    with pytest.raises(SupervisorPolicyError,match='explicit supervisor'):
        SupervisorSpendingPolicy.from_mapping(p)


def test_two_different_authorized_roles_ambiguous_for_same_purchase_type():
    p=rules();p['rules'].append(dict(p['rules'][1],role='senior-technician'))
    pol=SupervisorSpendingPolicy.from_mapping(p)
    with pytest.raises(SupervisorPolicyError,match='ambiguous'):
        pol.decide(requester_id='person-tech2',authoritative_roles=('procurement-manager','senior-technician'),purchase_type='copy_print',amount=Decimal('600'),autotask_udf_limit=Decimal('700'))


def test_reviewed_role_memberships_not_teams_claims():
    pol=SupervisorSpendingPolicy.from_mapping(rules())
    assert pol.roles_for('person-tech2')==('procurement-manager',)
    assert pol.roles_for('person-unknown')==()
    choice=pol.decide_from_reviewed_identities(requester_id='person-tech2',
        purchase_type='copy_print', amount=Decimal('550.01'),
        autotask_contact_udf_limit=Decimal('600.00'))
    assert choice.requires_approval and choice.approver_ids==('person-supervisor2',)
    with pytest.raises(SupervisorPolicyError,match='missing or ambiguous'):
        pol.decide_from_reviewed_identities(requester_id='person-unknown',
            purchase_type='copy_print', amount=Decimal('550.01'),
            autotask_contact_udf_limit=Decimal('600.00'))
