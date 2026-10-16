from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import sqlite3
import json
import pytest
from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from orchestrator.approval_plan_scope import ApprovedPlanScope
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from orchestrator.teams_plan_grant_bridge import ServerOwnedPlanProposal
from orchestrator.teams_plan_request_repository import PlanRequestRepository, plan_fingerprint

NOW = datetime(2026, 10, 16, tzinfo=timezone.utc)


def fixture(tmp_path, *, retention=True):
    request = OrchestrationRequest('execution', 'correlation', 'requester', 'org', 'test.read', None,
        'observe', OrchestrationMode.EXECUTE, False, False, 'low',
        DataHandlingPolicy('internal', False, retention_allowed=retention), ExecutionBudget(Decimal('0')),
        arguments={'resource_id':'known-test-device'}, client_id='client')
    scope = ApprovedPlanScope('plan', 'org', 'policy-v1', frozenset({'test.read'}),
        frozenset({'client'}), 0, False, NOW+timedelta(minutes=30))
    repo = PlanRequestRepository(tmp_path/'plans.db', current_policy_digest='policy-v1')
    return repo, request, scope


def proposal(request, scope):
    return ServerOwnedPlanProposal('planapproval-test', 'org', 'client', 'requester', 'test.read',
                                   plan_fingerprint((request,), scope), scope)


def test_request_roundtrip_binds_material_and_discards_old_execution_context(tmp_path):
    repo, request, scope = fixture(tmp_path)
    request = replace(request, authority_allowed=True, authority_context_id='expired-context', approval_present=True)
    plan = proposal(request, scope)
    repo.store(plan, (request,), now=NOW)
    restored = repo.require(plan.approval_id)
    assert restored.arguments == request.arguments
    assert restored.budget == request.budget
    assert restored.authority_context_id is None and restored.authority_allowed is False
    assert restored.approval_present is False
    repo.verify_proposal(plan)


def test_retention_without_explicit_policy_rejected(tmp_path):
    repo, request, scope = fixture(tmp_path, retention=False)
    with pytest.raises(PermissionError, match='retention'):
        proposal(request, scope)


@pytest.mark.parametrize('arguments', [ {'password':'not-a-real-password'}, {'nested':{'access_token':'secret'}}, {'header':'Bearer not-a-real-token'} ])
def test_credential_bearing_material_never_persisted(tmp_path, arguments):
    repo, request, scope = fixture(tmp_path)
    with pytest.raises(ValueError, match='credential'):
        proposal(replace(request, arguments=arguments), scope)


def test_tampered_target_and_policy_drift_rejected(tmp_path):
    repo, request, scope = fixture(tmp_path)
    plan = proposal(request, scope)
    repo.store(plan, (request,), now=NOW)
    with sqlite3.connect(repo.path) as db:
        payload = json.loads(db.execute('SELECT material_json FROM universal_plan_requests').fetchone()[0])
        payload['requests'][0]['arguments']['resource_id'] = 'different-device'
        db.execute('UPDATE universal_plan_requests SET material_json=?', (json.dumps(payload),))
    with pytest.raises(PermissionError, match='changed'):
        repo.verify_proposal(plan)
    changed = PlanRequestRepository(repo.path, current_policy_digest='policy-v2')
    with pytest.raises(PermissionError, match='policy'):
        changed.require(plan.approval_id)


def test_plan_cannot_smuggle_extra_capabilities(tmp_path):
    repo, request, scope = fixture(tmp_path)
    scope = replace(scope, allowed_capabilities=frozenset({'test.read','production.release'}))
    plan = proposal(request, scope)
    with pytest.raises(PermissionError, match='exactly'):
        repo.store(plan, (request,), now=NOW)


def test_multi_step_manifest_has_one_bound_fingerprint(tmp_path):
    repo, request, scope = fixture(tmp_path)
    second = replace(request, execution_id='execution-verify', capability_name='test.verify')
    scope = replace(scope, allowed_capabilities=frozenset({'test.read','test.verify'}))
    plan = replace(proposal(request, scope), plan_fingerprint=plan_fingerprint((request,second), scope))
    repo.store(plan,(request,second),now=NOW)
    assert len(repo.steps(plan.approval_id)) == 2
    repo.verify_proposal(plan)
    with pytest.raises(sqlite3.IntegrityError):
        repo.store(plan,(request,second),now=NOW)


def test_policy_is_refreshed_after_runtime_construction(tmp_path):
    repo, request, scope = fixture(tmp_path)
    policy = ['policy-v1']
    repo = PlanRequestRepository(repo.path,current_policy_digest=lambda:policy[0])
    plan = proposal(request,scope)
    repo.store(plan,(request,),now=NOW)
    policy[0] = 'policy-v2'
    with pytest.raises(PermissionError,match='policy'):
        repo.verify_proposal(plan)
