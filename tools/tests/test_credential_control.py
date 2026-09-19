from tools import credential_control_service as c
from tools import provision_credential_control as p

def test_policy_is_exact_not_wildcard():
    policy=p.policy_text(); assert 'connectors/*' not in policy and 'providers/*' not in policy
    for spec in p.base.PROVIDERS.values(): assert str(spec['secret_path']) in policy

def test_update_rejects_unexpected_before_secret_write():
    try: c.update('openai',{'api_key':'x','evil':'y'},'tester')
    except c.SafeError as e: assert 'Unexpected' in str(e)
    else: assert False

def test_update_uses_cas_and_never_audits_secret(monkeypatch,tmp_path):
    calls=[]; monkeypatch.setattr(c,'_login',lambda:'token'); monkeypatch.setattr(c,'_revoke',lambda t:None); monkeypatch.setattr(c,'_version',lambda *a:7); monkeypatch.setattr(c,'_request',lambda *a,**k:calls.append((a,k)) or {}); monkeypatch.setattr(c,'AUDIT_FILE',tmp_path/'audit.jsonl')
    out=c.update('openai',{'api_key':'TOP-SECRET-TEST-VALUE'},'tester')
    assert out['old_version']==7 and out['new_version']==8 and out['secret_values_recorded'] is False
    assert 'TOP-SECRET-TEST-VALUE' not in (tmp_path/'audit.jsonl').read_text()
    payload=calls[0][0][3]; assert payload['options']['cas']==7
