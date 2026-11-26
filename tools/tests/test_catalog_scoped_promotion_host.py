"""Proof that root-conditional code refuses source checkout execution and drift."""
from __future__ import annotations
import json
from pathlib import Path
from copy import deepcopy
import os
import stat
from types import SimpleNamespace
import pytest

from tools import catalog_scoped_promotion as p
from tools import catalog_scoped_promotion_host as h
from tools import catalog_scoped_promotion_request as q
from tools import catalog_scoped_promotion_root as root
from tools import catalog_scoped_control_readback as readback
from tools.tests.catalog_scoped_v2_fixture import synthetic_fresh_v2

ROOT=Path(__file__).resolve().parents[2]
MANIFEST=json.loads((ROOT/"config/catalog-scoped-release-admission.json").read_text())
HISTORICAL=json.loads((ROOT/p.ADMISSION_EVIDENCE_PATH).read_text())


def offer():return p.make_offer(MANIFEST,HISTORICAL,synthetic_fresh_v2(MANIFEST,HISTORICAL))


def test_root_host_denies_developer_checkout_execution():
    with pytest.raises(p.ScopedPromotionDenied,match="ROOT_INSTALLED_EXECUTION_REQUIRED"):
        h.NativeCatalogHost().enforce_installed_production_trust()


def test_root_request_exact_schema_no_auto_approval():
    o=offer()
    staged=q.exact_request("catalog_scope_stage",release_id=o["release_id"],source_revision=o["protected_main_sha"])
    assert staged["admission_receipt_sha256"]==p.ADMISSION_RECEIPT_SHA256
    assert "signed_owner_proof" not in staged
    assert "offer_sha256" not in staged
    for action in ("catalog_scope_promote","catalog_scope_recover"):
        req=q.exact_request(action,release_id=o["release_id"],
                            source_revision=o["protected_main_sha"],
                            offer_sha256=o["manifest_sha256"])
        assert req["offer_sha256"]==o["manifest_sha256"]
        assert "owner-approved" not in json.dumps(req)
    with pytest.raises(p.ScopedPromotionDenied):
        q.exact_request("catalog_scope_promote",release_id=o["release_id"],
                        source_revision=o["protected_main_sha"])
    with pytest.raises(p.ScopedPromotionDenied):
        q.exact_request("catalog_scope_stage",release_id=o["release_id"],
                        source_revision=o["protected_main_sha"],offer_sha256=o["manifest_sha256"])
    with pytest.raises(p.ScopedPromotionDenied):
        q.exact_request("all-containers",release_id=o["release_id"],
                        source_revision=o["protected_main_sha"])


def test_uninstalled_root_worker_denies_native_submission(tmp_path):
    o=offer()
    req=q.exact_request("catalog_scope_stage",release_id=o["release_id"],source_revision=o["protected_main_sha"])
    with pytest.raises(p.ScopedPromotionDenied,match="ROOT_WORKER_NOT_INSTALLED"):
        q.submit_to_native_worker(tmp_path,req,worker_path=tmp_path/"not-installed")
    assert list(tmp_path.rglob("*.json"))==[]


def test_attacker_cannot_substitute_root_worker_with_untrusted_owner(tmp_path):
    script=tmp_path/"worker.py"
    script.write_text("catalog_scope_promote _trusted_catalog_scoped_promotion_module")
    assert script.stat().st_uid==os.getuid()
    if os.getuid()!=0:
        with pytest.raises(p.ScopedPromotionDenied,match="ROOT_WORKER_UNTRUSTED"):
            q.root_worker_installed(script=script)


def test_strict_scoped_control_readback_honors_original_baseline():
    o=offer()
    overlay={
        "schema_version":"1.0","authorization":"owner_signed_catalog_scoped_dual_image",
        "release_id":o["release_id"],"snapshot_sha":o["candidate_sha"],
        "host_revision":o["rollback_sha"],"scope_sha256":o["scope_sha256"],
        "manifest_sha256":o["manifest_sha256"],
        "runtime_image_id":o["runtime_image_id"],"mcp_image_id":o["mcp_image_id"],
        "rollback_runtime_image_id":o["rollback_runtime_image_id"],
        "rollback_mcp_image_id":o["rollback_mcp_image_id"],
        "freeze_sha256":o["freeze_sha256"],
        "approval_id":"owner-mcp-"+"a"*32,
        "owner_principal":"person-entra-bee80bdcffb04c50b453c09d4d411f5f",
        "protected_containers":list(p.PROTECTED_CONTAINERS),
        "status":"scoped_pair_readback_pending","recorded_at":"2026-11-17T00:00:00Z",
        "global_owner_allowlist_unchanged":True,
    }
    live={"host_revision":o["rollback_sha"],"runtime_revision":o["candidate_sha"],
          "mcp_revision":o["candidate_sha"],"runtime_image_id":o["runtime_image_id"],
          "mcp_image_id":o["mcp_image_id"],"runtime_healthy":True,
          "mcp_running":True,"runtime_catalog_auth_mode":"jason_managed",
          "mcp_catalog_grant_profile":"aot-catalog-self-owner-v1",
          "global_owner_allowlist":"person-al",
          "protected_services":{name:True for name in p.PROTECTED_CONTAINERS}}
    control={"circuit_breaker":{"state":"closed"},
             "last_known_good":{"manifest":{"revision":o["rollback_sha"]}}}
    receipt=readback.verify_root_readback(offer=o,overlay=overlay,live=live,
             freeze_sha256=None,original_breaker=control,phase="inside_exact_release_lock")
    assert receipt["status"]=="scoped_readback_pass_not_global_source_alignment"
    for field,value in (("runtime_revision",o["rollback_sha"]),
                        ("global_owner_allowlist","person-everyone"),
                        ("host_revision",o["candidate_sha"]),
                        ("runtime_healthy",False)):
        modified=deepcopy(live);modified[field]=value
        with pytest.raises(p.ScopedPromotionDenied):
            readback.verify_root_readback(offer=o,overlay=overlay,live=modified,
                freeze_sha256=None,original_breaker=control,phase="inside_exact_release_lock")
    with pytest.raises(p.ScopedPromotionDenied,match="CONTROL_FREEZE_DRIFT"):
        readback.verify_root_readback(offer=o,overlay=overlay,live=live,
            freeze_sha256="0"*64,original_breaker=control,phase="steady_frozen")


def test_root_action_requires_trusted_installer_even_for_stage(monkeypatch):
    o=offer()
    request={"schema_version":"1.0","action":"catalog_scope_stage",
        "request_id":"1"*32,"source_revision":o["protected_main_sha"],
        "release_id":o["release_id"],
        "admission_receipt_sha256":p.ADMISSION_RECEIPT_SHA256}
    with pytest.raises(p.ScopedPromotionDenied,match="ROOT_INSTALLED_EXECUTION_REQUIRED"):
        root.execute_native_catalog_scoped_request(request)
    assert "approval" not in json.dumps(request)


def test_interrupted_native_create_restores_renamed_baseline(monkeypatch):
    o=offer();host=h.NativeCatalogHost();actions=[]
    rollback=h.inspect_container
    old_id='source-container-before-change'
    orig={
        'jason-runtime':{'Image':o['rollback_runtime_image_id'],'Config':{'Labels':{
            'com.teamaot.jason.source_revision':o['rollback_sha']}},
            'State':{'Running':True},'Id':old_id},
        'jason-mcp-pilot':{'Image':o['rollback_mcp_image_id'],'Config':{'Labels':{
            'com.teamaot.jason.source_revision':o['rollback_sha']}},
            'State':{'Running':True},'Id':'old-mcp'},
    }
    retained_name='jason-runtime-rollback-catalog-'+o['candidate_sha'][:12]
    names=dict(orig)
    names.pop('jason-runtime')
    names[retained_name]=orig['jason-runtime']
    def inspect(name):
        if name not in names:raise p.ScopedPromotionDenied('CONTAINER_NOT_FOUND')
        return names[name]
    def execute(*parts,timeout=480):
        actions.append(parts)
        if parts[0]=='rename':
            names[parts[2]]=names.pop(parts[1])
        elif parts[0]=='start':
            names[parts[1]]['State']['Running']=True
        elif parts[0]=='rm':
            names.pop(parts[-1],None)
    monkeypatch.setattr(h,'inspect_container',inspect)
    monkeypatch.setattr(h,'docker_run',execute)
    monkeypatch.setattr(host,'_journal_status',lambda *args,**kw:None)
    host.rollback_both(o)
    assert names['jason-runtime']['Image']==o['rollback_runtime_image_id']
    assert any(x[0]=='rename' for x in actions)
    assert not any(x[0]=='rm' for x in actions)


def test_unknown_live_image_never_removed_on_recovery(monkeypatch):
    o=offer();host=h.NativeCatalogHost();actions=[]
    first={'Image':'sha256:'+'0'*64,'Config':{'Labels':{
        'com.teamaot.jason.source_revision':o['rollback_sha']}},'State':{'Running':True}}
    monkeypatch.setattr(h,'inspect_container',lambda name:first)
    monkeypatch.setattr(h,'docker_run',lambda *args,**kw:actions.append(args))
    with pytest.raises(p.ScopedPromotionDenied,match='UNKNOWN_LIVE_IMAGE_CANNOT_ROLLBACK'):
        host.rollback_both(o)
    assert actions==[]


def test_root_watcher_refuses_uninstalled_source(monkeypatch):
    from tools import catalog_scoped_promotion_recovery as recovery
    with pytest.raises(p.ScopedPromotionDenied,match='RECOVERY_ROOT_INSTALLED_EXECUTION_REQUIRED'):
        recovery.run_once()


def test_root_recovery_handles_crash_before_first_freeze_backup(monkeypatch, tmp_path):
    """A journal alone never implies the native helper touched production."""
    from contextlib import nullcontext
    o=offer()
    native=h.NativeCatalogHost(root=tmp_path)
    protected={name:{'id':'original','started_at':'earlier','image':'pinned'}
               for name in p.PROTECTED_CONTAINERS}
    events=[]
    journal={'release_id':o['release_id'],'candidate_sha':o['candidate_sha'],
             'rollback_sha':o['rollback_sha'],'scope_sha256':o['scope_sha256'],
             'manifest_sha256':o['manifest_sha256'],
             'status':'owner_approval_consumed_no_mutation',
             'protected_services_before':protected}
    monkeypatch.setattr(native,'enforce_installed_production_trust',lambda:None)
    monkeypatch.setattr(native,'transaction_lock',lambda offer:nullcontext())
    monkeypatch.setattr(native,'_journal',lambda offer:dict(journal))
    monkeypatch.setattr(native,'open_circuit_breaker',lambda code:events.append('breaker'))
    monkeypatch.setattr(native,'_frozen',lambda offer:events.append('freeze_verified'))
    monkeypatch.setattr(native,'verify_rollback_and_host',lambda offer:events.append('original_images_verified'))
    monkeypatch.setattr(native,'verify_unchanged_protected_containers',lambda original:events.append('protected_services_verified'))
    monkeypatch.setattr(native,'clear_scoped_control_readback',lambda offer:events.append('overlay_absent'))
    monkeypatch.setattr(native,'_journal_status',lambda offer,status,**kw:events.append(status))
    monkeypatch.setattr(native,'rollback_both',lambda offer:pytest.fail('unexpected Docker write before backup'))
    reply=native.recover_interrupted(o)
    assert reply['status']=='interrupted_before_unfreeze_verified'
    assert reply['circuit_breaker_remains_open'] is True
    assert events.count('freeze_verified')==2
    assert 'original_images_verified' in events
    assert 'protected_services_verified' in events
    assert events[-1]=='interrupted_before_unfreeze_verified'


def test_missing_freeze_backup_after_mutation_fails_closed(monkeypatch,tmp_path):
    from contextlib import nullcontext
    o=offer();native=h.NativeCatalogHost(root=tmp_path)
    protected={name:{} for name in p.PROTECTED_CONTAINERS}
    journal={'release_id':o['release_id'],'candidate_sha':o['candidate_sha'],
        'rollback_sha':o['rollback_sha'],'scope_sha256':o['scope_sha256'],
        'manifest_sha256':o['manifest_sha256'],'status':'mutating_jason_runtime',
        'protected_services_before':protected}
    evidence=[]
    monkeypatch.setattr(native,'enforce_installed_production_trust',lambda:None)
    monkeypatch.setattr(native,'transaction_lock',lambda offer:nullcontext())
    monkeypatch.setattr(native,'_journal',lambda offer:dict(journal))
    monkeypatch.setattr(native,'open_circuit_breaker',lambda reason:evidence.append('breaker_open'))
    monkeypatch.setattr(native,'rollback_both',lambda offer:pytest.fail('cannot infer rollback backup'))
    with pytest.raises(p.ScopedPromotionDenied,match='RECOVERY_FREEZE_BACKUP_MISSING_AFTER_MUTATION'):
        native.recover_interrupted(o)
    assert evidence==['breaker_open']


def test_root_rechecks_protected_ci_at_promotion_not_only_staging(monkeypatch,tmp_path):
    o=offer()
    native=h.NativeCatalogHost(repo=tmp_path)
    native.policy={'native_root_control_supported':True}
    monkeypatch.setattr(h,'load_manifest',lambda repo,**kw:MANIFEST)
    monkeypatch.setattr(h,'verified_source_scope',lambda repo,manifest,**kw:
        {'verified_main_sha':o['protected_main_sha']})
    from tools import catalog_scoped_protected_ci
    monkeypatch.setattr(catalog_scoped_protected_ci,'check_catalog_protected_ci',
        lambda sha,**kw:{'passed':False,'failures':['governed-security-regressions:failure']})
    monkeypatch.setattr(native,'_frozen',lambda offer:pytest.fail('freeze readback after failed CI'))
    monkeypatch.setattr(h,'verify_native_preflights',lambda offer:pytest.fail('Docker preflight after failed CI'))
    with pytest.raises(p.ScopedPromotionDenied,match='LIVE_PROTECTED_SECURITY_CI_NOT_GREEN'):
        native.fresh_source_and_live_admission(o)
    assert native.freeze_before is None


def test_protected_root_breaker_control_cannot_be_written_as_operator():
    if os.geteuid()!=0:
        with pytest.raises(p.ScopedPromotionDenied,match='ROOT_CONTROL_WRITER_REQUIRES_ROOT'):
            h.atomic_root_protected_control({'schema_version':'1.0'})
