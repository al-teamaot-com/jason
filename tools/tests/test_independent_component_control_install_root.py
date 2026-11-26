"""Offline, fail-closed tests for minimum no-MCP-swap root install."""
from __future__ import annotations
import json
import os
from pathlib import Path
import stat
import pytest
from tools import independent_component_control_install_root as root

REPO = Path(__file__).resolve().parents[1]

def scoped_synthetic_stage(monkeypatch, tmp_path):
    stage = tmp_path / ("component-controller-install-" + "a"*12)
    stage.mkdir(mode=0o700)
    monkeypatch.setattr(root,"STAGE_ROOT",tmp_path)
    monkeypatch.setattr(root,"STAGE_UID",os.getuid())
    hashes={}
    for name in root.PINNED:
        body=("synthetic:" + name).encode()
        path=stage/name
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        path.write_bytes(body)
        path.chmod(0o400)
        hashes[name]=root.digest(body)
    monkeypatch.setattr(root,"PINNED",hashes)
    own=b"temporary fake root source"
    p=stage/root.SOURCE_FILE
    p.write_bytes(own)
    p.chmod(0o400)
    manifest={
        "schema_version":"1.0","action":root.ACTION,"source_sha":"a"*40,
        "rollback_sha":root.LKG,"controller_sha":root.SOURCE_CONTROLLER,
        "prior_authorization_scope_sha256":root.PREVIOUS_SCOPE,
        "freeze_sha256":root.FREEZE_HASH,"mcp_baseline_image":root.MCP_IMAGE,
        "new_mcp_image_deployed":False,"financial_scheduler_started":False,
        "one_use":True,"root_source_sha256":root.digest(own),
        "files_sha256":hashes,
    }
    manifest["scope_sha256"]=root.digest(root.canonical(manifest))
    p=stage/"manifest.json"
    p.write_text(json.dumps(manifest))
    p.chmod(0o400)
    for directory in stage.rglob("*"):
        if directory.is_dir():
            directory.chmod(0o700)
    return stage,manifest

def test_successful_scoped_stage_without_signature(tmp_path,monkeypatch):
    stage,manifest=scoped_synthetic_stage(monkeypatch,tmp_path)
    got,blobs=root.load_stage(stage,with_proof=False)
    assert got==manifest
    assert set(blobs)=={"manifest.json",root.SOURCE_FILE,*root.PINNED}

def test_requires_owner_signature_for_mutation(tmp_path,monkeypatch):
    stage,_=scoped_synthetic_stage(monkeypatch,tmp_path)
    with pytest.raises(root.Denied,match="INSTALL_STAGE_EXTRA_FILES"):
        root.load_stage(stage,with_proof=True)

def test_rejects_extra_files_and_mutated_blob(tmp_path,monkeypatch):
    stage,_=scoped_synthetic_stage(monkeypatch,tmp_path)
    x=stage/"extra.txt";x.write_text("extra");x.chmod(0o400)
    with pytest.raises(root.Denied,match="EXTRA_FILES"):
        root.load_stage(stage,with_proof=False)
    x.unlink()
    path=stage/next(iter(root.PINNED))
    path.chmod(0o600);path.write_text("tampered");path.chmod(0o400)
    with pytest.raises(root.Denied,match="UNREVIEWED_SOURCE"):
        root.load_stage(stage,with_proof=False)

def test_invalid_mcp_swap_or_schedule_denied(tmp_path,monkeypatch):
    stage,manifest=scoped_synthetic_stage(monkeypatch,tmp_path)
    path=stage/"manifest.json"
    for key in ("new_mcp_image_deployed","financial_scheduler_started"):
        wrong=dict(manifest);wrong[key]=True
        wrong.pop("scope_sha256")
        wrong["scope_sha256"]=root.digest(root.canonical(wrong))
        path.chmod(0o600);path.write_text(json.dumps(wrong));path.chmod(0o400)
        with pytest.raises(root.Denied,match="INSTALL_SCOPE_DENIED"):
            root.load_stage(stage,with_proof=False)
    wrong=dict(manifest);wrong["scope_sha256"]="0"*64
    path.chmod(0o600);path.write_text(json.dumps(wrong));path.chmod(0o400)
    with pytest.raises(root.Denied,match="SCOPE_HASH_MISMATCH"):
        root.load_stage(stage,with_proof=False)

def test_root_execution_cannot_run_as_regular_user(monkeypatch,tmp_path):
    monkeypatch.setattr(root.os,"geteuid",lambda:1000)
    with pytest.raises(root.Denied,match="ISOLATED_ROOT_REQUIRED"):
        root.execute(tmp_path)

def test_filesystem_install_is_only_component_scoped(tmp_path,monkeypatch):
    trust=tmp_path/"opt/jason/independent-component-release/trusted"
    state=tmp_path/"var/lib/jason/independent-component-release"
    profile=tmp_path/"etc/jason/independent-component-release/host-profiles.json"
    outbox=tmp_path/"release-manager"
    financial=tmp_path/"var/lib/jason/financial-statements"
    for base in (trust.parent.parent,state.parent,profile.parent.parent,outbox,
                 financial.parent):base.mkdir(parents=True,exist_ok=True)
    monkeypatch.setattr(root,"ROOT",trust.parent)
    monkeypatch.setattr(root,"TRUST",trust)
    monkeypatch.setattr(root,"STATE",state)
    monkeypatch.setattr(root,"PROFILE",profile)
    monkeypatch.setattr(root,"OWNER_OUTBOX",outbox)
    monkeypatch.setattr(root,"FIN_STATE",financial)
    monkeypatch.setattr(root.os,"chown",lambda *args,**kwargs:None)
    blobs={name:("controlled:"+name).encode() for name in root.PINNED}
    created=[]
    root.install(blobs,created)
    assert trust.joinpath("tools","independent_component_release_root.py").is_file()
    assert (state/"control/component-release.lock").is_file()
    assert (outbox/"independent-component-offers").is_dir()
    assert financial.is_dir()
    assert not (state/"control/protected-ci.json").exists()
    assert list((outbox/"independent-component-offers").iterdir())==[]
    assert not (tmp_path/"var/lib/jason/financial-statements/worker").exists()
    root.rollback(created)
    assert not trust.parent.exists()
    assert not financial.exists()

def test_signed_proof_precedes_all_installation_side_effects():
    source=(REPO/"independent_component_control_install_root.py").read_text()
    assert source.index("owner_id=verify_owner(directory,manifest)") < source.index(
        "mkdir(LEDGER,0,0o700,created)")
    assert source.index("record(\"attempt.json\",receipt)") < source.index(
        "install(blobs,created)")
    assert "docker restart" not in source
    assert "systemctl" not in source
    assert "jason-mcp-pilot" in source
    assert "MCP_AND_PROTECTED_SERVICES_UNCHANGED=True" in source

def test_owner_script_requires_entra_and_exact_signing():
    src=(REPO/"independent_component_control_install_owner.py").read_text()
    assert "auth.jwt_owner(" in src
    assert "APPROVE-INDEPENDENT-COMPONENT-CONTROLLER-INSTALL" in src
    assert "issue_exact_owner_release(" in src
    assert "verified_principal=principal" in src
    assert "sudo" not in src
    assert "systemctl" not in src
