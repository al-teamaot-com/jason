from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from orchestrator.approval_plan_grants import PlanGrantLedger, VerifiedPlanDecision
from orchestrator.approval_plan_scope import ApprovedPlanScope, ProposedPlanStep

NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)


def make_objects(tmp_path):
    ledger = PlanGrantLedger(tmp_path / 'grants.db')
    scope = ApprovedPlanScope('p', 'tenant-a', 'policy-a', frozenset({'build', 'deploy'}), frozenset({'c1'}), 2, True, NOW + timedelta(days=1))
    decision = VerifiedPlanDecision('approval-1', 'principal-1', True, True, True, 'plan-digest-1', NOW)
    step = ProposedPlanStep('p', 'tenant-a', 'policy-a', 'build', 'c1', 1, False)
    return ledger, scope, decision, step


def test_persist_and_reuse_bounded_plan(tmp_path):
    ledger, scope, decision, step = make_objects(tmp_path)
    ledger.record(scope, decision)
    reopened = PlanGrantLedger(tmp_path / 'grants.db')
    reopened.require_grant(step, plan_fingerprint='plan-digest-1', now=NOW)
    reopened.require_grant(replace(step, capability='deploy', production=True), plan_fingerprint='plan-digest-1', now=NOW)
    with pytest.raises(sqlite3.IntegrityError):
        reopened.record(scope, decision)


import sqlite3


@pytest.mark.parametrize('change', ['authenticated', 'authorized', 'approved'])
def test_unverified_decisions_fail(tmp_path, change):
    ledger, scope, decision, _ = make_objects(tmp_path)
    with pytest.raises(PermissionError):
        ledger.record(scope, replace(decision, **{change: False}))


def test_changed_plan_and_tenant_fail(tmp_path):
    ledger, scope, decision, step = make_objects(tmp_path)
    ledger.record(scope, decision)
    with pytest.raises(PermissionError):
        ledger.require_grant(step, plan_fingerprint='altered', now=NOW)
    with pytest.raises(PermissionError):
        ledger.require_grant(replace(step, organization_id='other'), plan_fingerprint='plan-digest-1', now=NOW)
    with pytest.raises(PermissionError):
        ledger.require_grant(step, plan_fingerprint='plan-digest-1', now=scope.expires_at)


def test_revocation_survives_restart(tmp_path):
    ledger, scope, decision, step = make_objects(tmp_path)
    ledger.record(scope, decision)
    ledger.revoke(scope.plan_id, at=NOW, reason='owner cancellation')
    with pytest.raises(PermissionError, match='revoked'):
        PlanGrantLedger(tmp_path / 'grants.db').require_grant(step, plan_fingerprint='plan-digest-1', now=NOW)
    with pytest.raises(sqlite3.IntegrityError):
        ledger.revoke(scope.plan_id, at=NOW, reason='replay')


def test_client_scope_cannot_be_bypassed_with_null(tmp_path):
    ledger, scope, decision, step = make_objects(tmp_path)
    ledger.record(scope, decision)
    with pytest.raises(PermissionError, match='client'):
        ledger.require_grant(replace(step, client_id=None), plan_fingerprint='plan-digest-1', now=NOW)


def test_scope_mutation_cannot_change_persisted_record(tmp_path):
    ledger, scope, decision, step = make_objects(tmp_path)
    ledger.record(scope, decision)
    with pytest.raises(sqlite3.IntegrityError):
        ledger.record(replace(scope, max_risk=999), replace(decision, approval_id='approval-2'))
    with pytest.raises(PermissionError):
        ledger.require_grant(replace(step, risk=999), plan_fingerprint='plan-digest-1', now=NOW)


def test_reused_approval_identifier_cannot_authorize_second_plan(tmp_path):
    ledger, scope, decision, step = make_objects(tmp_path)
    ledger.record(scope, decision)
    with pytest.raises(sqlite3.IntegrityError):
        ledger.record(replace(scope, plan_id='p2'), decision)


def test_missing_client_is_permitted_only_for_org_scoped_plan(tmp_path):
    ledger, scope, decision, step = make_objects(tmp_path)
    org_scope = replace(scope, allowed_clients=frozenset())
    ledger.record(org_scope, decision)
    ledger.require_grant(replace(step, client_id=None), plan_fingerprint='plan-digest-1', now=NOW)
    with pytest.raises(PermissionError):
        ledger.require_grant(step, plan_fingerprint='plan-digest-1', now=NOW)


def test_exact_publication_readback_does_not_accept_another_human_vote(tmp_path):
    ledger, scope, decision, _ = make_objects(tmp_path)
    ledger.record(scope, decision)
    ledger.require_matching_decision(scope, decision)
    with pytest.raises(sqlite3.IntegrityError):
        ledger.record(scope, decision)


@pytest.mark.parametrize('changes', [
    {'approver_identity_id': 'another-actor'},
    {'approval_id': 'another-approval'},
    {'plan_fingerprint': 'another-fingerprint'},
    {'decided_at': NOW + timedelta(seconds=1)},
])
def test_publication_recovery_rejects_changed_decision(tmp_path, changes):
    ledger, scope, decision, _ = make_objects(tmp_path)
    ledger.record(scope, decision)
    with pytest.raises(PermissionError):
        ledger.require_matching_decision(scope, replace(decision, **changes))


@pytest.mark.parametrize('changes', [
    {'plan_id': 'another-plan'},
    {'organization_id': 'another-org'},
    {'policy_digest': 'another-policy'},
    {'allowed_capabilities': frozenset({'build'})},
    {'allowed_clients': frozenset({'another-client'})},
    {'max_risk': 1},
    {'production_allowed': False},
    {'expires_at': NOW + timedelta(hours=1)},
])
def test_publication_recovery_rejects_changed_scope(tmp_path, changes):
    ledger, scope, decision, _ = make_objects(tmp_path)
    ledger.record(scope, decision)
    with pytest.raises(PermissionError):
        ledger.require_matching_decision(replace(scope, **changes), decision)


def test_publication_recovery_never_restores_revoked_or_unverified_decision(tmp_path):
    ledger, scope, decision, _ = make_objects(tmp_path)
    with pytest.raises(PermissionError):
        ledger.require_matching_decision(scope, decision)
    ledger.record(scope, decision)
    with pytest.raises(PermissionError):
        ledger.require_matching_decision(scope, replace(decision, authenticated=False))
    ledger.revoke(scope.plan_id, at=NOW, reason='owner cancellation')
    with pytest.raises(PermissionError):
        ledger.require_matching_decision(scope, decision)
