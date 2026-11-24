"""Isolated component transaction and independent health/admission regressions."""
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
import json
import os

import pytest

from tools import parallel_development_install as install
from tools import owner_approved_development_worker as worker

CANDIDATE = 'a' * 40


@pytest.fixture
def images(tmp_path):
    # Archive mount inherits the jason group/setgid; simulate the actual
    # production worker directory without weakening its custody checks.
    os.chown(tmp_path, -1, os.getgid())
    tmp_path.chmod(0o700)
    before = {n: None for n in install.FILES}
    before[install.WORKER] = (b'previous approved worker\n', 0o700)
    after = {n: (('reviewed ' + n).encode(), mode) for n, (_, mode) in install.FILES.items()}
    (tmp_path / install.WORKER).write_bytes(before[install.WORKER][0])
    (tmp_path / install.WORKER).chmod(0o700)
    (tmp_path / 'unrelated.py').write_bytes(b'untouched')
    return before, after


def test_exact_four_file_install_and_rollback(tmp_path, images):
    before, after = images
    with install.FileSet(tmp_path, os.getuid(), os.getgid()) as fs:
        assert fs.all() == before
        for name in install.FILES:
            fs.write(name, before[name], after[name])
        assert fs.all() == after
        fs.rollback(before, after)
        assert fs.all() == before
    assert (tmp_path / 'unrelated.py').read_bytes() == b'untouched'
    assert set(p.name for p in tmp_path.iterdir()) == {install.WORKER, 'unrelated.py'}


def test_interrupted_partial_install_restores_exact_before_images(tmp_path, images):
    before, after = images
    with install.FileSet(tmp_path, os.getuid(), os.getgid()) as fs:
        for name in list(install.FILES)[:2]:
            fs.write(name, before[name], after[name])
    with install.FileSet(tmp_path, os.getuid(), os.getgid()) as fs:
        fs.rollback(install.decoded(install.encoded(before)), install.decoded(install.encoded(after)))
        assert fs.all() == before


def test_foreign_content_denies_rollback_without_touching_other_files(tmp_path, images):
    before, after = images
    with install.FileSet(tmp_path, os.getuid(), os.getgid()) as fs:
        for name in install.FILES:
            fs.write(name, before[name], after[name])
        foreign = next(iter(install.FILES))
        (tmp_path / foreign).write_bytes(b'foreign change')
        observed = fs.all()
        with pytest.raises(PermissionError, match='FOREIGN_ROLLBACK_TARGET'):
            fs.rollback(before, after)
        assert fs.all() == observed


def test_no_follow_and_allowlist(tmp_path, images):
    before, after = images
    other = tmp_path / 'unrelated.py'
    target = next(iter(install.FILES))
    (tmp_path / target).symlink_to(other)
    with install.FileSet(tmp_path, os.getuid(), os.getgid()) as fs:
        with pytest.raises(OSError):
            fs.write(target, None, after[target])
        with pytest.raises(PermissionError, match='NOT_ALLOWLISTED'):
            fs.snapshot('../foreign')
    assert other.read_bytes() == b'untouched'


def test_atomic_add_cannot_overwrite_foreign_file(tmp_path, images):
    before, after = images
    target = next(iter(install.FILES))
    (tmp_path / target).write_bytes(b'existing')
    (tmp_path / target).chmod(0o600)
    with install.FileSet(tmp_path, os.getuid(), os.getgid()) as fs:
        with pytest.raises(PermissionError, match='BEFORE_IMAGE_CHANGED'):
            fs.write(target, None, after[target])
    assert (tmp_path / target).read_bytes() == b'existing'


def test_independent_review_scope_not_global_workspace_fingerprint(images):
    before, after = images
    facts = {'controls': {'freeze': 'unchanged'}, 'protected_peers': {'runtime': {'id': 'same'}}}
    scope = install.scope(CANDIDATE, before, after, {'existing': 'a'}, facts, {'source': 'b'})
    old = install.digest(install.canon(scope))
    install.check_newer_paths({'docs/independent-note.md', 'tools/unrelated_provider.py'},
                              ['tools/release_manager*.py'])
    # Scope neither consumes legacy receipts nor binds unrelated workspace counts.
    assert install.digest(install.canon(install.scope(CANDIDATE,before,after,{'existing':'a'},facts,{'source':'b'}))) == old
    for changed in ({'existing':'changed'}, {'existing':'a','other':'added'}):
        assert install.digest(install.canon(install.scope(CANDIDATE,before,after,changed,facts,{'source':'b'}))) != old
    changed_after = dict(after); changed_after[install.WORKER] = (b'changed', 0o700)
    assert install.digest(install.canon(install.scope(CANDIDATE,before,changed_after,{'existing':'a'},facts,{'source':'b'}))) != old
    assert scope['standing_authority'] is False
    assert scope['freeze_or_pause_change'] is False


@pytest.mark.parametrize('path', ['tools/owner_approved_development_worker.py',
    'config/development-concurrency-scopes.json','tools/support_repair_host_worker.py',
    'tools/manual_release_scope.py','tools/release_manager_new_control.py'])
def test_newer_component_dependency_or_protected_change_denied(path):
    with pytest.raises(PermissionError, match='NEWER_SCOPE_OR_CONTROL_CHANGE'):
        install.check_newer_paths({path}, ['tools/release_manager*.py'])


def test_recheck_material_scope_after_owner_approval(tmp_path, images, monkeypatch):
    before, after = images
    original = install.scope(CANDIDATE,before,after,{}, {'controls':{}},{})
    changed = deepcopy(original); changed['protected']['other'] = 'change'
    monkeypatch.setattr(install,'inspect',lambda *_: (changed,before,after))
    seen=[]
    ns={'owner':lambda s:seen.append(s) or 'test-owner','locks':nullcontext}
    with install.FileSet(tmp_path,os.getuid(),os.getgid()) as fs:
        with pytest.raises(PermissionError,match='APPROVED_MATERIAL_SCOPE_CHANGED'):
            install.apply(CANDIDATE,ns,fs,original)
        assert fs.all() == before
    assert seen == [original]


def test_no_authoritative_health_without_accepted_audit(monkeypatch):
    monkeypatch.setattr(worker,'_health_json',lambda *a: {'phase':'fully_verifying_and_archiving_closed_history'})
    monkeypatch.setattr(worker,'_native_health_guard',lambda:pytest.fail('must not run further probes'))
    value=worker.verified_development_health(worker.DEFAULT_SPOOL)
    assert value['verified'] is False
    assert value['reason'] == 'audit_migration_not_accepted'


@pytest.fixture
def health(monkeypatch):
    docs = {
        'release-status.json': {'phase':'accepted','whole_objective_verified':True,'candidate_sha':CANDIDATE},
        'production-control-state.json':{'schema_version':'1.0','last_known_good':{'manifest':
           {'revision':install.ROLLBACK,'runtime_image_id':'runtime','mcp_image_id':'mcp'}}},
        'production-drift.json':{'schema_version':'1.0','status':'pass','problems':[],'observed_at':'fresh'},
        'operational-health.json':{'status':'pass','failures':[],'snapshot_source_exit_code':0,
          'provider_contacted':False,'provider_credentials_used':False,'check_mode':'frequent_read_only_plus_recent_full_integrity',
          'full_proof_status':'pass','full_proof_age_seconds':20},
        'operational-full-health.json':{'status':'pass','failures':[],'snapshot_source_exit_code':0,
          'provider_contacted':False,'provider_credentials_used':False,'backup_restore_proof':
          {'counts_match':True,'backup_integrity':'ok','restore_integrity':'ok'}},
    }
    units = {'jason-audit-journal-release.service':{'ActiveState':'inactive','MainPID':'0','Result':'success','ExecMainStatus':'0'},
             'jason-audit-journal-maintenance.timer':{'ActiveState':'active'}}
    guard = type('Guard',(),{})()
    guard.protected_release_status=lambda:{'ready':True}
    guard.core_health_evidence=lambda:{'status':'verified','source_sha':install.ROLLBACK,
             'runtime_healthy':True,'mcp_running':True,'worker_scan_fresh':True}
    guard._container=lambda name:{'Image':'runtime' if name=='jason-runtime' else 'mcp'}
    monkeypatch.setattr(worker,'_health_json',lambda path,*args:docs[path.name])
    monkeypatch.setattr(worker,'_health_unit',lambda name:units.get(name,{'ActiveState':'inactive','Result':'success','ExecMainStatus':'0'}))
    monkeypatch.setattr(worker,'_native_health_guard',lambda:guard)
    return docs,units,guard


def test_native_health_gate_accepts_complete_evidence_only(health):
    value=worker.verified_development_health(worker.DEFAULT_SPOOL)
    assert value['verified'] is True
    assert value['production_authority'] is False
    assert value['production_revision'] == install.ROLLBACK


@pytest.mark.parametrize('file,key,value',[
    ('release-status.json','whole_objective_verified',False),
    ('production-drift.json','problems',[{'kind':'drift'}]),
    ('operational-health.json','full_proof_status','missing_or_invalid'),
    ('operational-health.json','status','fail'),
    ('operational-full-health.json','backup_restore_proof',{'counts_match':False}),
    ('operational-full-health.json','provider_contacted',True)])
def test_missing_or_failed_health_never_admits_feature(health,file,key,value):
    docs,_,_=health
    docs[file][key]=value
    assert worker.verified_development_health(worker.DEFAULT_SPOOL)['verified'] is False


def test_breaker_liveness_and_audit_worker_are_independent_gates(health):
    docs,units,guard=health
    guard.protected_release_status=lambda:{'ready':False}
    assert worker.verified_development_health(worker.DEFAULT_SPOOL)['verified'] is False
    guard.protected_release_status=lambda:{'ready':True}
    guard._container=lambda name:{'Image':'wrong'}
    assert worker.verified_development_health(worker.DEFAULT_SPOOL)['verified'] is False
    guard._container=lambda name:{'Image':'runtime' if name=='jason-runtime' else 'mcp'}
    units['jason-audit-journal-release.service']['ActiveState']='activating'
    assert worker.verified_development_health(worker.DEFAULT_SPOOL)['verified'] is False


def test_noncanonical_spool_and_unavailable_root_evidence_fail_closed(health,monkeypatch,tmp_path):
    assert worker.verified_development_health(tmp_path)['verified'] is False
    def missing(*args): raise OSError('unavailable')
    monkeypatch.setattr(worker,'_health_json',missing)
    assert worker.verified_development_health(worker.DEFAULT_SPOOL)['verified'] is False


def test_root_evidence_custody_and_staleness(tmp_path):
    path=tmp_path/'evidence.json'; path.write_text('{}');path.chmod(0o600)
    # Unit-test host account may use a non-matching primary group.
    if os.getgid()!=os.getuid():
        pytest.skip('fixture uid/gid mismatch')
    os.chown(path,-1,os.getgid())
    assert worker._health_json(path,os.getuid(),0o600,30)=={}
    os.utime(path,(1,1))
    with pytest.raises(ValueError,match='stale'):
        worker._health_json(path,os.getuid(),0o600,30)
    link=tmp_path/'alias';link.symlink_to(path)
    with pytest.raises(OSError):
        worker._health_json(link,os.getuid(),0o600)


def test_real_git_independent_and_reverted_conflicting_history(tmp_path, monkeypatch):
    import subprocess
    repo=tmp_path/'repo'; repo.mkdir()
    def git(*args):
        return subprocess.run(['git','-C',str(repo),*args],check=True,capture_output=True).stdout
    git('init','-b','main')
    git('config','user.email','review@example.invalid');git('config','user.name','Lab')
    (repo/'tools').mkdir()
    (repo/'tools/owner_approved_development_worker.py').write_text('before\n')
    git('add','.');git('commit','-m','baseline')
    base=git('rev-parse','HEAD').decode().strip()
    (repo/'tools/owner_approved_development_worker.py').write_text('candidate\n')
    git('commit','-am','candidate')
    candidate=git('rev-parse','HEAD').decode().strip()
    monkeypatch.setattr(install,'ROLLBACK',base)
    monkeypatch.setattr(install,'git',lambda path,*args:git(*args))
    (repo/'independent.txt').write_text('independent\n')
    git('add','.');git('commit','-m','independent')
    head=git('rev-parse','HEAD').decode().strip()
    paths=install.git_paths(repo,candidate,head)
    assert paths=={'independent.txt'}
    install.check_newer_paths(paths,['tools/release_manager*.py'])
    (repo/'tools/owner_approved_development_worker.py').write_text('conflict\n')
    git('commit','-am','conflicting')
    git('revert','--no-edit','HEAD')
    head=git('rev-parse','HEAD').decode().strip()
    assert 'tools/owner_approved_development_worker.py' in install.git_paths(repo,candidate,head)
    with pytest.raises(PermissionError,match='NEWER_SCOPE_OR_CONTROL_CHANGE'):
        install.check_newer_paths(install.git_paths(repo,candidate,head),['tools/release_manager*.py'])


@pytest.mark.parametrize('fail_canary',[False,True])
def test_owner_transaction_durable_receipt_and_exact_recovery(tmp_path, images, monkeypatch, fail_canary):
    before, after=images
    records=tmp_path/'records';records.mkdir(mode=0o700)
    monkeypatch.setattr(install,'RECORDS',records)
    monkeypatch.setattr(install,'DEPS',())
    monkeypatch.setattr(install,'root_dir',lambda path,create=False:None)
    facts={'controls':{},'protected_peers':{'runtime':{'id':'unchanged'}}}
    reviewed=install.scope(CANDIDATE,before,after,{},facts,{})
    monkeypatch.setattr(install,'inspect',lambda *_:(reviewed,before,after))
    monkeypatch.setattr(install,'protected_health',lambda:facts)
    checks=[]
    def canary():
        receipt=json.loads((records/CANDIDATE/'approval.json').read_text())
        assert receipt['scope']==reviewed and receipt['rollback_authorized'] is True
        checks.append('durable_owner_receipt')
        if fail_canary:raise PermissionError('injected postflight failure')
    monkeypatch.setattr(install,'verify_installed',canary)
    ns={'owner':lambda s:'test-owner','locks':nullcontext}
    with install.FileSet(tmp_path,os.getuid(),os.getgid()) as fs:
        if fail_canary:
            with pytest.raises(PermissionError,match='injected postflight'):
                install.apply(CANDIDATE,ns,fs,reviewed)
            assert fs.all()==before
        else:
            install.apply(CANDIDATE,ns,fs,reviewed)
            assert fs.all()==after
    result=json.loads((records/CANDIDATE/'result.json').read_text())
    assert result['status']==('rolled_back' if fail_canary else 'installed_isolated_verified')
    assert checks==['durable_owner_receipt']
    assert (tmp_path/'unrelated.py').read_bytes()==b'untouched'


def test_recovery_cleans_exact_interrupted_staging_but_preserves_foreign(tmp_path, images):
    before,after=images
    name=next(iter(install.FILES))
    with install.FileSet(tmp_path,os.getuid(),os.getgid()) as fs:
        path=tmp_path/fs.temp_name(name,after[name])
        path.write_bytes(after[name][0]);path.chmod(0o600)
        with pytest.raises(PermissionError,match='FOREIGN_OR_UNAPPROVED_TEMPORARY_FILE'):
            fs.check_temps(before,after)
        fs.rollback(before,after)
        assert not path.exists()
        path.write_bytes(b'foreign');path.chmod(0o600)
        with pytest.raises(PermissionError,match='FOREIGN_OR_UNAPPROVED_TEMPORARY_FILE'):
            fs.rollback(before,after)
        assert path.read_bytes()==b'foreign'
