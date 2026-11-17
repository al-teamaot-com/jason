"""Root bootstrap native source-only trust and exact Entra challenge tests."""
from __future__ import annotations
import json
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import builtins
import pytest

from tools import catalog_scoped_root_install_native as n
from tools import catalog_scoped_root_install_transaction as t
from tools import catalog_scoped_root_install_plan as p
from tools.tests.test_catalog_scoped_root_install_transaction import plan


def test_checkout_script_refuses_privileged_execution(plan):
    host=n.NativeRootInstaller(plan,Path('/tmp/catalog-untrusted'),{})
    with pytest.raises(n.NativeBootstrapDenied,match='ROOT_INSTALLED_ISOLATED_EXECUTION_REQUIRED'):
        host.verify_root_bootstrap_trust()


def test_checkout_main_refuses_even_read_only_root_preflight(monkeypatch):
    monkeypatch.setattr(n.sys,'argv',['catalog_scoped_root_install_native.py','--check-only',
        '--exact-plan-sha256','a'*64])
    with pytest.raises(n.NativeBootstrapDenied,match='ROOT_INSTALLED_ISOLATED_EXECUTION_REQUIRED'):
        n.main()


@pytest.mark.parametrize('value',[
    '/etc/passwd','/tmp/catalog-scoped-root-install-20261117',
    '/srv/jason/archive/engineering-evidence/other',
])
def test_plan_from_outside_exact_scope_denied_before_file_read(value):
    with pytest.raises(n.NativeBootstrapDenied,match='UNTRUSTED_EVIDENCE_ROOT_OR_PLAN_HASH'):
        n.load_bootstrap_plan(expected_plan_sha256='a'*64,evidence_root=Path(value))


class FakeEntra:
    TENANT=t.TID
    CLIENT_ID='9b9996e9-5c34-48b7-948c-f44f89352f89'
    SCOPE='https://mcp-jason.teamaot.com/mcp/Jason.Read'
    OWNERS=t.OWNER_OIDS
    def __init__(self):self.calls=[]
    def _form(self,url,args):
        self.calls.append((url,dict(args)))
        if url.endswith('/devicecode'):
            return {'device_code':'internal-never-printed','user_code':'ABC-123',
                    'verification_uri':'https://microsoft.com/devicelogin',
                    'expires_in':300,'interval':5}
        if url.endswith('/token'):
            return {'access_token':'synthetic-bearer-for-offline-test'}
        raise RuntimeError(url)
    def jwt_owner(self,token):
        assert token=='synthetic-bearer-for-offline-test'
        return 'bee80bdc-ffb0-4c50-b453-c09d4d411f5f'


def test_fresh_oauth_owner_checks_exact_consent_and_binds_plan(plan,monkeypatch,capsys):
    fake=FakeEntra()
    host=n.NativeRootInstaller(plan,Path('/tmp/read-only-evidence'),{})
    monkeypatch.setattr(host,'_verified_oauth_module',lambda:fake)
    monkeypatch.setattr(n.time,'sleep',lambda seconds:None)
    monkeypatch.setattr(builtins,'input',lambda prompt:t.CONFIRM)
    receipt=host.obtain_verified_entra_owner_for_exact_action(plan)
    assert receipt['source_sha']==plan['source_sha']
    assert receipt['scope_sha256']==plan['installation_scope_sha256']
    assert receipt['manifest_sha256']==plan['install_plan_sha256']
    assert receipt['affirmative_decision']==t.CONFIRM
    assert receipt['owner_oid'] in t.OWNER_OIDS
    assert receipt['standing_authority'] is False
    assert receipt['provider_write_approved'] is False
    assert receipt['verified_access_token_sha256']==sha256(b'synthetic-bearer-for-offline-test').hexdigest()
    assert len(fake.calls)==2
    printed=capsys.readouterr().out
    assert 'EXACT_ACTION='+t.ACTION in printed
    assert plan['install_plan_sha256'] in printed
    assert 'ABC-123' in printed
    assert 'synthetic-bearer-for-offline-test' not in printed
    assert 'internal-never-printed' not in printed


def test_owner_oauth_cannot_use_chat_only_approval_without_direct_consent(plan,monkeypatch):
    host=n.NativeRootInstaller(plan,Path('/tmp/read-only-evidence'),{})
    monkeypatch.setattr(host,'_verified_oauth_module',lambda:FakeEntra())
    monkeypatch.setattr(n.time,'sleep',lambda seconds:None)
    monkeypatch.setattr(builtins,'input',lambda prompt:'approved in chat')
    with pytest.raises(n.NativeBootstrapDenied,match='OWNER_EXACT_ACTION_CONSENT_MISSING'):
        host.obtain_verified_entra_owner_for_exact_action(plan)
    assert host.owner is None


def test_oauth_signin_failure_never_creates_owner_evidence(plan,monkeypatch):
    class Denied(FakeEntra):
        def _form(self,url,args):
            if url.endswith('/devicecode'):
                return {'device_code':'fake','user_code':'A','verification_uri':'https://microsoft.com/devicelogin',
                        'expires_in':300,'interval':5}
            return {'error':'access_denied'}
    host=n.NativeRootInstaller(plan,Path('/tmp/read-only-evidence'),{})
    monkeypatch.setattr(host,'_verified_oauth_module',lambda:Denied())
    monkeypatch.setattr(n.time,'sleep',lambda seconds:None)
    with pytest.raises(n.NativeBootstrapDenied,match='ENTRA_OWNER_SIGNIN_REJECTED'):
        host.obtain_verified_entra_owner_for_exact_action(plan)
    assert host.owner is None


def test_ci_gate_rejects_missing_protected_jobs(plan,tmp_path,monkeypatch):
    import copy
    fresh={'status':'SOURCE_SCOPE_VERIFIED_NOT_PRODUCTION_ELIGIBLE',
           'protected_source':{'verified_main_sha':plan['source_sha']},
           'protected_ci':{'passed':True,'required_checks':[
               'cap-001','cap-003','cap-007','system-registry','runtime-service',
               'documentation','repository-hygiene','conversation-experience',
               'teams-gateway','governed-security-regressions']},
           'production_mutations':False,'owner_approval_recorded':False}
    fresh['receipt_sha256']=sha256(p.canonical(fresh)).hexdigest()
    adapted=dict(plan)
    adapted['fresh_admission_receipt_sha256']=fresh['receipt_sha256']
    adapted['install_plan_sha256']=sha256(p.canonical({k:v for k,v in adapted.items()
                                                      if k!='install_plan_sha256'})).hexdigest()
    root=tmp_path
    (root/'verified-readonly-admission.json').write_text(json.dumps(fresh))
    host=n.NativeRootInstaller(adapted,root,{})
    def gh(endpoint):
        if endpoint.endswith('git/ref/heads/main'):
            return {'object':{'sha':plan['source_sha']}}
        return {'total_count':0,'check_runs':[]}
    monkeypatch.setattr(host,'_gh',gh)
    with pytest.raises(n.NativeBootstrapDenied,match='PROTECTED_CI_FAILED_OR_INCOMPLETE'):
        host._protected_git_and_ci()


def test_secure_blob_rejects_symlink_group_write_or_changed_source(tmp_path):
    import os
    path=tmp_path/'source.py'
    path.write_text('trusted source')
    path.chmod(0o600)
    assert n.secure_blob(path,owner=os.getuid(),mode=0o600)==b'trusted source'
    path.chmod(0o666)
    with pytest.raises(n.NativeBootstrapDenied,match='SOURCE_FILE_OWNER_MODE_SIZE'):
        n.secure_blob(path,owner=os.getuid())
    path.chmod(0o600)
    link=tmp_path/'source-link.py'
    link.symlink_to(path)
    with pytest.raises(n.NativeBootstrapDenied,match='SOURCE_SYMLINK'):
        n.secure_blob(link,owner=os.getuid())


def test_native_github_only_queries_exact_repo(plan):
    host=n.NativeRootInstaller(plan,Path('/tmp/not-real'),{})
    for path in ('repos/other/repo/git/ref/heads/main','https://evil.invalid/',
                 'repos/al-teamaot-com/jason/../secrets',
                 'repos/al-teamaot-com/jason/commits/xxx;cat /etc/passwd'):
        with pytest.raises(n.NativeBootstrapDenied,match='GITHUB_QUERY_SCOPE_INVALID'):
            host._gh(path)


def test_all_protected_checks_must_be_fresh_and_green(plan,tmp_path,monkeypatch):
    required=['cap-001','cap-003','cap-007','system-registry','runtime-service',
              'documentation','repository-hygiene','conversation-experience',
              'teams-gateway','governed-security-regressions']
    fresh={'status':'SOURCE_SCOPE_VERIFIED_NOT_PRODUCTION_ELIGIBLE',
           'protected_source':{'verified_main_sha':plan['source_sha']},
           'protected_ci':{'passed':True,'required_checks':required},
           'production_mutations':False,'owner_approval_recorded':False}
    fresh['receipt_sha256']=sha256(p.canonical(fresh)).hexdigest()
    changed=dict(plan)
    changed['fresh_admission_receipt_sha256']=fresh['receipt_sha256']
    changed['install_plan_sha256']=sha256(p.canonical({k:v for k,v in changed.items()
                                                      if k!='install_plan_sha256'})).hexdigest()
    (tmp_path/'verified-readonly-admission.json').write_text(json.dumps(fresh))
    host=n.NativeRootInstaller(changed,tmp_path,{})
    checks={name:{'id':i+100,'name':name,'status':'completed','conclusion':'success'}
            for i,name in enumerate(required)}
    def gh(endpoint):
        if endpoint.endswith('/git/ref/heads/main'):
            return {'object':{'sha':plan['source_sha']}}
        return {'total_count':len(checks),'check_runs':list(checks.values())}
    monkeypatch.setattr(host,'_gh',gh)
    host._protected_git_and_ci()
    checks['teams-gateway']['conclusion']='failure'
    with pytest.raises(n.NativeBootstrapDenied,match='PROTECTED_CI_FAILED_OR_INCOMPLETE'):
        host._protected_git_and_ci()
