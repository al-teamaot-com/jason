"""Scope gate tests: one approved plan can cover many unchanged steps."""
from datetime import datetime, timedelta, timezone
from dataclasses import replace

import pytest

from orchestrator.approval_plan_scope import ApprovedPlanScope, ProposedPlanStep, require_plan_scope

NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)


def fixture():
    scope = ApprovedPlanScope('plan-1', 'aot', 'policy-v1', frozenset({'build', 'test', 'deploy'}), frozenset({'client-1'}), 2, True, NOW + timedelta(days=1))
    step = ProposedPlanStep('plan-1', 'aot', 'policy-v1', 'build', 'client-1', 1, False)
    return scope, step


def test_one_plan_multiple_steps():
    scope, step = fixture()
    for capability, production in [('build', False), ('test', False), ('deploy', True)]:
        require_plan_scope(scope, replace(step, capability=capability, production=production), now=NOW)


@pytest.mark.parametrize('change', [
    {'plan_id': 'other'}, {'organization_id': 'other'}, {'policy_digest': 'new'},
    {'capability': 'shell'}, {'client_id': 'foreign'}, {'risk': 3}, {'risk': -1},
])
def test_scope_drift_rejected(change):
    scope, step = fixture()
    with pytest.raises(PermissionError):
        require_plan_scope(scope, replace(step, **change), now=NOW)


def test_expired_and_unapproved_production_rejected():
    scope, step = fixture()
    with pytest.raises(PermissionError):
        require_plan_scope(scope, step, now=scope.expires_at)
    with pytest.raises(PermissionError):
        require_plan_scope(replace(scope, production_allowed=False), replace(step, production=True), now=NOW)
