"""Exact-action financial first release admission tests (source-only)."""
from __future__ import annotations
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from tools import financial_component_oneuse_release_root as root
from tools import financial_component_oneuse_release_owner as owner

SRC=Path(__file__).resolve().parents[1]


def synth_stage(tmp_path,monkeypatch):
    stage=tmp_path/"independent-component-financial-release-c205bb4ac163"
    stage.mkdir(mode=0o700)
    cfg={
      "enabled":True,
      "tenant_id":"f7054323-d52b-4863-8c2f-1898f0b6077c",
      "drive_id":"b!v9dMj7hyfk-YA8R6vLsjLySnt-Wb3GtArtgpYfH3EVNo8p5rPdImQ5Z7APH0M9tF",
      "root_path":"Bank Checking Accounts Register",
      "run_hour":5,"timezone":"America/New_York",
    }
    blobs={
        "compose.yaml":b"single-scoped-component",
        "config.json":json.dumps(cfg).encode(),
        "boundary.sqlite3":b"synthetic-boundary",
    }
    scope={"action":"exact-first-financial-release"}
    blobs["scope.json"]=root.canonical(scope)
    monkeypatch.setattr(root,"SCOPE_SHA",root.digest(root.canonical(scope)))
    manifest={
       "candidate_sha":root.SOURCE,
       "rollback_sha":root.ZERO,
       "image_digest":root.IMAGE,
       "scope_sha256":root.SCOPE_SHA,
       "freeze_sha256":root.FREEZE_SHA,
       "component_id":"financial-statements",
       "provider_scope":{"tenant_id":cfg["tenant_id"]},
       "compose_sha256":root.digest(blobs["compose.yaml"]),
       "config_sha256":root.digest(blobs["config.json"]),
       "boundary_sha256":root.digest(blobs["boundary.sqlite3"]),
    }
    blobs["manifest.json"]=json.dumps(manifest).encode()
    monkeypatch.setattr(root,"MANIFEST_SHA",root.digest(root.canonical(manifest)))
    monkeypatch.setattr(root,"STAGE",stage)
    monkeypatch.setattr(root,"STAGE_UID",os.geteuid())
    for name,blob in blobs.items():
        p=stage/name
        p.write_bytes(blob)
        p.chmod(0o400)
    return stage,manifest,blobs


def test_scope_and_source_pin():
    assert root.ACTION=="owner-first-financial-statements-component-release-20261117"
    assert root.ZERO=="0"*40
    assert root.IMAGE.startswith("sha256:")
    assert root.SOURCE[:12] in str(root.STAGE)
    assert root.PROTECTED==("jason-runtime","jason-mcp-pilot",
                             "jason-pmv4-shadow-gateway",
                             "jason-teams-gateway","openbao")
    assert root.REQUIRED_CHECKS


def test_synthetic_exact_stage(tmp_path,monkeypatch):
    _,m,b=synth_stage(tmp_path,monkeypatch)
    got,files=root.exact_stage()
    assert got==m
    assert files==b


def test_extra_file_disallowed(tmp_path,monkeypatch):
    stage,_,_=synth_stage(tmp_path,monkeypatch)
    (stage/"unexpected").write_text("unexpected")
    with pytest.raises(root.Denied,match="STAGING_FILE_SET"):
        root.exact_stage()


def test_wrong_permissions_and_tamper_denied(tmp_path,monkeypatch):
    stage,_,_=synth_stage(tmp_path,monkeypatch)
    p=stage/"config.json"
    p.chmod(0o600)
    with pytest.raises(root.Denied,match="STAGING_FILE_UNTRUSTED"):
        root.exact_stage()
    p.chmod(0o400)
    p.chmod(0o600)
    p.write_text('{"enabled":true}')
    p.chmod(0o400)
    with pytest.raises(root.Denied,match="STAGED_SOURCE_DIGEST_DRIFT"):
        root.exact_stage()


def test_wrong_schedule_or_root_denied(tmp_path,monkeypatch):
    stage,m,b=synth_stage(tmp_path,monkeypatch)
    cfg=json.loads(b["config.json"])
    cfg["run_hour"]=6
    blob=json.dumps(cfg).encode()
    manifest=dict(m)
    manifest["config_sha256"]=root.digest(blob)
    mbytes=json.dumps(manifest).encode()
    monkeypatch.setattr(root,"MANIFEST_SHA",root.digest(root.canonical(manifest)))
    for name,content in (("manifest.json",mbytes),("config.json",blob)):
        p=stage/name
        p.chmod(0o600);p.write_bytes(content);p.chmod(0o400)
    with pytest.raises(root.Denied,match="STAGED_CONFIG_NOT_APPROVED"):
        root.exact_stage()


def test_ci_evidence_real_checks_required(monkeypatch):
    good={name:{"name":name,"status":"completed","conclusion":"success"}
          for name in root.REQUIRED_CHECKS}
    while len(good)<24:
        k=f"extra-verified-{len(good)}"
        good[k]={"name":k,"status":"completed","conclusion":"success"}
    checks=list(good.values())
    def api(endpoint,projection):
        if "compare/" in endpoint:
            return {"status":"ahead","merge_base_sha":root.SOURCE,"head":"a"*40}
        return {"total_count":len(checks),"checks":checks}
    monkeypatch.setattr(root,"gh_api",api)
    proof=root.verified_ci()
    assert proof["protected_main_ancestor"] and proof["required_ci_passed"]
    assert proof["check_count"]==len(checks)
    checks[0]["conclusion"]="failure"
    with pytest.raises(root.Denied,match="CI_NOT_ALL_PASS"):
        root.verified_ci()


def test_ci_provenance_not_any_branch(monkeypatch):
    monkeypatch.setattr(root,"gh_api",lambda endpoint,proj:{
        "status":"diverged","merge_base_sha":"0"*40,"head":"a"*40})
    with pytest.raises(root.Denied,match="SOURCE_NOT_IN_PROTECTED_MAIN"):
        root.verified_ci()


def test_owner_proof_real_signature_exact_scope(tmp_path,monkeypatch):
    from implementation.kernel import signed_owner_release as signer
    key=Ed25519PrivateKey.generate()
    oid,principal=sorted(signer.EXACT_OWNER_OAUTH_SUBJECTS.items())[0]
    manifest={"candidate_sha":root.SOURCE}
    signed=signer.issue_exact_owner_release(
        approval_id="owner-mcp-"+"a"*32,
        release_id="release-"+root.SOURCE[:16],
        candidate_sha=root.SOURCE,rollback_sha=root.ZERO,
        scope_sha256=root.SCOPE_SHA,
        manifest_sha256=root.MANIFEST_SHA,freeze_sha256=root.FREEZE_SHA,
        verified_tenant_id=signer.TID,verified_owner_oid=oid,
        verified_principal=principal,verified_organization_id="aot",
        confirmed_decision="approve",at=datetime.now(timezone.utc),
        private_key=key)
    fake={"schema_version":"1.0","action":root.ACTION,
          "manifest_sha256":root.MANIFEST_SHA,"signed_owner_proof":signed}
    p=tmp_path/"proof.json"
    p.write_text(json.dumps(fake));p.chmod(0o400)
    monkeypatch.setattr(root,"OWNER_PROOF",p)
    monkeypatch.setattr(root,"STAGE_UID",os.geteuid())
    monkeypatch.setattr(root,"root_module",lambda *args: type("Signer",(),{
        "read_pinned_root_owner_public_key":staticmethod(lambda *a,**k:key.public_key()),
        "verify_exact_owner_release":staticmethod(signer.verify_exact_owner_release),
    }))
    raw,approval=root.owner_signature(manifest)
    assert approval=="owner-mcp-"+"a"*32
    assert raw["payload"]["one_release_only"] is True
    fake["action"]="unrelated-release"
    p.chmod(0o600);p.write_text(json.dumps(fake));p.chmod(0o400)
    with pytest.raises(root.Denied,match="OWNER_ACTION_NOT_EXACT"):
        root.owner_signature(manifest)


def test_root_always_requires_isolated_privilege(monkeypatch):
    monkeypatch.setattr(root.os,"geteuid",lambda:1000)
    with pytest.raises(root.Denied,match="EXACT_PINNED_ROOT_EXECUTION_REQUIRED"):
        root.execute()


def test_release_path_uses_native_controller_only():
    content=(SRC/"financial_component_oneuse_release_root.py").read_text()
    assert 'run_native("promote","--candidate-sha",SOURCE)' in content
    assert 'ROOT_ENTRY=TRUST/"tools/independent_component_release_root.py"' in content
    assert 'signed,approval_id=owner_signature(m)' in content
    assert content.index("signed,approval_id=owner_signature(m)") < content.index(
        "root_json(LEDGER,attempt,0o600)")
    assert content.index("root_json(LEDGER,attempt,0o600)") < content.index(
        "ROOT_BUNDLE.mkdir(mode=0o700)")
    assert "docker restart" not in content
    assert 'systemctl stop' not in content
    assert 'systemctl restart' not in content
    assert 'os.system(' not in content
    assert "shell=True" not in content


def test_owner_issuer_requires_entra_signature_and_no_root():
    text=(SRC/"financial_component_oneuse_release_owner.py").read_text()
    assert "jwt_owner(" in text
    assert "APPROVE-EXACT-05AM-FINANCIAL-STATEMENT-RELEASE" in text
    assert "issue_exact_owner_release(" in text
    assert "verified_principal=principal" in text
    assert "PRODUCTION_MUTATION=NOT_YET_PERFORMED" in text
    assert "docker run" not in text
    assert "sudo" not in text
