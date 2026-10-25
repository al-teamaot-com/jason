from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import time
from pathlib import Path

import pytest
import jason_storage_autorepair as storage


def test_reviewed_policy_is_bounded():
    p=storage.policy()
    assert p['intervention_used_percent']==80
    assert p['destination_max_used_percent']==80
    assert p['allow_actions']==['archive_reconstructible_clean_detached_worktree','scoped_unused_buildx_cache_cleanup']
    assert p['no_service_signals'] is True
    assert p['no_live_data_mutations'] is True


def test_unapproved_broadened_policy_denied(tmp_path):
    p=storage.policy()
    p['allow_actions'].append('docker_image_prune')
    f=tmp_path/'policy.json';f.write_text(json.dumps(p))
    with pytest.raises(ValueError,match='unreviewed'):
        storage.policy(f)


def test_both_drives_high_denies_any_worktree_action(monkeypatch):
    monkeypatch.setattr(storage,'capacity_gate',lambda p:('both_drives_80_owner_capacity_review',{'root_percent':90,'archive_percent':85}))
    monkeypatch.setattr(storage,'candidates',lambda *a,**k:pytest.fail('candidates must not be inspected'))
    r=storage.repair()
    assert r['status']=='both_drives_80_owner_capacity_review'
    assert r['archived_count']==0


def test_no_archive_mount_denies_any_cleanup(monkeypatch):
    monkeypatch.setattr(storage,'capacity_gate',lambda p:('blocked_missing_independent_archive',{}))
    monkeypatch.setattr(storage,'candidates',lambda *a,**k:pytest.fail('candidates must not be inspected'))
    assert storage.repair()['status']=='blocked_missing_independent_archive'


def test_dry_run_does_not_copy_or_remove(monkeypatch):
    monkeypatch.setattr(storage,'capacity_gate',lambda p:('repair_allowed',{'root_percent':96,'archive_percent':5}))
    monkeypatch.setattr(storage,'candidates',lambda *a,**k:[(Path('/example/old'), 'a'*40)])
    assert storage.repair(dry_run=True)['candidate_count']==1


def test_immutable_snapshot_verified_without_touching_original(tmp_path):
    src=tmp_path/'safe-old-worktree';src.mkdir()
    (src/'.git').write_text('gitdir: /repo/.git/worktrees/old\n')
    (src/'code.txt').write_text('checked into merged source\n')
    dest=tmp_path/'archive'/'safe-old-worktree-abcdef.tar'
    digest,amount=storage.tar_snapshot(src,dest,'a'*40)
    assert dest.exists() and (src/'code.txt').exists()
    assert amount==dest.stat().st_size
    assert hashlib.sha256(dest.read_bytes()).hexdigest()==digest
    assert os.stat(dest).st_mode & 0o077 == 0
    with tarfile.open(dest) as t:
        assert src.name+'/code.txt' in t.getnames()


def test_archived_clean_old_worktree_has_durable_manifest(monkeypatch,tmp_path):
    srcroot=tmp_path/'old-worktrees';srcroot.mkdir()
    item=srcroot/'safe-clean-merged';item.mkdir()
    (item/'.git').write_text('gitdir: /repo/.git/worktrees/x\n')
    (item/'app.py').write_text('pass\n')
    archive=tmp_path/'archive';archive.mkdir()
    spool=tmp_path/'state';spool.mkdir()
    reviewed=dict(storage.policy())
    reviewed['source_worktree_root']=str(srcroot)
    reviewed['archive_worktree_root']=str(archive/'retired')
    reviewed['archive_mount']=str(archive)
    monkeypatch.setattr(storage,'policy',lambda _:reviewed)
    monkeypatch.setattr(storage,'capacity_gate',lambda p:('repair_allowed',{'root_percent':95,'archive_percent':5}))
    monkeypatch.setattr(storage,'ROOT',spool)
    monkeypatch.setattr(storage,'unused_build_cache_prune',lambda **kwargs:0)
    monkeypatch.setattr(storage,'candidates',lambda *a,**k:[(item,'a'*40)])
    monkeypatch.setattr(storage,'qualified',lambda *a,**k:True)
    monkeypatch.setattr(storage,'usage',lambda path:(5.0,200*storage.GIB,210*storage.GIB))
    def remove(*args,**kwargs):
        assert args[0:2]==('worktree','remove')
        shutil.rmtree(item)
        return subprocess.CompletedProcess(args,0,'','')
    monkeypatch.setattr(storage,'git',remove)
    report=storage.repair()
    assert report['status']=='archived_and_verified'
    assert report['archived_count']==1
    assert not item.exists()
    manifests=list((archive/'retired').glob('*.json'))
    assert len(manifests)==1
    rec=json.loads(manifests[0].read_text())
    assert rec['status']=='source_retired_by_git'
    assert rec['head']=='a'*40
    assert Path(rec['archive']).is_file()


def test_locked_cold_worktree_excluded(monkeypatch,tmp_path):
    root=tmp_path/'worktrees';root.mkdir()
    item=root/'really-old-detached';item.mkdir()
    os.utime(item,(time.time()-40*86400,)*2)
    out=f'worktree {item}\nHEAD {"a"*40}\ndetached\nlocked\n'
    monkeypatch.setattr(storage,'git',lambda *a,**k:subprocess.CompletedProcess(a,0,out,''))
    assert storage.candidates(root)==[]


def test_uncommitted_worktree_is_not_eligible(monkeypatch,tmp_path):
    src=tmp_path/'dirty';src.mkdir()
    sha='a'*40
    monkeypatch.setattr(storage,'active_reference',lambda p:False)
    calls=[subprocess.CompletedProcess([],0,sha+'\n',''),subprocess.CompletedProcess([],1,'',''),
           subprocess.CompletedProcess([],0,' M app.py\n','')]
    monkeypatch.setattr(storage,'git',lambda *a,**k:calls.pop(0))
    assert storage.qualified(src,sha) is False


def test_locked_with_reason_is_excluded(monkeypatch,tmp_path):
    root=tmp_path/'worktrees';root.mkdir()
    item=root/'really-old-detached';item.mkdir()
    os.utime(item,(time.time()-40*86400,)*2)
    out=f'worktree {item}\nHEAD {"a"*40}\ndetached\nlocked used-by-authorized-worker\n'
    monkeypatch.setattr(storage,'git',lambda *a,**k:subprocess.CompletedProcess(a,0,out,''))
    assert storage.candidates(root)==[]


def test_cache_prune_uses_exact_bounded_builder_and_validates_free_bytes(monkeypatch):
    calls=[]
    monkeypatch.setattr(storage,'active_build_processes',lambda:False)
    samples=iter([(95.0,10*storage.GIB,200*storage.GIB),(92.0,13*storage.GIB,200*storage.GIB)])
    monkeypatch.setattr(storage,'usage',lambda path:next(samples))
    def mockrun(args,**kwargs):
        calls.append((args,kwargs))
        return subprocess.CompletedProcess(args,0,'Total: 3GB','')
    monkeypatch.setattr(storage.subprocess,'run',mockrun)
    assert storage.unused_build_cache_prune()==3*storage.GIB
    assert calls[0][0]==['docker','buildx','prune','--builder','default','--filter','until=24h','--force']
    assert calls[0][1]['timeout']==90


def test_cache_prune_skips_active_build_without_mutation(monkeypatch):
    monkeypatch.setattr(storage,'active_build_processes',lambda:True)
    monkeypatch.setattr(storage.subprocess,'run',lambda *a,**k:pytest.fail('must not prune while build active'))
    assert storage.unused_build_cache_prune()==0


def test_cache_prune_rejects_unreviewed_parameters():
    with pytest.raises(ValueError,match='unreviewed'):
        storage.unused_build_cache_prune(hours=1)
