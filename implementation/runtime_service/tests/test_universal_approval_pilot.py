from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from jason_runtime.universal_approval_pilot import (CONFIG, MANIFEST, POLICY,
    DEFAULT_POLICY, load_campaign, settings_defaults, issue_case)
from test_universal_service_plan_issuance import service_env
from test_universal_teams_approval_runtime import NOW, signed, click


def source_config(tmp_path):
    (tmp_path/POLICY).write_bytes((CONFIG/POLICY).read_bytes())
    (tmp_path/MANIFEST).write_bytes((CONFIG/MANIFEST).read_bytes())
    return tmp_path


def test_reviewed_source_profile_contains_only_existing_worker_and_exact_resolution_steps(tmp_path):
    root = source_config(tmp_path)
    campaign = load_campaign(root, now=datetime(2026, 11, 28, tzinfo=timezone.utc))
    doc = json.loads((root/POLICY).read_text())
    assert set(doc['organizations']) == {'aot'}
    policy = doc['organizations']['aot']
    assert set(policy['service_requesters']) == {'jason-autonomy-worker'}
    assert policy['role_members'] == {'pilot_owner': ['person-entra-bee80bdcffb04c50b453c09d4d411f5f']}
    assert set(policy['capability_roles']) == {'service.ticket.update'}
    assert set(campaign['cases']) == {'approve'}
    steps = campaign['cases']['approve']['steps']
    assert len(steps)==2 and policy['service_requesters']['jason-autonomy-worker']['maximum_plan_steps']==2
    for step in steps:
        payload = step['arguments']['payload']; before=step['arguments']['expected_before']
        assert set(payload)=={'id','resolution'} and payload['id']==8870
        assert before['id']==8870 and before['companyID']==1158 and before['status']==5
        digest = hashlib.sha256(json.dumps(step['arguments'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        assert any(rule['arguments_sha256'] == digest for rule in policy['request_allowlist'])
    assert steps[0]['arguments']['payload']['resolution']==steps[1]['arguments']['expected_before']['resolution']
    assert steps[0]['arguments']['expected_before']['resolution']==steps[1]['arguments']['payload']['resolution']


def test_local_or_explicit_off_never_activates_pilot(tmp_path):
    root = source_config(tmp_path)
    assert settings_defaults({}, root) == ('off', DEFAULT_POLICY)
    assert settings_defaults({'JASON_SOURCE_REVISION': 'a'*40,
        'JASON_UNIVERSAL_APPROVAL_MODE': 'off'}, root) == ('off', DEFAULT_POLICY)


def test_source_profile_is_explicit_and_expiring(tmp_path):
    root = source_config(tmp_path)
    env = {'JASON_SOURCE_REVISION': 'a'*40}
    assert settings_defaults(env, root, now=datetime(2026,11,28,tzinfo=timezone.utc)) == ('enforced', str(root/POLICY))
    assert settings_defaults(env, root, now=datetime(2026,12,1,tzinfo=timezone.utc)) == ('off', DEFAULT_POLICY)
    doc=json.loads((root/MANIFEST).read_text());doc['enabled']=False
    (root/MANIFEST).write_text(json.dumps(doc))
    assert settings_defaults(env, root) == ('off', DEFAULT_POLICY)


def test_modified_policy_never_activates(tmp_path):
    root = source_config(tmp_path)
    (root/POLICY).write_text('{}')
    with pytest.raises(ValueError, match='digest'):
        settings_defaults({'JASON_SOURCE_REVISION': 'a'*40}, root,
            now=datetime(2026,11,28,tzinfo=timezone.utc))


def test_independently_configured_existing_mode_is_not_replaced(tmp_path):
    root=source_config(tmp_path)
    assert settings_defaults({'JASON_UNIVERSAL_APPROVAL_MODE':'enforced',
        'JASON_UNIVERSAL_APPROVAL_POLICY':'/existing/config'},root)==('enforced','/existing/config')


def test_expired_live_pilot_policy_denies_even_a_previously_valid_request(tmp_path):
    from jason_runtime.universal_teams_approval import UniversalApprovalPolicyFile
    env, delivery, issuer, request = service_env(tmp_path)
    doc=json.loads(env.policy.read_text());doc['organizations']['org']['valid_until']=(NOW-timedelta(seconds=1)).isoformat()
    env.policy.write_text(json.dumps(doc))
    policy=UniversalApprovalPolicyFile(env.policy, clock=lambda:NOW)
    with pytest.raises(PermissionError,match='expired'):
        policy.assert_request_allowed(request,required=True)


def test_pilot_cli_preserves_pending_request_and_requires_actual_deny_first(tmp_path):
    env, delivery, issuer, request = service_env(tmp_path)
    doc=json.loads(env.policy.read_text())
    doc['organizations']['org']['production_allowed']=True
    doc['organizations']['org']['request_allowlist'][0]['permission_mode']='execute'
    env.policy.write_text(json.dumps(doc))
    campaign={'requester_id':'worker','organization_id':'org','cases':{}}
    for case in ('deny','approve'):
        campaign['cases'][case]={'approval_id':'planapproval-cli-'+case,
            'execution_id':'cli-exec-'+case,'capability':'synthetic.resource.read',
            'arguments':dict(request.arguments),'client_id':'client',
            'title':'Controlled '+case,'summary':'Exact internal test.'}
    app=SimpleNamespace(universal_approval_handler=env.handler)
    with pytest.raises(PermissionError,match='Deny'):
        issue_case(app,campaign,'approve')
    issue_case(app,campaign,'deny')
    assert len(delivery.requests)==1 and not env.provider.calls
    assert issue_case(app,campaign,'deny')['reissued'] is False
    assert len(delivery.requests)==1
    proposal=env.handler.proposals.require('planapproval-cli-deny')
    click(env,signed(env,proposal,decision='deny'))
    assert not env.provider.calls
    issue_case(app,campaign,'approve')
    assert len(delivery.requests)==2
    proposal=env.handler.proposals.require('planapproval-cli-approve')
    click(env,signed(env,proposal))
    # The real worker handles one pending terminal state per cycle. Process
    # this known approved case through the same complete validation method.
    env.handler.plan_runner.process('planapproval-cli-approve')
    assert env.handler.requests.progress('planapproval-cli-approve')['state']=='completed'
    assert len(env.provider.calls)==1
    assert issue_case(app,campaign,'approve')['reissued'] is False
    assert len(delivery.requests)==2 and len(env.provider.calls)==1


def test_source_pilot_does_not_activate_in_embedded_mcp_application(tmp_path):
    root=source_config(tmp_path)
    env={'JASON_SOURCE_REVISION':'a'*40,'JASON_MCP_RESOURCE_URL':'https://example.invalid/mcp'}
    assert settings_defaults(env,root,now=datetime(2026,11,28,tzinfo=timezone.utc))==('off',DEFAULT_POLICY)

@pytest.mark.parametrize('decision',['approve','deny'])
def test_single_reviewed_card_covers_ordered_service_steps_without_second_approval(tmp_path,decision):
    env, delivery, issuer, request = service_env(tmp_path)
    doc=json.loads(env.policy.read_text()); org=doc['organizations']['org']
    org['production_allowed']=True
    org['service_requesters']['worker']['maximum_plan_steps']=2
    org['request_allowlist'][0]['permission_mode']='execute'
    second={'resource_id':'controlled-restore'}
    org['request_allowlist'].append({**org['request_allowlist'][0], 'arguments_sha256':hashlib.sha256(json.dumps(second,sort_keys=True,separators=(',',':')).encode()).hexdigest()})
    env.policy.write_text(json.dumps(doc))
    campaign={'schema_version':'2.0','requester_id':'worker','organization_id':'org','cases':{'approve':{'approval_id':'planapproval-cli-two','title':'One approval','summary':'Review two exact steps.', 'steps':[
        {'execution_id':'cli-two-1','capability':request.capability_name,'arguments':dict(request.arguments),'client_id':'client'},
        {'execution_id':'cli-two-2','capability':request.capability_name,'arguments':second,'client_id':'client'}]}}}
    app=SimpleNamespace(universal_approval_handler=env.handler)
    issue_case(app,campaign,'approve')
    assert len(delivery.requests)==1 and not env.provider.calls
    proposal=env.handler.proposals.require('planapproval-cli-two')
    click(env,signed(env,proposal,decision=decision))
    env.handler.plan_runner.process('planapproval-cli-two')
    if decision=='approve':
        assert env.handler.requests.progress('planapproval-cli-two')['state']=='completed'
        assert [x.arguments for x in env.provider.calls]==[request.arguments,second]
    else: assert not env.provider.calls
    assert issue_case(app,campaign,'approve')['reissued'] is False
    assert len(delivery.requests)==1
