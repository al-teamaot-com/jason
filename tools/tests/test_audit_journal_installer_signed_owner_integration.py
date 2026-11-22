"""Actual installer CLI stage and adopt call graph, all prod effects mocked."""
from __future__ import annotations
from contextlib import nullcontext
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import json
import sys
from unittest import mock
import pytest
from tools import audit_journal_install as install
from tools import audit_journal_signed_owner_bridge as bridge

CANDIDATE="a"*40
SCOPE={"action":bridge.ACTION,"policy":{
    "candidate_sha":CANDIDATE,"rollback_sha":bridge.ROLLBACK},
    "source_dataset_identity":{"device":3,"inode":7}}
BEFORE={"jason-runtime":{"Id":"fixture"}}
ORIGINAL=b'{"protected":"policy"}'
DESIRED={"protected":"policy","archive":"reviewed"}
OWN={"owner_oid":bridge.OWNER,"candidate_sha":CANDIDATE,
     "scope_sha256":bridge.digest(bridge.canon(SCOPE)),
     "same_scope_recheck_passed":True,"new_global_unfreeze":False,
     "approval_id":"owner-mcp-"+"e"*32}

def fit(tmp_path,monkeypatch,mode,*,fail_signed=False,change_scope=False):
    rec=[]
    path=Path(tmp_path/"source")
    path.mkdir()
    fake_bridge=SimpleNamespace(
        create_staged_offer=lambda *args:(
           rec.append(("root-stage-offer",args)),
           {"release_id":"release-"+CANDIDATE[:16],
            "scope_sha256":bridge.digest(bridge.canon(SCOPE)),
            "manifest_sha256":"d"*64})[1],
        verify_previously_signed_root_offer=lambda *args:(
           rec.append(("verify-real-owner-signature",args)),
           (_ for _ in ()).throw(PermissionError("missing signed approval"))
           if fail_signed else dict(OWN))[1],
        consume_one_use=lambda *args:rec.append(("one-use-owner-claim",args)),
    )
    fake_scope=SimpleNamespace(
       OWNER=bridge.OWNER,digest=lambda s:bridge.digest(bridge.canon(s)))
    modules={
       "audit_journal_release_scope":fake_scope,
       "audit_journal_container_release":SimpleNamespace(),
       "audit_journal_root_inventory":SimpleNamespace(),
       "pmv4_e_ci_refresh":SimpleNamespace(),
       "audit_journal_signed_owner_bridge":fake_bridge,
    }
    auth={"locks":lambda:nullcontext(),
          "owner":lambda *args:pytest.fail("No command-line Owner device authentication")}
    monkeypatch.setattr(install,"primitives",lambda *args:({},auth))
    monkeypatch.setattr(install,"staged_modules",lambda *args:(
        SimpleNamespace(cleanup=lambda:rec.append(("clean-releases",None))),
        {"source":"synthetic"},modules))
    monkeypatch.setattr(install,"ci",lambda *args:{"required_ci_passed":True})
    def fake_inspect(*args):
        result=dict(SCOPE)
        if change_scope and rec and rec[-1][0]=="verify-real-owner-signature":
            result["data_mutated"]=True
        rec.append(("live-root-inspect",None))
        return result,BEFORE,ORIGINAL,DESIRED
    monkeypatch.setattr(install,"inspect",fake_inspect)
    monkeypatch.setattr(install,"git",lambda *args:
        CANDIDATE if args==("rev-parse","HEAD") else "")
    monkeypatch.setattr(install.os,"geteuid",lambda:0)
    args=["audit_journal_install.py","--candidate-sha",CANDIDATE,mode]
    monkeypatch.setattr(sys,"argv",args)
    monkeypatch.setattr(install,"sys",SimpleNamespace(
        flags=SimpleNamespace(isolated=1),argv=args))
    monkeypatch.setattr(install,"save_record",lambda *args,**kw:
        rec.append(("immutable-root-approved-record",kw)))
    monkeypatch.setattr(install,"install",lambda *args,**kw:
        rec.append(("original-reviewed-install",args)))
    return rec

def test_original_signed_root_offer_stages_without_migration(tmp_path,monkeypatch,capsys):
    rec=fit(tmp_path,monkeypatch,"--stage-signed-owner-offer")
    install.main()
    names=[name for name,_ in rec]
    assert names==["live-root-inspect","root-stage-offer","clean-releases"]
    stage_args=[args for name,args in rec if name=="root-stage-offer"][0]
    assert stage_args[2]["dataset_identity"]==SCOPE["source_dataset_identity"]
    output=capsys.readouterr().out
    assert "GLOBAL_PRODUCTION_FREEZE_REMAINS_ACTIVE=true" in output
    assert "NO_DATABASE_OR_PROVIDER_MUTATIONS=true" in output

def test_verified_signed_owner_is_required_before_exact_root_transaction(
        tmp_path,monkeypatch):
    rec=fit(tmp_path,monkeypatch,"--adopt-signed-chatgpt-owner")
    install.main()
    assert [name for name,_ in rec]==[
        "live-root-inspect","verify-real-owner-signature",
        "live-root-inspect","immutable-root-approved-record",
        "one-use-owner-claim","original-reviewed-install",
        "clean-releases"]
    verify_args=[args for name,args in rec if name=="verify-real-owner-signature"][0]
    assert verify_args[2]["dataset_identity"]==SCOPE["source_dataset_identity"]
    claim=[args for name,args in rec if name=="immutable-root-approved-record"]
    assert claim[0]["signed_owner"]["approval_id"]==OWN["approval_id"]

def test_unapproved_signed_owner_denied_before_any_root_mutation(
        tmp_path,monkeypatch):
    rec=fit(tmp_path,monkeypatch,"--adopt-signed-chatgpt-owner",
            fail_signed=True)
    with pytest.raises(PermissionError,match="missing signed approval"):
        install.main()
    assert [name for name,_ in rec]==[
        "live-root-inspect","verify-real-owner-signature","clean-releases"]

def test_changed_live_scope_denied_before_claim_or_migration(tmp_path,monkeypatch):
    rec=fit(tmp_path,monkeypatch,"--adopt-signed-chatgpt-owner",
            change_scope=True)
    with pytest.raises(PermissionError,match="LIVE_REVIEWED_SCOPE_CHANGED"):
        install.main()
    assert not any(name in ("immutable-root-approved-record","one-use-owner-claim",
                            "original-reviewed-install") for name,_ in rec)

def test_installer_source_closure_pins_signed_owner_verifier_code():
    assert "tools/audit_journal_signed_owner_bridge.py" in install.EXTRA
    assert "implementation/kernel/signed_owner_release.py" in install.EXTRA
    body=Path(install.__file__).read_text()
    assert "bridge.verify_previously_signed_root_offer" in body
    assert "bridge.consume_one_use" in body
    assert "GLOBAL_PRODUCTION_FREEZE_REMAINS_ACTIVE" in body
    assert "signed_chatgpt_owner_approval" in body


def test_actual_reviewed_scope_schema_has_source_dataset_identity_not_fake_alias():
    from tools import audit_journal_release_scope as scope
    reviewed=scope.reviewed_scope(CANDIDATE,{}, {}, {}, {
        "dataset_identity":{"device":3,"inode":7},
        "producer_before":{},"producer_after":{},
        "desired_after_sha256":"f"*64,
        "archive_root_metadata":{"uid":1000,"gid":984,"mode":"0o2770"},
    })
    assert reviewed["source_dataset_identity"]==SCOPE["source_dataset_identity"]
    assert "dataset_identity" not in reviewed
