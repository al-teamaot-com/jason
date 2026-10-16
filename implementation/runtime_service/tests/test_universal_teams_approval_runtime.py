"""Real Ed25519, durable requests, live JKD checks, and callback continuation.

Only the final provider-execution boundary is substituted. These tests are not
Microsoft desktop/mobile provider acceptance and never call a customer system.
"""
import base64
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
from types import SimpleNamespace

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import pytest

from connectors.src.jason_connectors.approval_requests import ApprovalRequest, ApprovalRequestStatus
from jason_openclaw.signed_transport import Ed25519TransportAuthenticator, canonical_signed_payload
from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from kernel.identity_authority import (AuthorityGrant, IdentityAuthorityService, IdentityRecord,
    PermissionMode, SQLiteApprovalRepository, SQLiteAuthorityGrantRepository,
    SQLiteIdentityAuthorityStore, SQLiteIdentityRepository)
from orchestrator.approval_plan_scope import ApprovedPlanScope
from orchestrator.contracts import OrchestrationMode, OrchestrationRequest, OrchestrationStatus, ExecutionStage
from orchestrator.teams_identity_binding import MicrosoftIdentityBinding
from orchestrator.teams_identity_binding_sqlite import SQLiteMicrosoftIdentityBindingStore
from orchestrator.teams_plan_grant_bridge import ServerOwnedPlanProposal
from orchestrator.teams_plan_request_repository import plan_fingerprint
from jason_runtime.universal_teams_approval import build_universal_teams_approval_runtime

NOW = datetime(2026,10,16,16,0,tzinfo=timezone.utc)


class ProviderBoundary:
    def __init__(self):
        self.calls=[]
    def execute(self, request):
        assert request.authority_allowed and request.authority_context_id and request.approval_id
        self.calls.append(request)
        return SimpleNamespace(status=OrchestrationStatus.SUCCEEDED,stage=ExecutionStage.COMPLETED,
                               execution_id=request.execution_id)


def setup(tmp_path):
    store=SQLiteIdentityAuthorityStore(tmp_path/'authority.db')
    identities=SQLiteIdentityRepository(store)
    grants=SQLiteAuthorityGrantRepository(store)
    approvals=SQLiteApprovalRepository(store)
    bindings=SQLiteMicrosoftIdentityBindingStore(tmp_path/'bindings.db')
    for name in ('requester-a','requester-b','approver-a','approver-b','outsider'):
        identities.put(IdentityRecord(name,'human','org'))
        bindings.put(MicrosoftIdentityBinding('tenant','object-'+name,name,client_id='client'))
        grants.put(AuthorityGrant('grant-'+name,name,'test.read','org','client',
            PermissionMode.EXECUTE,approval_required=name.startswith('requester')))
    policy=tmp_path/'policy.json'
    policy.write_text(json.dumps({'schema_version':'1.0','organizations':{'org':{
        'role_members':{'reviewer':['approver-a','approver-b']},
        'capability_roles':{'test.read':['reviewer'],'test.verify':['reviewer']},
        'disabled_principals':[], 'max_risk':1,'production_allowed':False,
        'request_retention_allowed':True,'max_ttl_seconds':1800}}}))
    private=Ed25519PrivateKey.generate()
    public=private.public_key().public_bytes(Encoding.PEM,PublicFormat.SubjectPublicKeyInfo)
    authenticator=Ed25519TransportAuthenticator({'gateway-key':public},{'gateway-key':'registered-gateway'})
    authority=IdentityAuthorityService(identities,grants,approvals,contexts=store,clock=lambda:NOW)
    provider=ProviderBoundary()
    handler=build_universal_teams_approval_runtime(mode='enforced', database_path=tmp_path/'plans.db',
        policy_path=policy,bindings=bindings,identities=identities,grants=grants,
        formal_approvals=approvals,authority=authority,authenticator=authenticator,
        allowed_machine_identities=frozenset({'registered-gateway'}),orchestrator=provider,clock=lambda:NOW)
    return SimpleNamespace(handler=handler,private=private,provider=provider,identities=identities,
        grants=grants,approvals=approvals,bindings=bindings,policy=policy)


def seed(env, requester='requester-a', *, extra_step=False):
    h=env.handler
    request=OrchestrationRequest('execution-'+requester,'correlation-'+requester,requester,'org',
        'test.read',None,'deterministic',OrchestrationMode.EXECUTE,False,False,'low',
        DataHandlingPolicy('internal',False,retention_allowed=True),ExecutionBudget(Decimal('0')),
        arguments={'resource_id':'controlled-test'},client_id='client',permission_mode='observe')
    steps=(request,)
    if extra_step:
        steps+=(replace(request,execution_id='verify-'+requester,capability_name='test.verify'),)
    scope=ApprovedPlanScope('plan-'+requester,'org',h.requests.current_policy_digest,
        frozenset(s.capability_name for s in steps),frozenset({'client'}),1,False,NOW+timedelta(minutes=20))
    proposal=ServerOwnedPlanProposal('planapproval-'+requester,'org','client',requester,'test.read',
        plan_fingerprint(steps,scope),scope)
    h.requests.store(proposal,steps,now=NOW)
    h.proposals.store(proposal)
    h.service.teams_flow.approval_service.create(ApprovalRequest(proposal.approval_id,
        request.execution_id,request.correlation_id,'org','client',requester,'test.read','observe',
        NOW-timedelta(seconds=1),NOW+timedelta(minutes=5),('approver-a','approver-b')),now=NOW)
    return proposal


def signed(env, proposal, *, approver='approver-a', decision='approve', **overrides):
    envelope={'kind':'conversation.turn','request_id':'transport-'+proposal.approval_id,
        'correlation_id':'transport-correlation','issued_at':NOW.isoformat(),
        'expires_at':(NOW+timedelta(seconds=90)).isoformat(), 'nonce':'unique-nonce-'+proposal.approval_id,
        'channel':'msteams','text':'Respond to the reviewed approval',
        'transport_identity':{'microsoft_tenant_id':'tenant','microsoft_object_id':'object-'+approver,
                              'authentication_assurance':'botframework-authenticated'},
        'conversation_id':'conversation-'+approver,'message_id':'message-'+approver,
        'interaction':{'kind':'approval.submit','approval_id':proposal.approval_id,'decision':decision,
                       'channel_response_id':'message-'+approver,'selections':{}},
        'key_id':'gateway-key'}
    envelope.update(overrides)
    envelope['signature']=base64.b64encode(env.private.sign(canonical_signed_payload(envelope))).decode()
    return envelope


def click(env, envelope, **overrides):
    interaction=envelope['interaction']
    kwargs=dict(approval_id=interaction['approval_id'],decision=interaction['decision'],
        microsoft_tenant_id=envelope['transport_identity']['microsoft_tenant_id'],
        microsoft_object_id=envelope['transport_identity']['microsoft_object_id'],
        conversation_id=envelope['conversation_id'],channel_response_id=interaction['channel_response_id'],
        decided_at=datetime.fromisoformat(envelope['issued_at']),selections={},signed_envelope=envelope)
    kwargs.update(overrides)
    return env.handler.handle(**kwargs)


@pytest.mark.parametrize('requester',['requester-a','requester-b'])
@pytest.mark.parametrize('approver',['approver-a','approver-b'])
def test_verified_requesters_and_approvers_reach_actual_continuation(tmp_path,requester,approver):
    env=setup(tmp_path); plan=seed(env,requester)
    result=click(env,signed(env,plan,approver=approver))
    assert isinstance(result,dict) and result['executed'] is False
    assert result['status']=='approved' and not env.provider.calls
    assert env.handler.plan_runner.tick() is True
    assert env.handler.requests.progress(plan.approval_id)['state']=='completed'
    assert len(env.provider.calls)==1
    assert env.provider.calls[0].arguments=={'resource_id':'controlled-test'}
    assert env.approvals.get(plan.approval_id).decided_by==approver
    assert env.provider.calls[0].requested_mode=='deterministic'


def test_denial_never_grants_or_calls_provider(tmp_path):
    env=setup(tmp_path);plan=seed(env)
    result=click(env,signed(env,plan,decision='deny'))
    assert result['executed'] is False and result['approval_status']=='denied'
    assert not env.provider.calls and env.approvals.get(plan.approval_id) is None


@pytest.mark.parametrize('changes',[
    {'decision':'deny'}, {'microsoft_object_id':'object-approver-b'},
    {'conversation_id':'other-conversation'}, {'channel_response_id':'other-receipt'},
])
def test_callback_fields_cannot_change_signed_decision(tmp_path,changes):
    env=setup(tmp_path);plan=seed(env)
    with pytest.raises(PermissionError):
        click(env,signed(env,plan),**changes)
    assert not env.provider.calls and env.approvals.get(plan.approval_id) is None


def test_tampered_signature_and_expired_signed_envelope_rejected(tmp_path):
    env=setup(tmp_path);plan=seed(env)
    envelope=signed(env,plan)
    envelope['interaction']['decision']='deny'
    with pytest.raises(PermissionError,match='signature'):
        click(env,envelope)
    old=signed(env,plan,issued_at=(NOW-timedelta(minutes=5)).isoformat(),
               expires_at=(NOW-timedelta(minutes=3)).isoformat())
    with pytest.raises(PermissionError,match='expired'):
        click(env,old)
    assert not env.provider.calls


def test_authorized_identity_not_in_approval_role_is_denied(tmp_path):
    env=setup(tmp_path);plan=seed(env)
    with pytest.raises(PermissionError):
        click(env,signed(env,plan,approver='outsider'))
    assert env.handler.service.teams_flow.approval_service.repository.get(plan.approval_id).status is ApprovalRequestStatus.PENDING
    assert not env.provider.calls


def test_revoked_identity_fails_even_with_cryptographically_valid_card(tmp_path):
    env=setup(tmp_path);plan=seed(env)
    env.identities.put(IdentityRecord('approver-a','human','org',status='disabled'))
    with pytest.raises(PermissionError):
        click(env,signed(env,plan))
    assert not env.provider.calls


def test_cross_organization_binding_never_authorizes_plan(tmp_path):
    env=setup(tmp_path);plan=seed(env)
    env.identities.put(IdentityRecord('foreign','human','other-org'))
    env.bindings.put(MicrosoftIdentityBinding('other-tenant','foreign-object','foreign'))
    envelope=signed(env,plan,transport_identity={'microsoft_tenant_id':'other-tenant',
        'microsoft_object_id':'foreign-object','authentication_assurance':'botframework-authenticated'})
    with pytest.raises(PermissionError,match='organization'):
        click(env,envelope)
    assert not env.provider.calls


def test_replayed_approval_cannot_execute_twice(tmp_path):
    env=setup(tmp_path);plan=seed(env);envelope=signed(env,plan)
    assert click(env,envelope)['status']=='approved'
    assert env.handler.plan_runner.tick() is True
    with pytest.raises((ValueError,PermissionError)):
        click(env,envelope)
    assert len(env.provider.calls)==1


def test_second_step_requires_approver_authority_before_any_acceptance(tmp_path):
    env=setup(tmp_path);plan=seed(env,extra_step=True)
    with pytest.raises(PermissionError,match='plan step'):
        click(env,signed(env,plan))
    assert not env.provider.calls and env.approvals.get(plan.approval_id) is None


def test_policy_change_invalidates_old_pending_plan(tmp_path):
    env=setup(tmp_path);plan=seed(env)
    doc=json.loads(env.policy.read_text());doc['organizations']['org']['disabled_principals']=['approver-a']
    env.policy.write_text(json.dumps(doc))
    with pytest.raises(PermissionError,match='policy'):
        click(env,signed(env,plan))
    assert not env.provider.calls


def test_absent_signed_evidence_fails_closed(tmp_path):
    env=setup(tmp_path);plan=seed(env)
    with pytest.raises(PermissionError,match='signed'):
        click(env,signed(env,plan),signed_envelope=None)



def rebuild(env, tmp_path):
    store=SQLiteIdentityAuthorityStore(tmp_path/'authority.db')
    identities=SQLiteIdentityRepository(store)
    grants=SQLiteAuthorityGrantRepository(store)
    approvals=SQLiteApprovalRepository(store)
    authority=IdentityAuthorityService(identities,grants,approvals,contexts=store,clock=lambda:NOW)
    return build_universal_teams_approval_runtime(mode='enforced',database_path=tmp_path/'plans.db',
        policy_path=env.policy,bindings=SQLiteMicrosoftIdentityBindingStore(tmp_path/'bindings.db'),
        identities=identities,grants=grants,formal_approvals=approvals,authority=authority,
        authenticator=env.handler.evidence_verifier.authenticator,
        allowed_machine_identities=frozenset({'registered-gateway'}),orchestrator=env.provider,clock=lambda:NOW)


def grant_verification_step(env):
    for name in ('requester-a','requester-b','approver-a','approver-b'):
        env.grants.put(AuthorityGrant('verify-grant-'+name,name,'test.verify','org','client',
            PermissionMode.EXECUTE,approval_required=name.startswith('requester')))


def test_one_human_click_runs_two_exact_steps_with_fresh_independent_authority(tmp_path):
    env=setup(tmp_path);grant_verification_step(env);plan=seed(env,extra_step=True)
    assert click(env,signed(env,plan))['status']=='approved'
    # Recreate the worker from durable stores; this is not tied to the HTTP object.
    worker=rebuild(env,tmp_path).plan_runner
    assert worker.tick() is True
    assert [r.capability_name for r in env.provider.calls]==['test.read','test.verify']
    assert len({r.approval_id for r in env.provider.calls})==2
    assert len({r.authority_context_id for r in env.provider.calls})==2
    assert env.handler.requests.progress(plan.approval_id)['completed_steps']==2
    assert rebuild(env,tmp_path).plan_runner.tick() is False
    assert len(env.provider.calls)==2


def test_approval_audit_does_not_claim_execution_before_worker_runs(tmp_path):
    env=setup(tmp_path);plan=seed(env)
    click(env,signed(env,plan))
    from orchestrator.approval_audit import ApprovalAuditEventType
    events=env.handler.service.teams_flow.audit.sink.list_for_approval(approval_id=plan.approval_id,organization_id=plan.organization_id)
    assert ApprovalAuditEventType.ORCHESTRATOR_RESUMED not in [e.event_type for e in events]
    assert not env.provider.calls


def test_revoked_approver_between_click_and_execution_blocks_without_new_prompt(tmp_path):
    env=setup(tmp_path);plan=seed(env)
    click(env,signed(env,plan))
    env.identities.put(IdentityRecord('approver-a','human','org',status='disabled'))
    assert rebuild(env,tmp_path).plan_runner.tick() is True
    assert env.handler.requests.progress(plan.approval_id)['state']=='blocked'
    assert not env.provider.calls


def test_crash_after_atomic_human_decision_recovers_without_another_click(tmp_path,monkeypatch):
    env=setup(tmp_path);plan=seed(env)
    def fail_ledger(*args,**kwargs):
        raise OSError('synthetic storage interruption')
    monkeypatch.setattr(env.handler.service.ledger,'record',fail_ledger)
    with pytest.raises(OSError):
        click(env,signed(env,plan))
    # Decision receipt survives even when later grant publication was interrupted.
    assert env.handler.service.teams_flow.approval_service.repository.accepted_decision(plan.approval_id).status=='approved'
    assert not env.provider.calls
    recovered=rebuild(env,tmp_path)
    assert recovered.plan_runner.tick() is True
    assert len(env.provider.calls)==1
    assert recovered.requests.progress(plan.approval_id)['state']=='completed'


def test_restart_between_steps_skips_completed_step_and_finishes_remaining_step(tmp_path,monkeypatch):
    env=setup(tmp_path);grant_verification_step(env);plan=seed(env,extra_step=True)
    click(env,signed(env,plan))
    real_record=env.handler.requests.record_step_result
    def crash_after_receipt(approval_id,result,*,now):
        real_record(approval_id,result,now=now)
        raise SystemExit('synthetic worker stop after durable execution result')
    monkeypatch.setattr(env.handler.requests,'record_step_result',crash_after_receipt)
    with pytest.raises(SystemExit):
        env.handler.plan_runner.tick()
    assert len(env.provider.calls)==1
    resumed=rebuild(env,tmp_path)
    assert resumed.plan_runner.tick() is True
    assert [r.capability_name for r in env.provider.calls]==['test.read','test.verify']
    assert resumed.requests.progress(plan.approval_id)['state']=='completed'


def test_uncertain_execution_receipt_is_never_blindly_retried(tmp_path,monkeypatch):
    env=setup(tmp_path);plan=seed(env)
    click(env,signed(env,plan))
    def lose_receipt(*args,**kwargs):
        raise OSError('synthetic receipt storage failure after execution')
    monkeypatch.setattr(env.handler.requests,'record_step_result',lose_receipt)
    assert env.handler.plan_runner.tick() is True
    assert len(env.provider.calls)==1
    assert env.handler.requests.progress(plan.approval_id)['state']=='indeterminate'
    fresh=rebuild(env,tmp_path)
    assert fresh.plan_runner.tick() is False
    fresh.plan_runner.process(plan.approval_id)
    assert len(env.provider.calls)==1


def test_universal_maintenance_isolated_from_http_process():
    from jason_runtime.composition import RuntimeSettings
    from jason_runtime.maintenance_process import autonomy_maintenance_enabled,http_runtime_settings
    paths={name:Path('/tmp')/('synthetic-'+name) for name in (
        'authority_db','bindings_db','continuation_db','replay_db','security_audit_db',
        'orchestration_events_db','trusted_keys_registry','openbao_role_id_path','openbao_secret_id_path')}
    settings=RuntimeSettings(**paths,openbao_url='http://openbao.test',ollama_url='http://ollama.test',
        ollama_model='synthetic',allowed_machine_identities=frozenset({'registered-gateway'}),
        universal_approval_mode='enforced')
    assert autonomy_maintenance_enabled(settings)
    serving=http_runtime_settings(settings)
    assert serving.universal_approval_mode=='enforced'
    assert serving.universal_approval_worker_enabled is False
    assert not autonomy_maintenance_enabled(serving)
