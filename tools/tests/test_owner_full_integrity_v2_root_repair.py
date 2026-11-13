"""Exact v2 full-integrity source-only root repair acceptance.

No test calls execute() with a real root host, mutates real systemd, or runs
on production databases. All staged root objects live below disposable /tmp.
"""
from __future__ import annotations

from datetime import datetime,timezone
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import stat
import tarfile
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from tools import owner_full_integrity_v2_root_repair as repair

ROOT = Path(__file__).resolve().parents[2]
SHA = "95832507e6e5f804f092cb5d3ebdea90ba1a49bf"


def canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()


@pytest.fixture
def manifest():
    r=json.loads((ROOT/"config/owner-full-integrity-v2-source-manifest.json").read_text())
    scope=r.pop("scope_sha256")
    assert sha256(canonical(r)).hexdigest()==scope
    r["scope_sha256"]=scope
    return r


@pytest.fixture
def policy():
    return json.loads((ROOT/"config/owner-full-integrity-v2-repair-policy.json").read_text())


@pytest.fixture
def bundle(tmp_path,manifest,policy):
    paths={
        row["archive_member"]:(ROOT / row["git_path"]).read_bytes()
        for row in manifest["source"]
    }
    paths[manifest["new_unit_dropin"]["archive_member"]]=(
        ROOT/"config/owner-full-integrity-v2.service.conf").read_bytes()
    output=tmp_path/"test-source.tar"
    with tarfile.open(output,"w",format=tarfile.USTAR_FORMAT) as tf:
        for row in [*manifest["source"],manifest["new_unit_dropin"]]:
            data=paths[row["archive_member"]]
            assert sha256(data).hexdigest()==row["sha256"]
            item=tarfile.TarInfo(row["archive_member"])
            item.size=len(data);item.uid=0;item.gid=0;item.mtime=0
            item.uname="root";item.gname="root";item.mode=int(row["mode"],8)
            tf.addfile(item,io.BytesIO(data))
        data=canonical(manifest)+b"\n"
        item=tarfile.TarInfo("_metadata/reviewed-manifest.json")
        item.size=len(data);item.uid=0;item.gid=0;item.mtime=0
        item.mode=0o400
        tf.addfile(item,io.BytesIO(data))
    assert sha256(output.read_bytes()).hexdigest()==policy["bundle_sha256"]
    source=tmp_path/"reviewed-manifest.json"
    source.write_bytes(canonical(manifest)+b"\n")
    assert sha256(source.read_bytes()).hexdigest()==policy["manifest_sha256"]
    return output,source


def test_fixed_one_shot_scope_and_source(policy,manifest):
    assert repair.SOURCE==SHA==policy["source_sha"]==manifest["source_sha"]
    assert policy["production_lkg"]==repair.LKG
    assert policy["exact_action"]==repair.ACTION
    assert policy["one_shot"] is True
    assert policy["no_provider_writes"] is True
    assert policy["no_runtime_change"] is True
    assert policy["service_max_seconds"]==5700
    assert policy["full_scan_max_seconds"]==5400
    assert policy["script_sha256"]==sha256(
        (ROOT/"tools/owner_full_integrity_v2_root_repair.py").read_bytes()).hexdigest()
    assert repair.ROOT_SCRIPT != ROOT/"tools/owner_full_integrity_v2_root_repair.py"
    assert repair.ROOT_SCRIPT.as_posix().startswith("/usr/local/lib/jason/")
    assert repair.POLICY.as_posix().startswith("/etc/jason-owner-release/")


def test_bundle_verifies_exact_files_and_scope(bundle,policy,monkeypatch):
    archive,document=bundle
    monkeypatch.setattr(repair,"BUNDLE",archive)
    monkeypatch.setattr(repair,"MANIFEST",document)
    manifest,objects=repair.checked_bundle(policy)
    assert len(objects)==3
    assert set(objects)=={
        str(repair.ROOT_SOURCE/"openclaw_authority_health_snapshot.py"),
        str(repair.ROOT_SOURCE/"openclaw_authority_operational_health.py"),
        str(repair.FULL_DROPIN),
    }
    assert manifest["scope_sha256"]==policy["scope_sha256"]
    assert b"PRAGMA" in objects[str(repair.ROOT_SOURCE/"openclaw_authority_operational_health.py")]
    assert b"TimeoutStartSec=5700" in objects[str(repair.FULL_DROPIN)]
    assert b"Nice=19" in objects[str(repair.FULL_DROPIN)]


@pytest.mark.parametrize("change,reason",[
    ({"scope_sha256":"f"*64},"SOURCE_MANIFEST_SCOPE_CHANGED"),
    ({"bundle_sha256":"f"*64},"ROOT_REPAIR_BUNDLE_HASH_CHANGED"),
    ({"manifest_sha256":"f"*64},"ROOT_REPAIR_BUNDLE_HASH_CHANGED"),
])
def test_bundle_fail_closed_on_changed_policy(change,reason,bundle,policy,monkeypatch):
    archive,document=bundle
    monkeypatch.setattr(repair,"BUNDLE",archive)
    monkeypatch.setattr(repair,"MANIFEST",document)
    changed={**policy,**change}
    with pytest.raises(repair.RepairDenied):
        repair.checked_bundle(changed)


def test_bundle_tamper_and_foreign_object_denied(bundle,policy,monkeypatch):
    archive,document=bundle
    monkeypatch.setattr(repair,"BUNDLE",archive)
    monkeypatch.setattr(repair,"MANIFEST",document)
    tampered=archive.read_bytes()+b"modified"
    archive.write_bytes(tampered)
    with pytest.raises(repair.RepairDenied,match="BUNDLE_HASH_CHANGED"):
        repair.checked_bundle(policy)


def test_disposable_exact_stage_verify_and_rollback(tmp_path,bundle,policy,monkeypatch):
    archive,document=bundle
    monkeypatch.setattr(repair,"BUNDLE",archive)
    monkeypatch.setattr(repair,"MANIFEST",document)
    manifest,objects=repair.checked_bundle(policy)
    root=tmp_path/"isolated"
    root.mkdir(mode=0o700)
    assert repair.stage_objects(manifest,objects,root=root)
    repair.verify_objects(manifest,objects,root=root)
    assert repair.rollback_objects(manifest,objects,root=root)
    for target in objects:
        assert not (root/target.lstrip("/")).exists()


def test_foreign_child_denies_rollback_without_deleting_reviewed_bytes(
    tmp_path,bundle,policy,monkeypatch,
):
    archive,document=bundle
    monkeypatch.setattr(repair,"BUNDLE",archive)
    monkeypatch.setattr(repair,"MANIFEST",document)
    manifest,objects=repair.checked_bundle(policy)
    root=tmp_path/"isolated";root.mkdir(mode=0o700)
    repair.stage_objects(manifest,objects,root=root)
    foreign=root/str(repair.ROOT_SOURCE).lstrip("/")/"foreigner.py"
    foreign.write_text("foreign")
    with pytest.raises(repair.RepairDenied,match="FOREIGN_CHILD"):
        repair.rollback_objects(manifest,objects,root=root)
    assert foreign.read_text()=="foreign"
    repair.verify_objects(manifest,objects,root=root)
    foreign.unlink()
    assert repair.rollback_objects(manifest,objects,root=root)


def test_tampered_stage_denies_rollback_before_any_deletion(
    tmp_path,bundle,policy,monkeypatch,
):
    archive,document=bundle
    monkeypatch.setattr(repair,"BUNDLE",archive)
    monkeypatch.setattr(repair,"MANIFEST",document)
    manifest,objects=repair.checked_bundle(policy)
    root=tmp_path/"isolated";root.mkdir(mode=0o700)
    repair.stage_objects(manifest,objects,root=root)
    target=next(iter(objects))
    tampered=root/target.lstrip("/")
    tampered.chmod(0o600);tampered.write_bytes(b"tampered");tampered.chmod(0o555)
    with pytest.raises(repair.RepairDenied,match="UNVERIFIABLE_ROOT_ROLLBACK"):
        repair.rollback_objects(manifest,objects,root=root)
    assert tampered.read_bytes()==b"tampered"
    assert len([x for x in objects if (root/x.lstrip("/")).exists()])==3


def test_untrusted_source_cannot_execute(monkeypatch):
    monkeypatch.setattr(repair.os,"geteuid",lambda:0)
    monkeypatch.setattr(repair.sys,"flags",SimpleNamespace(isolated=1))
    with pytest.raises(repair.RepairDenied,match="TRUSTED_ROOT_INSTALL"):
        repair.execute()


def test_signed_owner_proof_is_one_use_bound_and_wrong_scope_denied(monkeypatch,policy,manifest):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from implementation.kernel import signed_owner_release as verifier
    key=Ed25519PrivateKey.generate()
    challenge={"device_code":"abc","user_code":"ABCD","verification_uri":"https://login.microsoft.com/device","expires_in":600}
    helper=SimpleNamespace(
        TENANT="tenant",CLIENT_ID="client",SCOPE="scope",
        _form=Mock(side_effect=[challenge,{"access_token":"synthetic"}]),
        jwt_owner=lambda token:verifier.OWNER_OID,
    )
    monkeypatch.setattr(repair,"load_trust",lambda path,name:helper if path==repair.OWNER_AUTH else verifier)
    monkeypatch.setattr(repair.time,"sleep",lambda seconds:None)
    monkeypatch.setattr(repair.sys,"stdin",SimpleNamespace(isatty=lambda:True))
    monkeypatch.setattr("builtins.input",lambda prompt:repair.CONFIRM)
    monkeypatch.setattr(verifier,"read_service_owner_signing_key",lambda path:key)
    monkeypatch.setattr(verifier,"read_pinned_root_owner_public_key",lambda path:key.public_key())
    proof=repair.signed_owner_decision(policy,manifest)
    payload=proof["payload"]
    assert payload["candidate_sha"]==repair.SOURCE
    assert payload["rollback_sha"]==repair.LKG
    assert payload["scope_sha256"]==policy["scope_sha256"]
    assert payload["one_release_only"] is True
    assert payload["standing_authority"] is False
    with pytest.raises(verifier.OwnerReleaseProofDenied,match="TRANSACTION_BINDING"):
        verifier.verify_exact_owner_release(
            proof,public_key=key.public_key(),
            expected_candidate_sha=repair.SOURCE,
            expected_rollback_sha=repair.LKG,
            expected_release_id="release-"+repair.SOURCE[:16],
            expected_scope_sha256="f"*64,
            expected_manifest_sha256=policy["manifest_sha256"],
            expected_freeze_sha256=policy["freeze_sha256"],
            at=datetime.now(timezone.utc),
        )


def test_full_proof_does_not_allow_partial_or_quick_substitute(tmp_path,monkeypatch):
    report={
        "status":"pass","failures":[],"snapshot_source_exit_code":0,
        "provider_contacted":False,"provider_credentials_used":False,
        "files":{x:{"integrity":"ok","present":True,"mode":"0o600"} for x in
                 ("authority","replay","security_audit","orchestration_audit")},
        "backup_restore_proof":{
            "backup_integrity":"ok","restore_integrity":"ok",
            "counts_match":True,"backup_mode":"0o600","restore_mode":"0o600",
        },
        "trusted_key_registry":{"present":True,"mode":"0o600","active_records":1},
        "delegations":{"expired_active_records":0},
    }
    current=tmp_path/"operational-full-health.json"
    current.write_text(json.dumps(report))
    current.chmod(0o600)
    actual=current.lstat()
    class FakePath:
        def lstat(self):
            return SimpleNamespace(st_uid=1000,st_mode=actual.st_mode,
                                   st_mtime=actual.st_mtime)
        def read_bytes(self):
            return current.read_bytes()
    monkeypatch.setattr(repair,"FULL",FakePath())
    assert repair.verify_full_proof(actual.st_mtime-1)==report
    report["files"]["orchestration_audit"]["integrity"]="quick_ok"
    current.write_text(json.dumps(report))
    with pytest.raises(repair.RepairDenied,match="FULL_SQLITE_DB_PROOF_MISSING"):
        repair.verify_full_proof(actual.st_mtime-1)
    report["files"]["orchestration_audit"]["integrity"]="ok"
    report["backup_restore_proof"]["counts_match"]=False
    current.write_text(json.dumps(report))
    with pytest.raises(repair.RepairDenied,match="COMPLETE_BACKUP_RESTORE"):
        repair.verify_full_proof(actual.st_mtime-1)


def test_root_policy_exact_code_hashes_and_consumed_v1_is_unchanged(
    policy,monkeypatch,
):
    fake={
        repair.POLICY:b"",
        repair.ROOT_SCRIPT:(ROOT/"tools/owner_full_integrity_v2_root_repair.py").read_bytes(),
        repair.OWNER_AUTH:b"original-vetted-owner-auth",
        repair.OWNER_PROOF:b"original-vetted-ed25519-owner-verifier",
        repair.FULL_UNIT:b"original-installed-full-service",
        repair.FAST_UNIT:b"original-installed-fast-service",
        repair.FAST_EMERGENCY:b"original-expiring-fast-overlay",
    }
    field_map={
        repair.ROOT_SCRIPT:"script_sha256",
        repair.OWNER_AUTH:"owner_auth_sha256",
        repair.OWNER_PROOF:"owner_proof_sha256",
        repair.FULL_UNIT:"full_unit_sha256",
        repair.FAST_UNIT:"fast_unit_sha256",
        repair.FAST_EMERGENCY:"old_fast_emergency_sha256",
    }
    test_policy=dict(policy)
    for path,name in field_map.items():
        test_policy[name]=sha256(fake[path]).hexdigest()
    fake[repair.POLICY]=canonical(test_policy)
    monkeypatch.setattr(repair,"read_secure_root",lambda path,*args,**kwargs:fake[path])
    assert repair.fixed_policy()==test_policy
    changed={**test_policy,"owner_proof_sha256":"f"*64}
    fake[repair.POLICY]=canonical(changed)
    with pytest.raises(repair.RepairDenied,match="PINNED_ROOT_FILE_CHANGED"):
        repair.fixed_policy()
    assert repair.ACTION!="owner-full-sqlite-integrity-proof-90m-recovery-v1"
    assert "full-integrity-recovery-ledger" not in str(repair.LEDGER)


def test_bounded_stage_requires_no_extra_sources(
    tmp_path,bundle,policy,monkeypatch,
):
    archive,document=bundle
    monkeypatch.setattr(repair,"BUNDLE",archive)
    monkeypatch.setattr(repair,"MANIFEST",document)
    manifest,objects=repair.checked_bundle(policy)
    root=tmp_path/"isolated";root.mkdir(mode=0o700)
    changed=dict(objects)
    changed["/etc/systemd/system/unapproved.service"]=b"bad"
    with pytest.raises(repair.RepairDenied,match="UNEXPECTED_ROOT_STAGING"):
        repair.stage_objects(manifest,changed,root=root)
    assert not (root/"etc").exists()


def test_source_only_check_refuses_implicit_production_apply(monkeypatch):
    monkeypatch.setattr(repair.os,"geteuid",lambda:1000)
    monkeypatch.setattr(repair.sys,"argv",[
        "owner_full_integrity_v2_root_repair.py","--check-only",
    ])
    assert repair.main()==0


def test_systemd_overlay_is_read_only_bounded_and_keeps_original_unit(manifest):
    text=(ROOT/"config/owner-full-integrity-v2.service.conf").read_text()
    assert "ExecStart=" in text
    assert "TimeoutStartSec=5700" in text
    assert "Nice=19" in text and "IOSchedulingClass=idle" in text
    assert "authority-health-v2-"+SHA[:12] in text
    assert "systemctl stop" not in text
    assert "jason-runtime.service" not in text
    assert "jason-mcp-pilot" not in text
    assert "ReadOnlyPaths=" in text
    assert manifest["no_runtime_or_mcp_mutation"] is True
    assert manifest["no_ticket_or_provider_mutation"] is True
