"""A1 atomic root staging, audit and one-Owner binding on disposable files only."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from pathlib import Path
import os
import stat
import subprocess

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from implementation.kernel.signed_owner_release import (
    issue_exact_owner_release, TID, OWNER_OID, OWNER_PRINCIPAL,
)
from tools import pmv4_a1_atomic_shadow_root as a1


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    root=tmp_path/"shadow"
    control=root/"control"
    control.mkdir(parents=True)
    (root/"releases").mkdir()
    archive=tmp_path/"packet"
    (archive/"release"/"bundle"/"config").mkdir(parents=True)
    (archive/"release"/"bundle"/"tools").mkdir()
    source_names=("config/profile.json","tools/review.py")
    sources={
        "config/profile.json":b'{"isolated":true}',
        "tools/review.py":b'print("no-provider-access")',
    }
    for name, data in sources.items():
        (archive/"release"/"bundle"/name).write_bytes(data)
    values={
        "ROOT":root,"TARGET":root/"releases"/a1.CANDIDATE,
        "AUDIT":control/"a1-exact-atomic-bootstrap.jsonl",
        "APPROVED":control/"approved-manifest.json",
        "REVIEWED":control/"reviewed-scope.json",
        "TOKEN":control/"gateway-token",
        "ARCHIVE":archive,"FILES":source_names,
    }
    for name, value in values.items():
        monkeypatch.setattr(a1,name,value)
    plan={"source_files":{k:a1.sha(v) for k,v in sources.items()},
          "bundle_sha256":a1.shadow.bundle_digest(archive/"release"/"bundle"),
          "shadow_manifest_sha256":a1.sha(b"{}")}
    return root,archive,sources,plan


def test_script_has_no_nonroot_direct_release_authority():
    with pytest.raises(a1.A1RootDenied,match="ROOT_EXECUTION_REQUIRED"):
        a1.root_script_trusted()


def test_atomic_stage_and_exact_empty_baseline_rollback(isolated):
    root,archive,sources,plan=isolated
    manifest={"candidate_sha":a1.CANDIDATE}
    scope={"service":"jason-pmv4-shadow"}
    owner="owner-mcp-"+"d"*32
    a1.append("begin",owner,{"test_only":True})
    a1.stage_exact(plan,manifest,scope,owner)
    assert a1.TARGET.is_dir()
    assert a1.shadow.bundle_digest(a1.TARGET/"bundle")==plan["bundle_sha256"]
    assert (a1.TARGET/"release-manifest.json").read_bytes()==a1.canon(manifest)
    assert a1.TOKEN.is_file()
    assert stat.S_IMODE(a1.TOKEN.stat().st_mode)==0o400
    assert 32<=len(a1.TOKEN.read_bytes())<=128
    rows=a1.audit_rows()
    assert rows[-1]["event"]=="root-stage-verified"
    assert rows[0]["approval_id"]==owner
    a1.cleanup_exact_unpromoted(owner)
    assert not a1.TARGET.exists()
    assert not a1.APPROVED.exists()
    assert not a1.REVIEWED.exists()
    assert not a1.TOKEN.exists()
    assert a1.AUDIT.exists()


def test_modified_stage_content_is_not_deleted(isolated):
    root,archive,sources,plan=isolated
    owner="owner-mcp-"+"e"*32
    a1.append("begin",owner,{"test_only":True})
    a1.stage_exact(plan,{}, {},owner)
    path=a1.TARGET/"bundle"/"config"/"profile.json"
    path.chmod(0o600)
    path.write_text("foreign modification")
    path.chmod(0o400)
    with pytest.raises(a1.A1RootDenied,match="ROLLBACK_FOREIGN_OR_CHANGED_FILE"):
        a1.cleanup_exact_unpromoted(owner)
    assert path.read_text()=="foreign modification"


def test_root_journal_tamper_rejected(isolated):
    root,archive,sources,plan=isolated
    owner="owner-mcp-"+"f"*32
    a1.append("begin",owner,{"test_only":True})
    a1.append("intent-create-file",owner,{"path":"/tmp/no-op"})
    assert len(a1.audit_rows())==2
    a1.AUDIT.chmod(0o600)
    data=a1.AUDIT.read_bytes().replace(b"intent-create-file",b"unexpected-file--")
    a1.AUDIT.write_bytes(data)
    with pytest.raises(a1.A1RootDenied,match="AUDIT_CHAIN_CHANGED"):
        a1.audit_rows()


def test_one_owner_parent_child_scope_bound_and_expiry(isolated,monkeypatch):
    root,archive,sources,plan=isolated
    now=datetime.now(timezone.utc)
    key=Ed25519PrivateKey.generate()
    monkeypatch.setattr(a1.shadow,"read_pinned_root_owner_public_key",
                        lambda *_args,**_kw:key.public_key())
    approval="owner-mcp-"+"a"*32
    scope_sha="c"*64
    manifest={"scope_sha256":"d"*64}
    plan={"scope_sha256":scope_sha,"shadow_freeze_sha256":"e"*64}
    proof_args={
        "approval_id":approval,"release_id":"release-"+a1.CANDIDATE[:16],
        "candidate_sha":a1.CANDIDATE,"rollback_sha":a1.ROLLBACK,
        "freeze_sha256":"e"*64,"verified_tenant_id":TID,
        "verified_owner_oid":OWNER_OID,"verified_principal":OWNER_PRINCIPAL,
        "verified_organization_id":"aot","confirmed_decision":"approve",
        "at":now,"private_key":key,
    }
    parent=issue_exact_owner_release(
        scope_sha256=scope_sha,manifest_sha256=a1.sha(a1.canon(plan)),
        **proof_args)
    child=issue_exact_owner_release(
        scope_sha256=manifest["scope_sha256"],
        manifest_sha256=a1.sha(a1.canon(manifest)),**proof_args)
    record={
        "schema_version":"1.0","action":a1.ACTION,
        "source_sha":a1.CANDIDATE,"scope_sha256":scope_sha,
        "manifest_sha256":a1.sha(a1.canon(plan)),"approval_id":approval,
        "signed_root_release":parent,"signed_shadow_release":child,
    }
    monkeypatch.setattr(a1,"OWNER_PROOF",archive/"test-only-owner-proof.json")
    a1.OWNER_PROOF.write_bytes(a1.canon(record))
    a1.OWNER_PROOF.chmod(0o400)
    verified, signed_child=a1.verify_owner(plan,manifest)
    assert verified["owner_oid"]==OWNER_OID
    assert signed_child["payload"]["approval_id"]==approval
    with pytest.raises(a1.A1RootDenied,match="HISTORICAL_APPROVAL_NOT_COMMITTED"):
        a1.verify_owner(plan,manifest,recovery=True)
    a1.append("begin",approval,{"source":"exact-owner"})
    a1.append("committed",approval,{"shadow_accepted":True})
    historic, _=a1.verify_owner(plan,manifest,recovery=True)
    assert historic["approval_id"]==approval
    changed=dict(plan,scope_sha256="f"*64)
    with pytest.raises(Exception):
        a1.verify_owner(changed,manifest)


def test_stage_fails_on_preexisting_root_target(isolated):
    root,archive,sources,plan=isolated
    a1.TARGET.mkdir()
    marker=a1.TARGET/"unrelated"
    marker.write_bytes(b"untouched")
    a1.append("begin","owner-mcp-"+"9"*32,{})
    with pytest.raises(a1.A1RootDenied,match="STAGE_DIRECTORY_ALREADY_PRESENT"):
        a1.stage_exact(plan,{}, {}, "owner-mcp-"+"9"*32)
    assert marker.read_bytes()==b"untouched"


def test_active_watchdog_policy_requires_explicit_shadow_allowance(tmp_path):
    config=tmp_path/"production-desired-state.json"
    allowed=["jason-runtime","jason-mcp-pilot","jason-pmv4-shadow-gateway"]
    config.write_text(__import__("json").dumps({
        "schema_version":"1.0","allowed_running_containers":allowed}))
    config.chmod(0o600)
    digest=a1.active_shadow_allowlist(path=config,expected_uid=os.geteuid())
    assert len(digest)==64
    assert digest==a1.sha(config.read_bytes())
    config.write_text(__import__("json").dumps({
        "schema_version":"1.0",
        "allowed_running_containers":["jason-runtime","jason-mcp-pilot"]}))
    with pytest.raises(a1.A1RootDenied,match="SHADOW_NOT_ALLOWED"):
        a1.active_shadow_allowlist(path=config,expected_uid=os.geteuid())


def test_active_watchdog_policy_symlink_or_wrong_mode_refused(tmp_path):
    config=tmp_path/"desired.json"
    config.write_text('{"schema_version":"1.0","allowed_running_containers":["jason-pmv4-shadow-gateway"]}')
    config.chmod(0o666)
    with pytest.raises(a1.A1RootDenied,match="POLICY_NOT_TRUSTED"):
        a1.active_shadow_allowlist(path=config,expected_uid=os.geteuid())
    config.chmod(0o600)
    alias=tmp_path/"alias.json"
    alias.symlink_to(config)
    with pytest.raises(a1.A1RootDenied,match="POLICY_NOT_TRUSTED"):
        a1.active_shadow_allowlist(path=alias,expected_uid=os.geteuid())
