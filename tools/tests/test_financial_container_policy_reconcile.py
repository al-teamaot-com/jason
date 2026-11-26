"""Offline exact signed financial container root policy admission tests."""
from __future__ import annotations
import json
import os
from pathlib import Path
import pytest
from tools import financial_container_policy_reconcile_root as root

ROOT=Path(__file__).resolve().parents[1]

def create_stage(monkeypatch,tmp_path):
    stage=tmp_path/("financial-container-policy-"+"a"*12)
    stage.mkdir(mode=0o700)
    monkeypatch.setattr(root,"STAGE_PARENT",tmp_path)
    monkeypatch.setattr(root,"UID",os.geteuid())
    baseline=json.loads((ROOT.parent/"config/production-desired-state.json").read_text())
    baseline["allowed_system_units"]=sorted(
      set(baseline["allowed_system_units"])|{
        "jason-catalog-root-bootstrap-recovery.service",
        "jason-catalog-root-bootstrap-recovery.timer",
        "jason-catalog-scoped-recovery.service",
        "jason-catalog-scoped-recovery.timer",
      })
    source=(json.dumps(baseline,sort_keys=True,indent=2)+"\n").encode()
    target=root.candidate(source)
    monkeypatch.setattr(root,"BASE_SHA",root.digest(source))
    monkeypatch.setattr(root,"TARGET_SHA",root.digest(target))
    code=(ROOT/"financial_container_policy_reconcile_root.py").read_bytes()
    manifest={
      "schema_version":"1.0","action":root.ACTION,"source_sha":"a"*40,
      "rollback_sha":root.LKG,
      "pmv4_catalog_policy_sha":root.PMV4_SOURCE,
      "financial_candidate_sha":root.FINANCIAL_SOURCE,
      "financial_image_id":root.FINANCIAL_IMAGE,
      "freeze_sha256":root.FREEZE_SHA,
      "baseline_sha256":root.BASE_SHA,
      "target_sha256":root.TARGET_SHA,
      "root_script_sha256":root.digest(code),
      "one_use":True,"provider_mutations":0,
      "protected_service_restarts":False,
      "new_containers_started":False,
    }
    manifest["scope_sha256"]=root.digest(root.canonical(manifest))
    files={"baseline.json":source,"candidate.json":target,
           root.SRC_FILE:code,
           "manifest.json":(json.dumps(manifest)+"\n").encode()}
    for name,body in files.items():
        p=stage/name;p.write_bytes(body);p.chmod(0o400)
    return stage,manifest,files

def test_exact_single_container_diff():
    raw=b'{"schema_version":"1.0","allowed_running_containers":["jason-runtime"],"allowed_system_units":[]}'
    result=json.loads(root.candidate(raw))
    assert result["allowed_running_containers"]==["jason-financial-statements","jason-runtime"]
    assert result["allowed_system_units"]==[]

def test_duplicate_container_refused():
    p=b'{"schema_version":"1.0","allowed_running_containers":["jason-financial-statements"]}'
    with pytest.raises(root.Denied,match="ALREADY_DECLARED"):
        root.candidate(p)

def test_reviewed_scope_without_owner(tmp_path,monkeypatch):
    stage,m,blobs=create_stage(monkeypatch,tmp_path)
    plan,readback=root.stage(stage)
    assert plan==m
    assert readback==blobs

def test_requires_owner_for_root(tmp_path,monkeypatch):
    stage,*_=create_stage(monkeypatch,tmp_path)
    with pytest.raises(root.Denied,match="UNEXPECTED_FILES"):
        root.stage(stage,with_proof=True)

def test_rejects_extra_and_tampered_stage(tmp_path,monkeypatch):
    stage,*_=create_stage(monkeypatch,tmp_path)
    x=stage/"additional";x.write_text("no")
    with pytest.raises(root.Denied,match="UNEXPECTED_FILES"):
        root.stage(stage)
    x.unlink()
    p=stage/"candidate.json"
    p.chmod(0o600);p.write_bytes(b"{}");p.chmod(0o400)
    with pytest.raises(root.Denied,match="DIFF_NOT_SINGLE_CONTAINER"):
        root.stage(stage)

def test_rejects_out_of_scope_provider_or_runtime(tmp_path,monkeypatch):
    stage,manifest,_=create_stage(monkeypatch,tmp_path)
    p=stage/"manifest.json"
    for k,v in (("provider_mutations",1),("protected_service_restarts",True),
                ("new_containers_started",True)):
        wrong=dict(manifest);wrong[k]=v
        without=dict(wrong);without.pop("scope_sha256")
        wrong["scope_sha256"]=root.digest(root.canonical(without))
        p.chmod(0o600);p.write_text(json.dumps(wrong));p.chmod(0o400)
        with pytest.raises(root.Denied,match="SCOPE_NOT_EXACT"):
            root.stage(stage)

def test_unprivileged_cannot_execute(tmp_path,monkeypatch):
    monkeypatch.setattr(root.os,"geteuid",lambda:1000)
    with pytest.raises(root.Denied,match="ISOLATED_ROOT_REQUIRED"):
        root.execute(tmp_path)

def test_single_action_source_contract():
    data=(ROOT/"financial_container_policy_reconcile_root.py").read_text()
    assert data.index("approval=root_owner(directory,manifest)") < data.index(
        'record(LEDGER/"attempt.json",outcome)')
    assert data.index('record(LEDGER/"attempt.json",outcome)') < data.index(
        "atomic_replace(target)",data.index("def execute"))
    assert data.index("watchdog_pass()",data.index("def execute")) < data.index(
        'outcome["status"]="verified"')
    assert "systemctl restart" not in data
    assert "systemctl stop" not in data
    assert "docker run" not in data
    assert "shell=True" not in data
    assert "os.system(" not in data

def test_owner_source_exact_signed_entra_and_no_root():
    data=(ROOT/"financial_container_policy_reconcile_owner.py").read_text()
    assert "auth.jwt_owner(" in data
    assert "issue_exact_owner_release(" in data
    assert "APPROVE-EXACT-FINANCIAL-CONTAINER-POLICY" in data
    assert "verified_principal=principal" in data
    assert "sudo" not in data
    assert "systemctl" not in data

def test_catalog_receipt_required():
    data=(ROOT/"financial_container_policy_reconcile_root.py").read_text()
    assert "four_unit_catalog_policy_reconciled" in data
    assert "FINANCIAL_POLICY_CATALOG_RECONCILE_NOT_COMPLETE" in data
    assert 'get("circuit_breaker",{}).get("state")=="closed"' in data
    assert "NAME not in running" in data
    assert "new_containers_started" in data


def test_real_temporary_owner_signature_is_bound_to_exact_policy(tmp_path,monkeypatch):
    """Exercise Ed25519 verification without reading production signing keys."""
    from datetime import datetime,timezone
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from implementation.kernel import signed_owner_release as signer
    key=Ed25519PrivateKey.generate()
    oid,principal=sorted(signer.EXACT_OWNER_OAUTH_SUBJECTS.items())[0]
    source="b"*40
    manifest={
        "schema_version":"1.0","action":root.ACTION,
        "source_sha":source,"rollback_sha":root.LKG,
        "scope_sha256":"c"*64,"freeze_sha256":root.FREEZE_SHA,
    }
    proof=signer.issue_exact_owner_release(
        approval_id="owner-mcp-"+"a"*32,
        release_id="release-"+source[:16],
        candidate_sha=source,rollback_sha=root.LKG,
        scope_sha256=manifest["scope_sha256"],
        manifest_sha256=root.digest(root.canonical(manifest)),
        freeze_sha256=root.FREEZE_SHA,
        verified_tenant_id=signer.TID,verified_owner_oid=oid,
        verified_principal=principal,verified_organization_id="aot",
        confirmed_decision="approve",at=datetime.now(timezone.utc),
        private_key=key)
    wrapper={
        "schema_version":"1.0","action":root.ACTION,
        "manifest_sha256":root.digest(root.canonical(manifest)),
        "signed_owner_proof":proof,
    }
    packet=tmp_path/"packet";packet.mkdir()
    path=packet/root.OWNER_FILE
    path.write_text(json.dumps(wrapper))
    path.chmod(0o400)
    # The real verifier accepts the exact temporary proof only under the
    # matching source, Owner, scope, manifest, rollback, and freeze bindings.
    valid=signer.verify_exact_owner_release(
        proof,public_key=key.public_key(),
        expected_candidate_sha=source,expected_rollback_sha=root.LKG,
        expected_release_id="release-"+source[:16],
        expected_scope_sha256=manifest["scope_sha256"],
        expected_manifest_sha256=root.digest(root.canonical(manifest)),
        expected_freeze_sha256=root.FREEZE_SHA,
        at=datetime.now(timezone.utc))
    assert valid["approval_id"]=="owner-mcp-"+"a"*32
    with pytest.raises(signer.OwnerReleaseProofDenied):
        signer.verify_exact_owner_release(
            proof,public_key=key.public_key(),
            expected_candidate_sha=source,expected_rollback_sha=root.LKG,
            expected_release_id="release-"+source[:16],
            expected_scope_sha256="d"*64,
            expected_manifest_sha256=root.digest(root.canonical(manifest)),
            expected_freeze_sha256=root.FREEZE_SHA,
            at=datetime.now(timezone.utc))
