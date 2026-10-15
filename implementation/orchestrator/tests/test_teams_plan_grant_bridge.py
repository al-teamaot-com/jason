from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from orchestrator.approval_plan_grants import PlanGrantLedger
from orchestrator.approval_plan_scope import ApprovedPlanScope, ProposedPlanStep
from orchestrator.teams_plan_grant_bridge import ServerOwnedPlanProposal, record_verified_teams_plan_grant

NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)


def objects(tmp_path):
    scope = ApprovedPlanScope('p', 'aot', 'policy', frozenset({'build', 'deploy'}), frozenset({'c1'}), 2, True, NOW + timedelta(hours=1))
    proposal = ServerOwnedPlanProposal('approval-1', 'aot', 'c1', 'requester-1', 'build', 'plan-digest', scope)
    decision = SimpleNamespace(approval_id='approval-1', status='approved', organization_id='aot', client_id='c1', requested_by='requester-1', capability='build', decided_by='approver-1')
    result = SimpleNamespace(accepted_approval=decision, resumed_request=SimpleNamespace(authority_context_id='ctx-1'))
    return PlanGrantLedger(tmp_path / 'decisions.sqlite3'), proposal, result


def test_authenticated_flow_receipt_persists_for_multiple_steps(tmp_path):
    ledger, proposal, result = objects(tmp_path)
    record_verified_teams_plan_grant(result=result, proposal=proposal, ledger=ledger, decided_at=NOW)
    for name in ('build', 'deploy'):
        ledger.require_grant(ProposedPlanStep('p', 'aot', 'policy', name, 'c1', 1, name == 'deploy'), plan_fingerprint='plan-digest', now=NOW)


@pytest.mark.parametrize('changed', ['approval_id', 'organization_id', 'client_id', 'requested_by', 'capability', 'status'])
def test_mismatched_verified_result_cannot_grant(tmp_path, changed):
    ledger, proposal, result = objects(tmp_path)
    values = vars(result.accepted_approval).copy()
    values[changed] = 'denied' if changed == 'status' else 'different'
    result.accepted_approval = SimpleNamespace(**values)
    with pytest.raises(PermissionError):
        record_verified_teams_plan_grant(result=result, proposal=proposal, ledger=ledger, decided_at=NOW)


def test_missing_fresh_execution_authority_cannot_grant(tmp_path):
    ledger, proposal, result = objects(tmp_path)
    result.resumed_request = None
    with pytest.raises(PermissionError):
        record_verified_teams_plan_grant(result=result, proposal=proposal, ledger=ledger, decided_at=NOW)
