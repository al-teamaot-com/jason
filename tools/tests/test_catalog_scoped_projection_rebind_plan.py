"""Source-only exact two-file catalog worker/projection update planning.

No privileged apply, owner signature minting, desired-state modification,
image promotion or provider write in this planning module.
"""
from __future__ import annotations
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import json
import stat
import pytest

from tools import catalog_scoped_projection_rebind_plan as p
from tools.catalog_scoped_root_install_plan import canonical
from tools.tests.test_catalog_scoped_root_install_plan import mock_source
from tools import catalog_scoped_root_install_plan as earlier

MAIN='a'*40


@pytest.fixture
def case(tmp_path,monkeypatch,mock_source):
    offer,host=mock_source
    old=earlier.build_install_plan(tmp_path,{},{},host,expected_source_sha=earlier.repo_revision(tmp_path))
    worker=tmp_path/'root-worker-original'
    worker.write_bytes(b'original fixed worker source')
    worker.chmod(0o755)
    freeze=tmp_path/'original-freeze'
    freeze.write_bytes(b'original active freeze bytes')
    freeze.chmod(0o600)
    original=old['root_policy_after_separate_approval']
    original['root_worker_sha256']=sha256(worker.read_bytes()).hexdigest()
    old['root_file_plan'][next(i for i,e in enumerate(old['root_file_plan'])
        if e['destination']==str(p.WORKER))]['sha256']=original['root_worker_sha256']
    old['freeze_sha256']=sha256(freeze.read_bytes()).hexdigest()
    old['install_plan_sha256']=sha256(canonical({k:v for k,v in old.items()
                                              if k!='install_plan_sha256'})).hexdigest()
    untrusted_old_lstat=Path.lstat
    def root_owned_lstat(obj):
        meta=untrusted_old_lstat(obj)
        if obj==worker:
            return SimpleNamespace(st_uid=0,st_mode=stat.S_IFREG|0o755,st_nlink=1)
        return meta
    monkeypatch.setattr(Path,'lstat',root_owned_lstat)
    monkeypatch.setattr(p,'PROJECTION',tmp_path/'not-installed-projection')
    blobs={
        'tools/release_host_reconcile_worker.py':b'"tools/pmv4_mcp_projection.py"',
        'tools/pmv4_mcp_projection.py':b'EXACT_MOUNTS=("root-owned",)',
        'tools/deploy_live_container.py':b'from pmv4_mcp_projection import (\n--preflight',
    }
    def get(repo,*args):
        assert args[0]=='show' and args[1].startswith(MAIN+':')
        return blobs[args[1].split(':',1)[1]]
    return old,worker,freeze,get,blobs


def test_exact_plan_is_deterministic_and_never_authorizes_elevation(case,tmp_path):
    old,worker,freeze,git,blobs=case
    a=p.build(tmp_path,old,installed_worker=worker,freeze=freeze,
              source_main_sha=MAIN,git_blob=git)
    b=p.build(tmp_path,old,installed_worker=worker,freeze=freeze,
              source_main_sha=MAIN,git_blob=git)
    assert a==b
    assert a['status']=='SOURCE_ONLY_REBIND_PREP_NOT_AUTHORIZED'
    assert len(a['root_install_targets'])==2
    assert a['root_install_targets'][0]['destination']==str(p.WORKER)
    assert a['root_install_targets'][1]['destination']==str(p.PROJECTION)
    assert a['updated_root_policy_exactly']['source_sha']==MAIN
    assert a['updated_root_policy_exactly']['root_worker_sha256']==sha256(blobs['tools/release_host_reconcile_worker.py']).hexdigest()
    old_policy=old['root_policy_after_separate_approval']
    for k in old_policy:
        if k not in ('source_sha','root_worker_sha256'):
            assert a['updated_root_policy_exactly'][k]==old_policy[k]
    assert a['requires_bootstrap_recovery_supersession'] is True
    assert a['bootstrap_recovery_timer_retirement_separately_approved'] is False
    assert a['existing_bootstrap_recovery_timer']=='jason-catalog-root-bootstrap-recovery.timer'
    assert a['catalog_recovery_timer_must_remain_active'] is True
    assert a['requires_rollback_of_bootstrap_timer_on_failure'] is True
    assert a['requires_four_unit_drift_reconciled'] is True
    assert a['requires_native_breaker_closed'] is True
    assert a['requires_fresh_signed_exact_owner'] is True
    assert a['requires_native_production_lock'] is True
    assert a['production_mutations'] is False
    assert a['provider_write_authorized'] is False
    assert a['runtime_mcp_promotion_authorized'] is False
    assert a['signed_owner_proof_attached'] is False
    assert a['plan_sha256']==sha256(canonical({k:v for k,v in a.items()
                                              if k!='plan_sha256'})).hexdigest()


def test_disallow_missing_verified_projection_source(case,tmp_path):
    old,worker,freeze,git,blobs=case
    def incomplete(repo,*args):
        if args[1].endswith(':tools/release_host_reconcile_worker.py'):
            return b'worker without pinned projection'
        return git(repo,*args)
    with pytest.raises(p.CatalogProjectionRebindDenied,match='WORKER_DOES_NOT_PIN_PROJECTION'):
        p.build(tmp_path,old,installed_worker=worker,freeze=freeze,source_main_sha=MAIN,git_blob=incomplete)


def test_installed_projection_already_exists_requires_review(case,tmp_path):
    old,worker,freeze,git,blobs=case
    p.PROJECTION.write_text('unexpected already installed')
    with pytest.raises(p.CatalogProjectionRebindDenied,match='PROJECTION_ALREADY_INSTALLED'):
        p.build(tmp_path,old,installed_worker=worker,freeze=freeze,source_main_sha=MAIN,git_blob=git)


def test_original_root_worker_or_freeze_drift_denied(case,tmp_path):
    old,worker,freeze,git,blobs=case
    worker.write_bytes(b'changed root worker')
    with pytest.raises(p.CatalogProjectionRebindDenied,match='INSTALLED_ROOT_WORKER_NOT_ORIGINAL_APPROVED'):
        p.build(tmp_path,old,installed_worker=worker,freeze=freeze,source_main_sha=MAIN,git_blob=git)
    worker.write_bytes(b'original fixed worker source')
    freeze.write_bytes(b'changed original freeze')
    with pytest.raises(p.CatalogProjectionRebindDenied,match='ORIGINAL_FREEZE_CHANGED'):
        p.build(tmp_path,old,installed_worker=worker,freeze=freeze,source_main_sha=MAIN,git_blob=git)


def test_old_plan_is_digested_and_forged_authority_denied(case,tmp_path):
    old,worker,freeze,git,blobs=case
    path=tmp_path/'old-install-plan.json'
    path.write_text(json.dumps(old))
    assert p.read_old_root_plan(path)['source_sha']==old['source_sha']
    copy=deepcopy(old);copy['production_mutations']=True
    path.write_text(json.dumps(copy))
    with pytest.raises(p.CatalogProjectionRebindDenied,match='OLD_APPROVED_PLAN_HASH_INVALID'):
        p.read_old_root_plan(path)


def test_new_plan_cannot_be_its_own_rollback(case,tmp_path):
    old,worker,freeze,git,blobs=case
    with pytest.raises(p.CatalogProjectionRebindDenied,match='SOURCE_ONLY_UPDATE_NOT_NEEDED'):
        p.build(tmp_path,old,installed_worker=worker,freeze=freeze,
                source_main_sha=old['source_sha'],git_blob=git)
