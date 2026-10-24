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


def test_reviewed_source_profile_contains_only_existing_worker_and_exact_internal_notes(tmp_path):
    root = source_config(tmp_path)
    campaign = load_campaign(root, now=datetime(2026, 10, 24, tzinfo=timezone.utc))
    doc = json.loads((root/POLICY).read_text())
    assert set(doc['organizations']) == {'aot'}
    policy = doc['organizations']['aot']
    assert set(policy['service_requesters']) == {'jason-autonomy-worker'}
    assert policy['role_members'] == {'pilot_owner': ['person-al']}
    assert set(policy['capability_roles']) == {'service.ticket.note.create'}
    for case in campaign['cases'].values():
        payload = case['arguments']['payload']
        assert payload['ticketID'] == 8870 and payload['noteType'] == 3 and payload['publish'] == 2
        digest = hashlib.sha256(json.dumps(case['arguments'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        assert any(rule['arguments_sha256'] == digest for rule in policy['request_allowlist'])


def test_local_or_explicit_off_never_activates_pilot(tmp_path):
    root = source_config(tmp_path)
    assert settings_defaults({}, root) == ('off', DEFAULT_POLICY)
    assert settings_defaults({'JASON_SOURCE_REVISION': 'a'*40,
        'JASON_UNIVERSAL_APPROVAL_MODE': 'off'}, root) == ('off', DEFAULT_POLICY)


def test_source_profile_is_explicit_and_expiring(tmp_path):
    root = source_config(tmp_path)
    env = {'JASON_SOURCE_REVISION': 'a'*40}
    assert settings_defaults(env, root, now=datetime(2026,10,24,tzinfo=timezone.utc)) == ('enforced', str(root/POLICY))
    assert settings_defaults(env, root, now=datetime(2026,10,28,tzinfo=timezone.utc)) == ('off', DEFAULT_POLICY)
    doc=json.loads((root/MANIFEST).read_text());doc['enabled']=False
    (root/MANIFEST).write_text(json.dumps(doc))
    assert settings_defaults(env, root) == ('off', DEFAULT_POLICY)


def test_modified_policy_never_activates(tmp_path):
    root = source_config(tmp_path)
    (root/POLICY).write_text('{}')
    with pytest.raises(ValueError, match='digest'):
        settings_defaults({'JASON_SOURCE_REVISION': 'a'*40}, root,
            now=datetime(2026,10,24,tzinfo=timezone.utc))


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
