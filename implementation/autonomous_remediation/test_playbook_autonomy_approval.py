from datetime import datetime, timedelta, timezone

import pytest

from .playbook_autonomy_approval import SQLitePlaybookAutonomyApprovalStore


def test_exact_version_and_capability_are_required(tmp_path):
    store=SQLitePlaybookAutonomyApprovalStore(tmp_path/'a.sqlite3')
    record=store.new(playbook_id='pb',playbook_version='1.0',policy_id='policy',allowed_capabilities=['service.ticket.update'],approved_by='person-al')
    store.put(record)
    assert store.find_approved(playbook_id='pb',playbook_version='1.0',policy_id='policy',capability='service.ticket.update') is not None
    assert store.find_approved(playbook_id='pb',playbook_version='1.1',policy_id='policy',capability='service.ticket.update') is None
    assert store.find_approved(playbook_id='pb',playbook_version='1.0',policy_id='policy',capability='automation.component.execute') is None
    store.close()


def test_source_flag_alone_has_no_durable_approval(tmp_path):
    store=SQLitePlaybookAutonomyApprovalStore(tmp_path/'a.sqlite3')
    assert store.find_approved(playbook_id='pb',playbook_version='1.0',policy_id='policy',capability='service.ticket.update') is None
    store.close()


def test_expired_and_revoked_approvals_do_not_authorize(tmp_path):
    store=SQLitePlaybookAutonomyApprovalStore(tmp_path/'a.sqlite3')
    expired=store.new(playbook_id='pb',playbook_version='1.0',policy_id='p1',allowed_capabilities=['x.y.z'],approved_by='person-al',expires_at=datetime.now(timezone.utc)-timedelta(seconds=1))
    store.put(expired)
    assert store.find_approved(playbook_id='pb',playbook_version='1.0',policy_id='p1',capability='x.y.z') is None
    active=store.new(playbook_id='pb',playbook_version='1.0',policy_id='p2',allowed_capabilities=['x.y.z'],approved_by='person-al')
    store.put(active); store.revoke(active.approval_id,revoked_by='person-al')
    assert store.find_approved(playbook_id='pb',playbook_version='1.0',policy_id='p2',capability='x.y.z') is None
    store.close()


def test_approval_id_scope_is_immutable(tmp_path):
    store=SQLitePlaybookAutonomyApprovalStore(tmp_path/'a.sqlite3')
    record=store.new(playbook_id='pb',playbook_version='1.0',policy_id='p',allowed_capabilities=['x.y.z'],approved_by='person-al')
    store.put(record)
    from dataclasses import replace
    with pytest.raises(ValueError):
        store.put(replace(record, playbook_version='2.0'))
    store.close()
