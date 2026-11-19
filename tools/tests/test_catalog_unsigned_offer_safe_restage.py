"""Catalog source-only restage: unrelated PMv4 merges never expand release scope."""
from __future__ import annotations
from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import catalog_scoped_promotion as contract
from tools import catalog_scoped_promotion_root as root
from tools.tests.test_catalog_scoped_promotion import offer as sample_offer


def encoded(item):
    return json.dumps(item,sort_keys=True,separators=(",",":")).encode()+b"\n"


def refresh(item):
    o=deepcopy(item)
    old=o["protected_main_sha"]
    o["protected_main_sha"]=("b"*40 if old!="b"*40 else "a"*40)
    o["fresh_admission_receipt_sha256"]="c"*64
    payload={k:v for k,v in o.items() if k!="manifest_sha256"}
    o["manifest_sha256"]=sha256(contract.canonical(payload)).hexdigest()
    contract.validate_offer(o)
    return o


@pytest.fixture
def host(tmp_path,monkeypatch):
    original=sample_offer()
    new=refresh(original)
    rootdir=tmp_path/"root"
    (rootdir/"offers").mkdir(parents=True)
    (rootdir/"transactions").mkdir(parents=True)
    auth=tmp_path/"authority"
    (auth/"offers").mkdir(parents=True)
    (auth/"owner-approvals").mkdir(parents=True)
    (auth/"offers").chmod(0o700)
    (rootdir/"offers"/(new["release_id"]+".json")).write_bytes(encoded(original))
    (auth/"offers"/(new["release_id"]+".json")).write_bytes(encoded(original))
    monkeypatch.setattr(root,"ROOT",rootdir)
    monkeypatch.setattr(root,"AUTH_ROOT",auth)
    monkeypatch.setattr(root.pwd,"getpwnam",lambda name:SimpleNamespace(pw_uid=os.getuid(),pw_gid=os.getgid()))
    monkeypatch.setattr(root,"secure_read",lambda path,**kw:Path(path).read_bytes())
    monkeypatch.setattr(root,"atomic_root_json",lambda path,item:Path(path).write_bytes(encoded(item)))
    old_lstat=Path.lstat
    def test_lstat(path):
        real=old_lstat(path)
        if path==rootdir/"superseded-source-only-offers":
            return SimpleNamespace(st_mode=real.st_mode,st_uid=0)
        return real
    monkeypatch.setattr(Path,"lstat",test_lstat)
    class Fake:
        repo=tmp_path
        opened=0
        breaker=[]
        @contextmanager
        def transaction_lock(self,offer):
            self.opened+=1
            yield
        def _frozen(self,offer):return {"frozen":True}
        def open_circuit_breaker(self,reason):self.breaker.append(reason)
    instance=Fake()
    def git_run(command,**kwargs):
        if "merge-base" in command:return SimpleNamespace(returncode=0,stdout=b"")
        if "ls-remote" in command:
            return SimpleNamespace(returncode=0,stdout=(new["protected_main_sha"]+"\trefs/heads/main\n").encode())
        pytest.fail("unexpected shell command")
    monkeypatch.setattr(root.subprocess,"run",git_run)
    return instance,original,new,rootdir,auth


def test_stale_unsigned_offer_refresh_preserves_candidate_and_exact_audit(host):
    fake,old,new,state,auth=host
    response=root._restage_unchanged_catalog_scope(fake,new)
    assert response["status"]=="catalog_unsigned_offer_restaged_without_production_mutation"
    assert response["owner_approval_required"] is True
    assert response["production_mutations"] is False
    assert fake.opened==1 and fake.breaker==[]
    for file in (state/"offers"/(new["release_id"]+".json"),auth/"offers"/(new["release_id"]+".json")):
        assert file.read_bytes()==encoded(new)
    assert (state/"superseded-source-only-offers"/(new["release_id"]+"-"+old["manifest_sha256"]+".json")).read_bytes()==encoded(old)
    assert not (auth/"owner-approvals"/(new["release_id"]+".json")).exists()
    assert not (state/"transactions"/(new["release_id"]+".json")).exists()


@pytest.mark.parametrize("existing",["owner-approvals","transactions","active"])
def test_restaging_fails_closed_after_any_approval_or_attempt(host,existing):
    fake,old,new,state,auth=host
    target={
        "owner-approvals":auth/"owner-approvals"/(new["release_id"]+".json"),
        "transactions":state/"transactions"/(new["release_id"]+".json"),
        "active":state/"active.json",
    }[existing]
    target.write_text("not authorized")
    with pytest.raises(PermissionError,match="OFFER_RESTAGE_EXISTING_APPROVAL_OR_TRANSACTION"):
        root._restage_unchanged_catalog_scope(fake,new)
    assert fake.opened==0
    assert (state/"offers"/(new["release_id"]+".json")).read_bytes()==encoded(old)


@pytest.mark.parametrize("field",[
    "candidate_sha","rollback_sha","runtime_image_id","mcp_image_id",
    "runtime_settings","mcp_settings","protected_containers","scope_sha256",
    "freeze_sha256","separate_owner_approval_required","no_global_owner_expansion",
])
def test_other_scope_may_not_change_under_source_only_refresh(host,field):
    fake,old,new,state,auth=host
    other=deepcopy(new)
    if isinstance(other[field],str):
        if field=="candidate_sha":
            other[field]="d"*40
            other["release_id"]="release-"+other[field][:16]
        elif field=="rollback_sha":
            other[field]="d"*40
        elif field.endswith("image_id"):
            other[field]="sha256:"+"f"*64
        else:
            other[field]="f"*64
    elif isinstance(other[field],dict):
        other[field]={"UNAPPROVED":"true"}
    elif isinstance(other[field],list):
        other[field]=["unapproved"]
    elif isinstance(other[field],bool):
        other[field]=False
    other["manifest_sha256"]=sha256(contract.canonical({k:v for k,v in other.items() if k!="manifest_sha256"})).hexdigest()
    with pytest.raises(Exception):
        root._restage_unchanged_catalog_scope(fake,other)
    assert fake.opened==0


def test_mismatched_public_and_root_offer_denied(host):
    fake,old,new,state,auth=host
    (auth/"offers"/(new["release_id"]+".json")).write_bytes(b'{"forged":true}\n')
    with pytest.raises(PermissionError,match="OFFER_RESTAGE_ROOT_PUBLIC_MISMATCH"):
        root._restage_unchanged_catalog_scope(fake,new)
    assert fake.opened==0


def test_second_write_failure_restores_both_exact_original_offers(host,monkeypatch):
    fake,old,new,state,auth=host
    native_replace=root.os.replace
    failed=False
    def fail_once(src,dest):
        nonlocal failed
        if not failed and str(dest).endswith(new["release_id"]+".json"):
            failed=True
            raise OSError("synthetic public atomic swap failure")
        return native_replace(src,dest)
    monkeypatch.setattr(root.os,"replace",fail_once)
    with pytest.raises(OSError,match="synthetic public atomic"):
        root._restage_unchanged_catalog_scope(fake,new)
    assert failed and fake.opened==1 and fake.breaker==[]
    assert (state/"offers"/(new["release_id"]+".json")).read_bytes()==encoded(old)
    assert (auth/"offers"/(new["release_id"]+".json")).read_bytes()==encoded(old)
    # The attempt preserves immutable audit of the rejected previous scope.
    assert (state/"superseded-source-only-offers"/(new["release_id"]+"-"+old["manifest_sha256"]+".json")).read_bytes()==encoded(old)


def test_reject_source_main_that_is_not_descendant(host,monkeypatch):
    fake,old,new,state,auth=host
    def no_ancestor(command,**kwargs):
        return SimpleNamespace(returncode=1,stdout=b"")
    monkeypatch.setattr(root.subprocess,"run",no_ancestor)
    with pytest.raises(PermissionError,match="OFFER_RESTAGE_MAIN_NOT_DESCENDANT"):
        root._restage_unchanged_catalog_scope(fake,new)
    assert fake.opened==0


def test_root_stage_routes_existing_stale_offer_only_to_controlled_restage(monkeypatch,host):
    fake,old,new,state,auth=host
    calls=[]
    monkeypatch.setattr(root,"NativeCatalogHost",lambda repo:fake)
    monkeypatch.setattr(root,"CatalogPMv4ProtectedHost",lambda repo:fake)
    fake.enforce_installed_production_trust=lambda:None
    monkeypatch.setattr(root,"attest_source_scope",lambda repo,**kw:{"protected_source":{"verified_main_sha":new["protected_main_sha"]}})
    monkeypatch.setattr(root,"load_manifest",lambda *args,**kw:{"snapshot_sha":new["candidate_sha"]})
    monkeypatch.setattr(root,"make_offer",lambda *args,**kwargs:new)
    monkeypatch.setattr(root,"_root_offer_path",lambda _:state/"offers"/(new["release_id"]+".json"))
    monkeypatch.setattr(root,"_trusted_public_offer",lambda _:pytest.fail("unsafe ordinary root offer overwrite"))
    monkeypatch.setattr(root,"_restage_unchanged_catalog_scope",lambda host,payload:calls.append(payload) or {"status":"controlled_restage"})
    historical=(Path(__file__).resolve().parents[2]/
                root.ADMISSION_EVIDENCE_PATH).read_bytes()
    def read_in_ci(path,**kw):
        if str(path).endswith(root.ADMISSION_EVIDENCE_PATH):
            return historical
        return Path(path).read_bytes()
    monkeypatch.setattr(root,"secure_read",read_in_ci)
    request={
        "schema_version":"1.0","action":"catalog_scope_stage",
        "request_id":"1"*32,"source_revision":new["protected_main_sha"],
        "release_id":new["release_id"],
        "admission_receipt_sha256":root.ADMISSION_RECEIPT_SHA256
    }
    assert root.execute_native_catalog_scoped_request(request,repo=state,native_ci_checks=lambda *_:{})=={"status":"controlled_restage"}
    assert calls==[new]
