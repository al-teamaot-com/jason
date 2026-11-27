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

def test_optional_preproduction_shadow_not_a_mandatory_production_peer():
    # The preproduction-only shadow gateway can be stopped after OOM without
    # failing release health for the protected production worker. The native
    # drift policy and core health guard still independently protect runtime
    # and MCP. This is not an override of either guard.
    policy=json.loads((Path(__file__).resolve().parents[2] /
                       'config/production-desired-state.json').read_text())
    required=set(policy['required_containers'])
    assert required <= set(install.PEERS)
    assert 'jason-pmv4-shadow-gateway' not in required
    assert 'jason-pmv4-shadow-gateway' not in install.PEERS
    assert {'jason-runtime','jason-mcp-pilot','jason-pmv4-ticket-core',
            'jason-teams-gateway','openbao'} == set(install.PEERS)



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


def test_legacy_overlap_holds_are_exact_owner_bound_without_activation(images):
    before, after = images
    held = {'disposition': 'preexisting_sources_held_not_active_or_deployment_authorized',
            'open_prs': [{'number': 692, 'head_sha': '1'*40, 'draft': True,
                          'changed_files': ['tools/owner_approved_development_worker.py']}],
            'dirty_worktrees': [{'path': '/home/al/held-editor',
                                 'head_sha': '2'*40,
                                 'file_sha256': {'tools/owner_approved_development_worker.py': '3'*64},
                                 'changed_files': ['tools/owner_approved_development_worker.py']}]}
    scope = install.scope(CANDIDATE, before, after, {}, {'controls': {}}, {}, held)
    baseline = install.digest(install.canon(scope))
    assert scope['legacy_overlap_review'] == held
    assert scope['standing_authority'] is False
    assert scope['freeze_or_pause_change'] is False
    for segment, key, value in [('open_prs','head_sha','4'*40),
                                ('dirty_worktrees','head_sha','5'*40),
                                ('dirty_worktrees','file_sha256',
                                 {'tools/owner_approved_development_worker.py':'6'*64})]:
        changed = deepcopy(held)
        changed[segment][0][key] = value
        assert install.digest(install.canon(install.scope(
            CANDIDATE,before,after,{}, {'controls':{}},{},changed))) != baseline


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
def health(monkeypatch,tmp_path):
    monkeypatch.setattr(worker,"NORMAL_RETIREMENT_POLICY",tmp_path/"retired.json")
    docs = {
        'forward-release-status.json': {
          'schema_version':'1.0','action':install.FORWARD_ACTION,
          'scope_sha256':install.FORWARD_SCOPE_SHA256,
          'phase':'accepted','status':'accepted','no_legacy_rebuild':True,
          'provider_calls':0,'initial_archive_events':install.FORWARD_ARCHIVED_EVENTS,
          'root_free_bytes':52_000_000_000,'sealed_segments':2,
          'full_health':'pass','fast_health':'pass','drift':'pass','breaker':'closed'},
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
             'jason-audit-journal-no-restore-release.service':{'ActiveState':'inactive','MainPID':'0','Result':'success','ExecMainStatus':'0'},
             'jason-audit-journal-maintenance.service':{'ActiveState':'inactive','MainPID':'0','Result':'success','ExecMainStatus':'0'},
             'jason-audit-journal-maintenance.timer':{'ActiveState':'active'}}
    guard = type('Guard',(),{})()
    guard.protected_release_status=lambda:{'ready':True}
    guard.core_health_evidence=lambda:{'status':'verified','source_sha':install.ROLLBACK,
             'runtime_healthy':True,'mcp_running':True,'worker_scan_fresh':True}
    guard._container=lambda name:{'Image':'runtime' if name=='jason-runtime' else 'mcp'}
    monkeypatch.setattr(worker,'_health_json',lambda path,*args:docs[path.name])
    monkeypatch.setattr(worker,'_health_unit',lambda name:units.get(name,{'ActiveState':'inactive','Result':'success','ExecMainStatus':'0'}))
    guard.read_components=lambda:None
    monkeypatch.setattr(worker,'_native_health_guard',lambda:(guard,guard.read_components))
    return docs,units,guard


def test_native_health_gate_accepts_complete_evidence_only(health):
    value=worker.verified_development_health(worker.DEFAULT_SPOOL)
    assert value['verified'] is True
    assert value['production_authority'] is False
    assert value['production_revision'] == install.ROLLBACK


@pytest.mark.parametrize('file,key,value',[
    ('forward-release-status.json','phase','awaiting_actual_no_restore_daily_rollover_and_native_health'),
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


def test_canonical_stage_c_guard_scope_is_owner_bound(images):
    before, after = images
    root_before = (b'original-trusted-native-guard', 0o444)
    root_after = (b'stage-c-trusted-native-guard', 0o444)
    facts = {'controls': {}, 'protected_peers': {}}
    checked = install.scope(CANDIDATE, before, after, {}, facts, {},
                            guard_before=root_before, guard_after=root_after)
    native = checked['native_guard_repair']
    assert native['target'] == str(install.GUARD_PATH)
    assert native['root_owned'] is True and native['service_restarts'] == 0
    assert native['before'] == install.image(root_before)
    assert native['after'] == install.image(root_after)
    assert str(install.GUARD_PATH) in checked['installation_targets']
    assert any(str(install.GUARD_DIR) in name and install.GUARD_NAME in name
               for name in checked['reserved_temporary_files'])
    changed = install.scope(CANDIDATE, before, after, {}, facts, {},
                            guard_before=root_before, guard_after=(b'foreign', 0o444))
    assert install.digest(install.canon(checked)) != install.digest(install.canon(changed))
    with pytest.raises(PermissionError, match='NATIVE_GUARD_SCOPE_INCOMPLETE'):
        install.scope(CANDIDATE, before, after, {}, facts, {}, guard_before=root_before)


def test_native_root_guard_fileset_rollback_and_allowlist(tmp_path):
    root = tmp_path / 'root-trusted'
    root.mkdir()
    root.chmod(0o700)
    name = install.GUARD_NAME
    other = root / 'foreign-no-touch'
    other.write_bytes(b'unchanged')
    original = (b'original-root-owned-read-only-guard', 0o444)
    candidate = (b'reviewed-stage-c-guard', 0o444)
    path = root / name
    path.write_bytes(original[0])
    path.chmod(original[1])
    with install.FileSet(root, os.getuid(), os.getgid(), (name,)) as fs:
        assert fs.all() == {name: original}
        with pytest.raises(PermissionError, match='NOT_ALLOWLISTED'):
            fs.snapshot('foreign-no-touch')
        fs.write(name, original, candidate)
        assert fs.all() == {name: candidate}
        fs.rollback({name: original}, {name: candidate})
        assert fs.all() == {name: original}
    assert other.read_bytes() == b'unchanged'
    assert path.stat().st_mode & 0o777 == 0o444


@pytest.mark.parametrize('fail_acceptance', [False, True])
def test_one_owner_worker_and_native_guard_atomic_rollback(tmp_path, images, monkeypatch, fail_acceptance):
    before, after = images
    native_dir = tmp_path / 'trusted-root-files'
    native_dir.mkdir()
    native_dir.chmod(0o700)
    old = b'original-native-guard'
    new = b'stage-c-native-guard'
    native_file = native_dir / install.GUARD_NAME
    native_file.write_bytes(old)
    native_file.chmod(0o444)
    monkeypatch.setattr(install, 'GUARD_DIR', native_dir)
    monkeypatch.setattr(install, 'GUARD_PATH', native_file)
    monkeypatch.setattr(install, 'GUARD_BEFORE_SHA', install.digest(old))
    monkeypatch.setattr(install, 'GUARD_AFTER_SHA', install.digest(new))
    records = tmp_path.parent / (tmp_path.name + '-records')
    records.mkdir(mode=0o700)
    monkeypatch.setattr(install, 'RECORDS', records)
    monkeypatch.setattr(install, 'root_dir', lambda path, create=False: None)
    monkeypatch.setattr(install, 'DEPS', ())
    monkeypatch.setattr(install, 'git', lambda *_: new)
    facts = {'controls': {}, 'protected_peers': {'runtime': {'id': 'unchanged'}}}
    checked = install.scope(CANDIDATE, before, after, {}, facts, {},
                            guard_before=(old, 0o444), guard_after=(new, 0o444))
    monkeypatch.setattr(install, 'inspect', lambda *_: (checked, before, after))
    monkeypatch.setattr(install, 'protected_health', lambda *args, **kwargs: facts)
    def acceptance():
        if fail_acceptance:
            raise PermissionError('injected five-file acceptance failure')
    monkeypatch.setattr(install, 'verify_installed', acceptance)
    ns = {'owner': lambda scope: 'test-owner', 'locks': nullcontext}
    with install.FileSet(tmp_path, os.getuid(), os.getgid()) as fs, \
         install.FileSet(native_dir, os.getuid(), os.getgid(), (install.GUARD_NAME,)) as guardfs:
        if fail_acceptance:
            with pytest.raises(PermissionError, match='injected five-file'):
                install.apply(CANDIDATE, ns, fs, checked, guardfs)
            assert fs.all() == before and guardfs.all() == {install.GUARD_NAME: (old, 0o444)}
        else:
            install.apply(CANDIDATE, ns, fs, checked, guardfs)
            assert fs.all() == after and guardfs.all() == {install.GUARD_NAME: (new, 0o444)}
    receipt = json.loads((records / CANDIDATE / 'approval.json').read_text())
    assert receipt['guard_before_bytes'] and receipt['guard_after_bytes']
    assert receipt['scope']['native_guard_repair'] == checked['native_guard_repair']
    result = json.loads((records / CANDIDATE / 'result.json').read_text())
    assert result['status'] == ('rolled_back' if fail_acceptance else 'installed_isolated_verified')


def test_interrupted_five_file_receipt_recovers_only_exact_approved_images(
    tmp_path, images, monkeypatch
):
    before, after = images
    native_dir = tmp_path / 'trusted-root'
    native_dir.mkdir()
    native_dir.chmod(0o700)
    old, new = b'trusted-previous-guard', b'canonical-stage-c-guard'
    native = native_dir / install.GUARD_NAME
    native.write_bytes(old)
    native.chmod(0o444)
    monkeypatch.setattr(install, 'GUARD_DIR', native_dir)
    monkeypatch.setattr(install, 'GUARD_PATH', native)
    monkeypatch.setattr(install, 'GUARD_BEFORE_SHA', install.digest(old))
    monkeypatch.setattr(install, 'GUARD_AFTER_SHA', install.digest(new))
    monkeypatch.setattr(install, 'DEPS', ())
    records = tmp_path.parent / (tmp_path.name + '-receipts')
    records.mkdir(mode=0o700)
    monkeypatch.setattr(install, 'RECORDS', records)
    monkeypatch.setattr(install, 'root_dir', lambda path, create=False: None)
    monkeypatch.setattr(install, 'git', lambda *_: new)
    monkeypatch.setattr(install, 'protected_health', lambda *args, **kwargs: {'controls': {}})
    monkeypatch.setattr(install, 'verify_installed', lambda: None)
    source_hashes = {'tools/parallel_development_install.py':
                     install.digest(Path(install.__file__).read_bytes())}
    reviewed = install.scope(CANDIDATE, before, after, {}, {'controls': {}},
                             source_hashes, guard_before=(old, 0o444),
                             guard_after=(new, 0o444))
    monkeypatch.setattr(install, 'inspect', lambda *_: (reviewed, before, after))
    ns = {'owner': lambda _: 'test-owner', 'locks': nullcontext}
    with install.FileSet(tmp_path, os.getuid(), os.getgid()) as fs, \
         install.FileSet(native_dir, os.getuid(), os.getgid(), (install.GUARD_NAME,)) as guardfs:
        install.apply(CANDIDATE, ns, fs, reviewed, guardfs)
        assert fs.all() == after
        assert guardfs.all() == {install.GUARD_NAME: (new, 0o444)}
        (records / CANDIDATE / 'result.json').unlink()
        # A real crash before result publication leaves a durable root receipt
        # and exact installed images. This simulates that window, not new consent.
        monkeypatch.setattr(install, 'control_bytes', lambda: {})
        monkeypatch.setattr(install, 'unit',
                            lambda name, user=False: {'ActiveState': 'inactive'})
        original_read = install.read
        def local_approval(path, uid, mode=None, **kwargs):
            if Path(path) == records / CANDIDATE / 'approval.json':
                return Path(path).read_bytes()
            return original_read(path, uid, mode, **kwargs)
        monkeypatch.setattr(install, 'read', local_approval)
        install.recover(CANDIDATE, {'locks': nullcontext}, fs, guardfs)
        assert fs.all() == before
        assert guardfs.all() == {install.GUARD_NAME: (old, 0o444)}
    result = json.loads((records / CANDIDATE / 'result.json').read_text())
    assert result['status'] == 'rolled_back_interrupted'
    assert (tmp_path / 'unrelated.py').read_bytes() == b'untouched'


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


def _accepted_forward_fixture():
    return {'schema_version':'1.0','action':install.FORWARD_ACTION,
        'scope_sha256':install.FORWARD_SCOPE_SHA256,
        'phase':'accepted','status':'accepted','no_legacy_rebuild':True,
        'provider_calls':0,'initial_archive_events':install.FORWARD_ARCHIVED_EVENTS,
        'root_free_bytes':52_000_000_000,'sealed_segments':2,
        'full_health':'pass','fast_health':'pass','drift':'pass','breaker':'closed'}


@pytest.mark.parametrize('field,value',[
    ('phase','awaiting_actual_no_restore_daily_rollover_and_native_health'),
    ('status',None),('schema_version','2.0'),('action','ADOPT-EXACT-DAILY-AUDIT-JOURNAL'),
    ('scope_sha256','0'*64),('no_legacy_rebuild',False),
    ('provider_calls',1),('provider_calls',False),
    ('initial_archive_events',34616409),('initial_archive_events',True),
    ('root_free_bytes',10_000_000_000),('root_free_bytes',True),
    ('sealed_segments',1),('sealed_segments',True),
    ('full_health','failed'),('fast_health','missing'),('drift','drift_detected'),
    ('breaker','open')])
def test_both_parallel_admission_paths_reject_unaccepted_forward_receipt(field,value):
    accepted=_accepted_forward_fixture()
    assert install.forward_audit_accepted(accepted) is True
    assert worker.accepted_forward_audit(accepted) is True
    corrupt=dict(accepted);corrupt[field]=value
    assert install.forward_audit_accepted(corrupt) is False
    assert worker.accepted_forward_audit(corrupt) is False


def test_legacy_acceptance_is_never_treated_as_no_restore_acceptance():
    legacy={'phase':'accepted','whole_objective_verified':True,'candidate_sha':'a'*40}
    assert install.forward_audit_accepted(legacy) is False
    assert worker.accepted_forward_audit(legacy) is False


def test_root_parallel_install_requires_completed_one_shot_and_maintenance(monkeypatch):
    units={'jason-audit-journal-release.service':
            {'ActiveState':'inactive','MainPID':'0','Result':'success','ExecMainStatus':'0'},
           'jason-audit-journal-no-restore-release.service':
            {'ActiveState':'inactive','MainPID':'0','Result':'success','ExecMainStatus':'0'},
           'jason-audit-journal-maintenance.service':
            {'ActiveState':'inactive','MainPID':'0','Result':'success','ExecMainStatus':'0'},
           'jason-audit-journal-maintenance.timer':{'ActiveState':'active'}}
    monkeypatch.setattr(install,'unit',lambda name,user=False:units[name])
    assert install.audit_recovery_service_complete() is True
    for name,field,value in (
        ('jason-audit-journal-no-restore-release.service','ActiveState','activating'),
        ('jason-audit-journal-release.service','ActiveState','activating'),
        ('jason-audit-journal-maintenance.timer','ActiveState','inactive'),
        ('jason-audit-journal-maintenance.service','Result','exit-code'),
        ('jason-audit-journal-no-restore-release.service','MainPID','999'),
    ):
        original=units[name][field]
        units[name][field]=value
        assert install.audit_recovery_service_complete() is False, (name,field)
        units[name][field]=original


def test_worker_rejects_recovery_still_activating_even_with_accepted_receipt(health):
    docs,units,_=health
    assert worker.verified_development_health(worker.DEFAULT_SPOOL)['verified'] is True
    units['jason-audit-journal-no-restore-release.service']['ActiveState']='activating'
    result=worker.verified_development_health(worker.DEFAULT_SPOOL)
    assert result['verified'] is False and result['reason']=='audit_release_not_quiescent'
    units['jason-audit-journal-no-restore-release.service']['ActiveState']='inactive'
    units['jason-audit-journal-maintenance.service']['Result']='exit-code'
    result=worker.verified_development_health(worker.DEFAULT_SPOOL)
    assert result['verified'] is False and result['reason']=='audit_maintenance_not_verified'


def test_real_root_entrypoint_denies_incomplete_audit_before_owner_or_install(monkeypatch):
    """Exercise actual `main()` audit gate, not a mocked preflight function.

    We never execute Root or a provider. This recreates the exact isolated
    root flag/CLI envelope and makes all subsequent privileges unreachable.
    """
    from types import SimpleNamespace
    import sys as real_sys
    monkeypatch.setattr(real_sys,'argv',['parallel_development_install.py','--candidate-sha',CANDIDATE,'--review-only'])
    monkeypatch.setattr(install,'sys',SimpleNamespace(flags=SimpleNamespace(isolated=1)))
    monkeypatch.setattr(install,'os',SimpleNamespace(geteuid=lambda:0))
    # Simulate the reviewed host worktree path in both GitHub Actions and on
    # Jason. Do not weaken the installed Root path guard itself.
    monkeypatch.setattr(install,'REPO',Path('/srv/jason/archive/engineering-worktrees/isolated-reviewed-candidate'))
    monkeypatch.setattr(install,'read',lambda *a,**k:install.canon({
        **_accepted_forward_fixture(),
        'phase':'awaiting_actual_no_restore_daily_rollover_and_native_health'}))
    monkeypatch.setattr(install,'native_code',lambda *a,**k:pytest.fail('must not load owner issuer'))
    with pytest.raises(PermissionError,match='AUDIT_FORWARD_RECOVERY_NOT_ACCEPTED'):
        install.main()


def test_real_root_entrypoint_reaches_pinned_issuer_only_after_forward_acceptance(monkeypatch):
    from types import SimpleNamespace
    import sys as real_sys
    monkeypatch.setattr(real_sys,'argv',['parallel_development_install.py','--candidate-sha',CANDIDATE,'--review-only'])
    monkeypatch.setattr(install,'sys',SimpleNamespace(flags=SimpleNamespace(isolated=1)))
    monkeypatch.setattr(install,'os',SimpleNamespace(geteuid=lambda:0))
    # Simulate the reviewed host worktree path in both GitHub Actions and on
    # Jason. Do not weaken the installed Root path guard itself.
    monkeypatch.setattr(install,'REPO',Path('/srv/jason/archive/engineering-worktrees/isolated-reviewed-candidate'))
    monkeypatch.setattr(install,'read',lambda *a,**k:install.canon(_accepted_forward_fixture()))
    units={'jason-audit-journal-release.service':
            {'ActiveState':'inactive','MainPID':'0','Result':'success','ExecMainStatus':'0'},
           'jason-audit-journal-no-restore-release.service':
            {'ActiveState':'inactive','MainPID':'0','Result':'success','ExecMainStatus':'0'},
           'jason-audit-journal-maintenance.service':
            {'ActiveState':'inactive','MainPID':'0','Result':'success','ExecMainStatus':'0'},
           'jason-audit-journal-maintenance.timer':{'ActiveState':'active'}}
    monkeypatch.setattr(install,'unit',lambda name,user=False:units[name])
    monkeypatch.setattr(install,'native_code',lambda *a,**k:(_ for _ in ()).throw(
        RuntimeError('NEXT_TRUSTED_ISSUER_REACHED_WITH_NO_WRITES')))
    with pytest.raises(RuntimeError,match='NEXT_TRUSTED_ISSUER_REACHED_WITH_NO_WRITES'):
        install.main()


@pytest.fixture
def coordinated_health(health):
    docs,units,guard=health
    manifest=docs['production-control-state.json']['last_known_good']['manifest']
    worker.NORMAL_RETIREMENT_POLICY.touch()
    rows={
        'jason-runtime':{'revision':install.ROLLBACK,'image_id':'runtime','container_id':'runtime-id'},
        'jason-mcp-pilot':{'revision':'a'*40,'image_id':'mcp-new','container_id':'mcp-new-id'},
    }
    state={'schema_version':'3.0','status':'verified_component_release',
           'host_revision':manifest['revision'],'components':rows}
    def live(name):
        row=rows[name]
        return {'Image':row['image_id'],'Id':row['container_id'],
                'Config':{'Labels':{'com.teamaot.jason.source_revision':row['revision']}}}
    guard.read_components=lambda:state
    guard._container=live
    return guard,state


def test_development_health_accepts_independently_verified_scoped_components(coordinated_health):
    result=worker.verified_development_health(worker.DEFAULT_SPOOL)
    assert result['verified'] is True
    assert result['production_authority'] is False
    assert result['production_revision']==install.ROLLBACK


@pytest.mark.parametrize('field',['Image','Id','revision'])
def test_scoped_development_health_rejects_unexpected_live_identity(coordinated_health,field):
    guard,state=coordinated_health
    original=guard._container
    def live(name):
        result=original(name)
        if name=='jason-mcp-pilot':
            if field=='revision':
                result['Config']['Labels']['com.teamaot.jason.source_revision']='b'*40
            else:
                result[field]='different'
        return result
    guard._container=live
    result=worker.verified_development_health(worker.DEFAULT_SPOOL)
    assert result['verified'] is False
    assert result['reason']=='live_core_image_mismatch'


@pytest.mark.parametrize('key,value',[('host_revision','b'*40),('schema_version','1.0'),
                                      ('status','unverified')])
def test_scoped_health_rejects_unverified_anchor(coordinated_health,key,value):
    guard,state=coordinated_health
    state[key]=value
    result=worker.verified_development_health(worker.DEFAULT_SPOOL)
    assert result['verified'] is False
    assert result['reason']=='live_core_component_anchor_mismatch'


def test_scoped_health_does_not_fall_back_after_retirement(coordinated_health):
    guard,state=coordinated_health
    guard.read_components=lambda:None
    result=worker.verified_development_health(worker.DEFAULT_SPOOL)
    assert result['verified'] is False
    assert result['reason']=='live_core_component_readback_missing'


def test_scoped_health_rejects_changed_readback_during_probe(coordinated_health):
    from copy import deepcopy
    guard,state=coordinated_health
    later=deepcopy(state)
    later['components']['jason-mcp-pilot']['image_id']='different'
    records=iter([state,later])
    guard.read_components=lambda:next(records)
    result=worker.verified_development_health(worker.DEFAULT_SPOOL)
    assert result['verified'] is False
    assert result['reason']=='native_health_changed_during_probe'


def test_scoped_health_rejects_reader_failure(coordinated_health):
    guard,_=coordinated_health
    def denied():
        raise PermissionError('independent readback denied')
    guard.read_components=denied
    assert worker.verified_development_health(worker.DEFAULT_SPOOL)['verified'] is False
