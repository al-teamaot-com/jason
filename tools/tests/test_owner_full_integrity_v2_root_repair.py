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


def test_signed_owner_proof_is_user_signed_root_verified_and_wrong_scope_denied(
    monkeypatch,policy,manifest,
):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from implementation.kernel import signed_owner_release as verifier
    key=Ed25519PrivateKey.generate()
    policy_bytes=canonical(policy)+b"\n"
    root_policy_sha=sha256(policy_bytes).hexdigest()
    at=datetime.now(timezone.utc)
    proof=verifier.issue_exact_owner_release(
        approval_id="owner-mcp-"+"a"*32,
        release_id="release-"+repair.SOURCE[:16],
        candidate_sha=repair.SOURCE,rollback_sha=repair.LKG,
        scope_sha256=policy["scope_sha256"],
        manifest_sha256=root_policy_sha,
        freeze_sha256=policy["freeze_sha256"],
        verified_tenant_id=verifier.TID,
        verified_owner_oid=verifier.OWNER_OID,
        verified_principal=verifier.EXACT_OWNER_OAUTH_SUBJECTS[verifier.OWNER_OID],
        verified_organization_id="aot",
        confirmed_decision="approve",at=at,private_key=key,
    )
    envelope={
        "schema_version":"1.0","action":repair.ACTION,
        "source_sha":repair.SOURCE,
        "scope_sha256":policy["scope_sha256"],
        "bundle_sha256":policy["bundle_sha256"],
        "root_policy_sha256":root_policy_sha,
        "status":"AUTHENTICATED_OWNER_APPROVED_NOT_EXECUTED",
        "signed_owner_proof":proof,
    }
    monkeypatch.setattr(repair,"read_secure_root",lambda path,*args:policy_bytes)
    monkeypatch.setattr(repair,"load_trust",lambda path,name:verifier)
    monkeypatch.setattr(verifier,"read_pinned_root_owner_public_key",
                        lambda *args,**kwargs:key.public_key())
    assert repair.verify_signed_owner_payload(policy,envelope)==proof
    assert proof["payload"]["one_release_only"] is True
    assert proof["payload"]["standing_authority"] is False
    with pytest.raises(repair.RepairDenied,match="SIGNED_OWNER_DECISION_EXACT_ACTION_DRIFT"):
        repair.verify_signed_owner_payload(
            policy,{**envelope,"action":"unreviewed-production-install"})
    with pytest.raises(repair.RepairDenied,match="SIGNED_OWNER_DECISION_EXACT_ACTION_DRIFT"):
        repair.verify_signed_owner_payload(
            policy,{**envelope,"root_policy_sha256":"f"*64})
    with pytest.raises(verifier.OwnerReleaseProofDenied,match="TRANSACTION_BINDING"):
        repair.verify_signed_owner_payload(
            {**policy,"scope_sha256":"f"*64},
            {**envelope,"scope_sha256":"f"*64})
    assert "read_service_owner_signing_key(" not in (
        __import__("inspect").getsource(repair))
    assert str(repair.OWNER_SIGNED_DECISION).startswith("/srv/jason/archive/")



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


def test_disposable_fake_root_full_lifecycle_runs_proof_before_fast_health(
    tmp_path,monkeypatch,policy,
):
    """Full lifecycle uses only fakes; never contacts host systemd or Docker."""
    import contextlib

    emergency=tmp_path/"expired-fast-overlay.conf"
    emergency.write_bytes(b"[Service]\nExecStart=synthetic-expired\n")
    emergency_bytes=emergency.read_bytes()
    local_policy=dict(policy)
    local_policy["old_fast_emergency_sha256"]=sha256(emergency_bytes).hexdigest()
    ledger=tmp_path/"ledger";ledger.mkdir(mode=0o700)
    class RootLedger:
        def lstat(self):
            return SimpleNamespace(
                st_mode=stat.S_IFDIR|0o700,st_uid=0,
            )
        def is_symlink(self):return False
        def iterdir(self):return iter(())
        def __truediv__(self,item):return ledger/item

    monkeypatch.setattr(repair,"LEDGER",RootLedger())
    monkeypatch.setattr(repair,"FAST_EMERGENCY",emergency)
    monkeypatch.setattr(repair.os,"geteuid",lambda:0)
    monkeypatch.setattr(repair.sys,"flags",SimpleNamespace(isolated=1))
    monkeypatch.setattr(repair,"ROOT_SCRIPT",Path(repair.__file__).resolve())
    monkeypatch.setattr(repair,"fixed_policy",lambda:local_policy)
    monkeypatch.setattr(repair,"checked_bundle",lambda p:({"source":[],"new_unit_dropin":{}},{"file":b"x"}))
    monkeypatch.setattr(repair,"verified_initial_bootstrap_ledger",lambda:True)
    monkeypatch.setattr(repair,"root_state",lambda p:{"runtime_id":"rt","mcp_id":"mcp"})
    monkeypatch.setattr(repair,"signed_owner_decision",lambda *args:{"payload":{"exact":"approved"}})
    @contextlib.contextmanager
    def lock():
        yield
    monkeypatch.setattr(repair,"native_release_lock",lock)
    operations=[]
    monkeypatch.setattr(repair,"root_audit",lambda path,data:operations.append(
        ("audit",path.name,dict(data))))
    monkeypatch.setattr(repair,"stage_objects",lambda m,o:operations.append(("stage",)))
    monkeypatch.setattr(repair,"verify_objects",lambda m,o:operations.append(("verify_source",)))
    monkeypatch.setattr(repair,"rollback_objects",lambda *args,**kwargs:operations.append(("rollback",)))
    def system(*args,**kwargs):
        operations.append(("system",*args))
        if args[0]=="cat":
            return (str(repair.ROOT_SOURCE/"openclaw_authority_health_snapshot.py")
                    +" TimeoutStartSec=5700")
        return ""
    monkeypatch.setattr(repair,"system",system)
    monkeypatch.setattr(repair,"verify_full_proof",lambda after:operations.append(("full_pass",)))
    fast=tmp_path/"fast.json"
    fast.write_text(json.dumps({"status":"pass","failures":[]}))
    monkeypatch.setattr(repair,"FAST",fast)
    clock=[0]
    def root_readback(path):
        if path==repair.DRIFT:
            clock[0]+=1
            return {"status":"pass","problems":[],
                    "observed_at":f"2026-11-13T13:00:{clock[0]:02}Z"}
        return {"circuit_breaker":{"state":"closed"}}
    monkeypatch.setattr(repair,"protected_release_record",root_readback)
    monkeypatch.setattr(repair.time,"sleep",lambda seconds:None)
    monkeypatch.setattr(repair.subprocess,"run",lambda *a,**k:SimpleNamespace(returncode=0))
    repair.execute()
    stages=[i[0] for i in operations]
    assert "rollback" not in stages
    assert stages.index("audit")<stages.index("stage")
    assert stages.index("verify_source")<stages.index("full_pass")
    assert stages.count("full_pass")==1
    assert not emergency.exists()
    result=[i for i in operations if i[0]=="audit" and i[1].endswith(".result.json")][0][2]
    assert result["status"]=="verified"
    assert result["full_integrity_verified"] is True
    assert result["root_drift_distinct_passes"]==3
    assert result["root_breaker_closed"] is True


def test_disposable_fake_root_failed_full_proof_never_unlocks_breaker(
    tmp_path,monkeypatch,policy,
):
    import contextlib
    emergency=tmp_path/"expired-fast-overlay.conf"
    emergency.write_bytes(b"original-immutable-overlay")
    local_policy=dict(policy)
    local_policy["old_fast_emergency_sha256"]=sha256(emergency.read_bytes()).hexdigest()
    ledger=tmp_path/"ledger";ledger.mkdir(mode=0o700)
    class RootLedger:
        def lstat(self):return SimpleNamespace(st_mode=stat.S_IFDIR|0o700,st_uid=0)
        def is_symlink(self):return False
        def iterdir(self):return iter(())
        def __truediv__(self,item):return ledger/item
    monkeypatch.setattr(repair,"LEDGER",RootLedger())
    monkeypatch.setattr(repair,"FAST_EMERGENCY",emergency)
    monkeypatch.setattr(repair.os,"geteuid",lambda:0)
    monkeypatch.setattr(repair.sys,"flags",SimpleNamespace(isolated=1))
    monkeypatch.setattr(repair,"ROOT_SCRIPT",Path(repair.__file__).resolve())
    monkeypatch.setattr(repair,"fixed_policy",lambda:local_policy)
    monkeypatch.setattr(repair,"checked_bundle",lambda p:({"source":[],"new_unit_dropin":{}},{"file":b"x"}))
    monkeypatch.setattr(repair,"verified_initial_bootstrap_ledger",lambda:True)
    monkeypatch.setattr(repair,"root_state",lambda p:{"runtime_id":"rt","mcp_id":"mcp"})
    monkeypatch.setattr(repair,"signed_owner_decision",lambda *args:{"payload":{"exact":"approved"}})
    @contextlib.contextmanager
    def lock():yield
    monkeypatch.setattr(repair,"native_release_lock",lock)
    events=[]
    monkeypatch.setattr(repair,"root_audit",lambda path,data:events.append(("audit",path.name,dict(data))))
    monkeypatch.setattr(repair,"stage_objects",lambda m,o:events.append(("stage",)))
    monkeypatch.setattr(repair,"verify_objects",lambda m,o:events.append(("verify",)))
    monkeypatch.setattr(repair,"rollback_objects",lambda *a,**k:events.append(("rollback",)))
    def system(*args,**kwargs):
        events.append(("system",*args))
        return (str(repair.ROOT_SOURCE/"openclaw_authority_health_snapshot.py")
                +" TimeoutStartSec=5700") if args[0]=="cat" else ""
    monkeypatch.setattr(repair,"system",system)
    def fail_full(at):
        events.append(("proof_failed",))
        raise repair.RepairDenied("FULL_TIMEOUT")
    monkeypatch.setattr(repair,"verify_full_proof",fail_full)
    with pytest.raises(repair.RepairDenied,match="FULL_TIMEOUT"):
        repair.execute()
    assert emergency.read_bytes()==b"original-immutable-overlay"
    assert ("rollback",) in events
    assert not any(e[:3]==("system","start","jason-openclaw-authority-health.service")
                   for e in events)
    result=[e for e in events if e[0]=="audit" and e[1].endswith(".result.json")][0][2]
    assert result["status"]=="failed"
    assert result["full_integrity_verified"] is False
    assert result["root_breaker_closed"] is False
    assert result["source_rollback"]=="verified_absence"


def test_disposable_uid1000_signed_decision_is_verified_by_real_uid0_root(
    tmp_path,monkeypatch,policy,
):
    """Real UID0 test, synthetic al-owned proof and root-owned policy in /tmp."""
    import os
    if os.geteuid()!=0:
        pytest.skip("requires isolated disposable UID0 pytest job")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from implementation.kernel import signed_owner_release as verifier
    key=Ed25519PrivateKey.generate()
    archive=tmp_path/"owner-archive"
    archive.mkdir(mode=0o2770)
    os.chown(archive,1000,1000)
    archive.chmod(0o2770)
    policy_file=tmp_path/"installed-root-policy.json"
    policy_raw=canonical(policy)+b"\n"
    policy_file.write_bytes(policy_raw)
    policy_file.chmod(0o400)
    at=datetime.now(timezone.utc)
    proof=verifier.issue_exact_owner_release(
        approval_id="owner-mcp-"+"c"*32,
        release_id="release-"+repair.SOURCE[:16],
        candidate_sha=repair.SOURCE,rollback_sha=repair.LKG,
        scope_sha256=policy["scope_sha256"],
        manifest_sha256=sha256(policy_raw).hexdigest(),
        freeze_sha256=policy["freeze_sha256"],
        verified_tenant_id=verifier.TID,
        verified_owner_oid=verifier.OWNER_OID,
        verified_principal=verifier.EXACT_OWNER_OAUTH_SUBJECTS[verifier.OWNER_OID],
        verified_organization_id="aot",
        confirmed_decision="approve",at=at,private_key=key)
    decision={
        "schema_version":"1.0","action":repair.ACTION,
        "source_sha":repair.SOURCE,"scope_sha256":policy["scope_sha256"],
        "bundle_sha256":policy["bundle_sha256"],
        "root_policy_sha256":sha256(policy_raw).hexdigest(),
        "status":"AUTHENTICATED_OWNER_APPROVED_NOT_EXECUTED",
        "signed_owner_proof":proof,
    }
    file=archive/"one-verified-owner-decision.json"
    file.write_bytes(canonical(decision)+b"\n")
    file.chmod(0o600)
    os.chown(file,1000,1000)
    monkeypatch.setattr(repair,"POLICY",policy_file)
    monkeypatch.setattr(repair,"OWNER_SIGNED_DECISION",file)
    monkeypatch.setattr(repair,"load_trust",lambda path,name:verifier)
    monkeypatch.setattr(verifier,"read_pinned_root_owner_public_key",
                        lambda *args,**kwargs:key.public_key())
    assert repair.signed_owner_decision(policy,{})==proof
    file.chmod(0o644)
    with pytest.raises(repair.RepairDenied,match="SIGNED_OWNER_DECISION_FILE_UNTRUSTED"):
        repair.signed_owner_decision(policy,{})
    file.chmod(0o600)
    decision["action"]="unapproved-production-reboot"
    file.write_bytes(canonical(decision)+b"\n")
    with pytest.raises(repair.RepairDenied,match="SIGNED_OWNER_DECISION_EXACT_ACTION_DRIFT"):
        repair.signed_owner_decision(policy,{})


def test_prior_bootstrap_audit_is_verified_and_never_reused_as_new_approval(
    tmp_path,monkeypatch,
):
    from datetime import timedelta
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from implementation.kernel import signed_owner_release as verifier
    root=tmp_path/"historical-verified-root-ledger"
    root.mkdir()
    first=root/(repair.BOOTSTRAP_ACTION+".attempt.json")
    second=root/(repair.BOOTSTRAP_ACTION+".result.json")
    key=Ed25519PrivateKey.generate()
    earlier=datetime.now(timezone.utc)-timedelta(minutes=35)
    historic=verifier.issue_exact_owner_release(
        approval_id="owner-mcp-"+"d"*32,
        release_id="release-"+repair.BOOTSTRAP_SOURCE[:16],
        candidate_sha=repair.BOOTSTRAP_SOURCE,
        rollback_sha=repair.LKG,
        scope_sha256=repair.BOOTSTRAP_SCOPE,
        manifest_sha256=repair.BOOTSTRAP_MANIFEST_SHA,
        freeze_sha256="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f",
        verified_tenant_id=verifier.TID,
        verified_owner_oid=verifier.OWNER_OID,
        verified_principal=verifier.EXACT_OWNER_OAUTH_SUBJECTS[verifier.OWNER_OID],
        verified_organization_id="aot",
        confirmed_decision="approve",
        at=earlier,private_key=key,
    )
    attempt={
        "schema_version":"1.0",
        "action":repair.BOOTSTRAP_ACTION,
        "source_sha":repair.BOOTSTRAP_SOURCE,
        "scope_sha256":repair.BOOTSTRAP_SCOPE,
        "status":"claimed_before_root_trust_installation",
        "owner_proof":historic,
    }
    result={
        "schema_version":"1.0",
        "action":repair.BOOTSTRAP_ACTION,
        "source_sha":repair.BOOTSTRAP_SOURCE,
        "scope_sha256":repair.BOOTSTRAP_SCOPE,
        "status":"verified",
        "ledger_directory":str(root),
        "approved_files":[
            "/usr/local/lib/jason/owner_full_integrity_v2_root_repair.py",
            "/etc/jason-owner-release/owner-full-integrity-v2-repair-policy.json",
        ],
        "production_services_changed":False,
        "full_sqlite_scan_ran":False,
        "root_breaker_modified":False,
    }
    first.write_bytes(canonical(attempt)+b"\n")
    second.write_bytes(canonical(result)+b"\n")

    class PriorLedger:
        def lstat(self):
            return SimpleNamespace(
                st_uid=0,st_gid=0,st_mode=stat.S_IFDIR|0o700,
            )
        def is_symlink(self):return False
        def iterdir(self):return root.iterdir()
        def __truediv__(self,name):return root/name
        def __str__(self):return str(root)

    monkeypatch.setattr(repair,"LEDGER",PriorLedger())
    monkeypatch.setattr(repair,"read_secure_root",lambda path,*a,**k:path.read_bytes())
    monkeypatch.setattr(repair,"load_trust",lambda p,name:verifier)
    monkeypatch.setattr(verifier,"read_pinned_root_owner_public_key",
                        lambda *args,**kwargs:key.public_key())
    assert repair.verified_initial_bootstrap_ledger() is True
    # The bootstrap signature is historically valid but already expired; it
    # does not authorize a fresh live full-integrity production scan.
    with pytest.raises(verifier.OwnerReleaseProofDenied,match="EXPIRED"):
        verifier.verify_exact_owner_release(
            historic,public_key=key.public_key(),
            expected_candidate_sha=repair.BOOTSTRAP_SOURCE,
            expected_rollback_sha=repair.LKG,
            expected_release_id="release-"+repair.BOOTSTRAP_SOURCE[:16],
            expected_scope_sha256=repair.BOOTSTRAP_SCOPE,
            expected_manifest_sha256=repair.BOOTSTRAP_MANIFEST_SHA,
            expected_freeze_sha256="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f",
            at=datetime.now(timezone.utc),
        )
    unrelated=root/"foreign-audit.json"
    unrelated.write_text("foreign")
    with pytest.raises(repair.RepairDenied,match="FOREIGN_LEDGER"):
        repair.verified_initial_bootstrap_ledger()
    unrelated.unlink()
    result["status"]="failed"
    second.write_bytes(canonical(result)+b"\n")
    with pytest.raises(repair.RepairDenied,match="AUDIT_INCONSISTENT"):
        repair.verified_initial_bootstrap_ledger()


def test_root_check_only_requires_verified_bootstrap_audit_without_writes(
    monkeypatch,
):
    observed=[]
    monkeypatch.setattr(repair.os,"geteuid",lambda:0)
    monkeypatch.setattr(repair.sys,"argv",[
        "owner_full_integrity_v2_root_repair.py","--check-only",
    ])
    monkeypatch.setattr(repair,"fixed_policy",lambda:observed.append("policy") or {})
    monkeypatch.setattr(repair,"checked_bundle",lambda p:observed.append("bundle"))
    monkeypatch.setattr(
        repair,"verified_initial_bootstrap_ledger",
        lambda:observed.append("bootstrap_ledger"))
    monkeypatch.setattr(repair,"root_state",lambda p:observed.append("root_state"))
    assert repair.main()==0
    assert observed==["policy","bundle","bootstrap_ledger","root_state"]
    observed.clear()
    def refuse():
        raise repair.RepairDenied("FOREIGN_ROOT_BOOTSTRAP_LEDGER")
    monkeypatch.setattr(repair,"verified_initial_bootstrap_ledger",refuse)
    assert repair.main()==2
    assert observed==["policy","bundle"]
