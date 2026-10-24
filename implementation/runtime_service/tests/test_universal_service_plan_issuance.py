"""One existing workload -> real approval engine -> isolated provider fixture.

No live authority, Microsoft account, customer ticket or provider is changed.
"""
from dataclasses import replace
from decimal import Decimal
import hashlib
import json

import pytest

from autonomous_remediation.autonomous_principal import AutonomousPrincipal
from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.identity_authority import AuthorityGrant, IdentityRecord, PermissionMode
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest
from test_universal_plan_issuance import with_issuer
from test_universal_teams_approval_runtime import setup, NOW, signed, click


def service_env(tmp_path):
    env = setup(tmp_path)
    env.identities.put(IdentityRecord('worker', 'service', 'org'))
    env.grants.put(AuthorityGrant('service-read', 'worker', 'synthetic.resource.read',
        'org', 'client', PermissionMode.EXECUTE, approval_required=True))
    request = OrchestrationRequest('service-execution', 'service-correlation', 'worker',
        'org', 'synthetic.resource.read', None, 'deterministic',
        OrchestrationMode.EXECUTE, False, False, 'low',
        DataHandlingPolicy('internal', False, retention_allowed=True),
        ExecutionBudget(Decimal('0'), maximum_attempts=1),
        arguments={'resource_id': 'controlled-test'}, client_id='client',
        requester_kind='service', permission_mode='observe')
    doc = json.loads(env.policy.read_text())
    org = doc['organizations']['org']
    org['service_requesters'] = {'worker': {'microsoft_tenant_id': 'tenant', 'maximum_plan_steps': 1}}
    org['request_allowlist'] = [{
        'principal_id': 'worker', 'capability': request.capability_name,
        'permission_mode': request.permission_mode, 'client_id': request.client_id,
        'arguments_sha256': hashlib.sha256(json.dumps(dict(request.arguments),
            sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest(),
    }]
    env.policy.write_text(json.dumps(doc))
    delivery, issuer = with_issuer(env)
    return env, delivery, issuer, request


def issue(issuer, request, principal=None):
    return issuer.submit_service_plan(requests=(request,),
        principal=principal or AutonomousPrincipal('worker', 'org'),
        title='Controlled internal pilot', summary='One exact harmless internal action.',
        production=False, ttl_seconds=1800)


def test_service_is_not_a_fake_human_and_executes_only_after_real_signed_decision(tmp_path):
    env, delivery, issuer, request = service_env(tmp_path)
    result = issue(issuer, request)
    assert result['status'] == 'awaiting_approval' and not env.provider.calls
    pending = delivery.requests[0]
    assert pending.requested_by == 'worker'
    assert pending.metadata['requester_authentication_assurance'] == 'workload_identity'
    assert pending.authorized_approver_ids == ('approver-a', 'approver-b')
    proposal = env.handler.proposals.require(pending.approval_id)
    assert click(env, signed(env, proposal))['plan_status'] == 'queued'
    assert not env.provider.calls
    assert env.handler.plan_runner.tick()
    assert len(env.provider.calls) == 1
    assert env.provider.calls[0].principal_id == 'worker'
    context = issuer.authority.contexts.get_context(env.provider.calls[0].authority_context_id)
    assert context.principal_id == 'worker'
    assert context.authentication_assurance == 'workload_identity'
    assert env.handler.requests.progress(pending.approval_id)['state'] == 'completed'
    with pytest.raises((ValueError, PermissionError)):
        click(env, signed(env, proposal))
    env.handler.plan_runner.tick()
    assert len(env.provider.calls) == 1


def test_service_deny_never_grants_or_executes(tmp_path):
    env, delivery, issuer, request = service_env(tmp_path)
    issue(issuer, request)
    proposal = env.handler.proposals.require('planapproval-issued')
    result = click(env, signed(env, proposal, decision='deny'))
    assert result['approval_status'] == 'denied' and result['executed'] is False
    env.handler.plan_runner.tick()
    assert not env.provider.calls and env.approvals.get('planapproval-issued') is None


@pytest.mark.parametrize('change', [
    {'arguments': {'resource_id': 'wrong-target'}},
    {'capability_name': 'synthetic.other.read'},
    {'client_id': 'other-client'},
    {'principal_id': 'requester-a'},
    {'organization_id': 'other-org'},
    {'permission_mode': 'execute'},
    {'requester_kind': 'human'},
])
def test_service_scope_cannot_drift_or_impersonate_a_human(tmp_path, change):
    env, delivery, issuer, request = service_env(tmp_path)
    with pytest.raises(PermissionError):
        issue(issuer, replace(request, **change))
    assert not delivery.requests and not env.provider.calls


@pytest.mark.parametrize('status,kind', [('disabled', 'service'), ('active', 'human')])
def test_service_must_be_a_live_registered_workload(tmp_path, status, kind):
    env, delivery, issuer, request = service_env(tmp_path)
    env.identities.put(IdentityRecord('worker', kind, 'org', status=status))
    with pytest.raises(PermissionError):
        issue(issuer, request)
    assert not delivery.requests


def test_absent_jkd_grant_cannot_be_replaced_by_config(tmp_path):
    env, delivery, issuer, request = service_env(tmp_path)
    env.grants.revoke('service-read')
    with pytest.raises(PermissionError, match='authority'):
        issue(issuer, request)
    assert not delivery.requests and not env.provider.calls


@pytest.mark.parametrize('field', ['service_requesters', 'request_allowlist'])
def test_service_issuance_is_disabled_without_explicit_narrow_policy(tmp_path, field):
    env, delivery, issuer, request = service_env(tmp_path)
    doc = json.loads(env.policy.read_text()); del doc['organizations']['org'][field]
    env.policy.write_text(json.dumps(doc))
    with pytest.raises(PermissionError):
        issue(issuer, request)
    assert not delivery.requests


def test_human_authentication_label_cannot_authorize_service_issuance(tmp_path):
    env, delivery, issuer, request = service_env(tmp_path)
    with pytest.raises(PermissionError):
        issue(issuer, request, AutonomousPrincipal('worker', 'org', 'botframework-authenticated'))
    assert not delivery.requests


def test_service_plan_cannot_exceed_declared_step_count(tmp_path):
    env, delivery, issuer, request = service_env(tmp_path)
    with pytest.raises(PermissionError):
        issuer.submit_service_plan(requests=(request, replace(request, execution_id='second')),
            principal=AutonomousPrincipal('worker', 'org'), title='bounded', summary='test',
            production=False)
    assert not delivery.requests


def test_current_policy_is_rechecked_before_worker_provider_call(tmp_path):
    env, delivery, issuer, request = service_env(tmp_path)
    issue(issuer, request)
    proposal = env.handler.proposals.require('planapproval-issued')
    click(env, signed(env, proposal))
    doc = json.loads(env.policy.read_text())
    doc['organizations']['org']['request_allowlist'][0]['arguments_sha256'] = '0' * 64
    env.policy.write_text(json.dumps(doc))
    env.handler.plan_runner.tick()
    assert not env.provider.calls
    assert env.handler.requests.progress('planapproval-issued')['state'] == 'blocked'


def test_workload_approval_executes_through_real_central_orchestrator(tmp_path):
    from test_universal_plan_central_orchestrator import real_central
    env, _, _, request = service_env(tmp_path)
    provider, audit = real_central(env, tmp_path)
    delivery, issuer = with_issuer(env)
    issued = issue(issuer, request)
    proposal = env.handler.proposals.require(issued['approval_id'])
    assert click(env, signed(env, proposal))['plan_status'] == 'queued'
    assert not provider.calls
    assert env.handler.plan_runner.tick()
    progress = env.handler.requests.progress(issued['approval_id'])
    assert progress['state'] == 'completed', progress
    assert len(provider.calls) == 1
    executed, plan = provider.calls[0]
    assert executed.principal_id == 'worker'
    assert issuer.authority.contexts.get_context(executed.authority_context_id).authentication_assurance == 'workload_identity'
    assert env.execution_ledger.evidence(executed.approval_id)['state'] == 'succeeded'


def test_service_cannot_route_owner_card_to_a_different_tenant(tmp_path):
    env, delivery, issuer, request = service_env(tmp_path)
    doc=json.loads(env.policy.read_text())
    doc['organizations']['org']['service_requesters']['worker']['microsoft_tenant_id']='other-tenant'
    env.policy.write_text(json.dumps(doc))
    with pytest.raises(PermissionError,match='tenant'):
        issue(issuer,request)
    assert not delivery.requests and not env.provider.calls


def test_allowlist_never_accepts_extra_wildcard_authority_field(tmp_path):
    env, delivery, issuer, request = service_env(tmp_path)
    doc=json.loads(env.policy.read_text())
    doc['organizations']['org']['request_allowlist'][0]['allow_all']=True
    env.policy.write_text(json.dumps(doc))
    with pytest.raises(ValueError,match='rule'):
        issue(issuer,request)
    assert not delivery.requests and not env.provider.calls
