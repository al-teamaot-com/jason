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
