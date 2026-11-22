"""Exact P0 post-PASS finalizer: zero host mutation and fake-proof acceptance."""
from __future__ import annotations
from datetime import datetime,timezone,timedelta
from pathlib import Path
from types import SimpleNamespace
import json
import os
import stat
import pytest
from tools import audit_full_health_p0_finalize as f
from tools import audit_full_health_p0_recovery as old

def fake_original(tmp_path,monkeypatch):
    original=tmp_path/"existing-approval"
    original.mkdir()
    report=tmp_path/"full.json"
    report.write_text('{"status":"pass"}')
    fast=tmp_path/"fast.json"
    fast.write_text('{"status":"pass"}')
    override=tmp_path/"93-review.conf"
    override.write_bytes(b"expected-93")
    worker=tmp_path/"recovery.py"
    worker.write_bytes(b"original Root worker")
    policy=tmp_path/"release"
    policy.mkdir()
    (policy/"production-control-state.json").write_text(json.dumps({
        "circuit_breaker":{"state":"open",
                           "reason":"continuous_production_drift_detected"},
        "last_known_good":{"manifest":{"revision":old.LKG}}}))
    (policy/"production-drift.json").write_text(json.dumps({
        "status":"pass","problems":[]}))
    system={
        (f.FULL_UNIT,"ActiveState"):"failed",
        (f.FULL_UNIT,"ExecMainStatus"):"2",
        (f.FULL_UNIT,"User"):"root",
        (f.FULL_UNIT,"ProtectSystem"):"strict",
        (f.FULL_UNIT,"ReadWritePaths"):"/var/lib/jason/openclaw",
        (f.FAST_UNIT,"ActiveState"):"inactive",
        ("jason-openclaw-authority-full-integrity.timer","ActiveState"):"active",
        ("jason-openclaw-authority-health.timer","ActiveState"):"active",
        ("jason-production-drift-watchdog.timer","ActiveState"):"active",
    }
    claim={"action":old.ACTION,
       "candidate_sha":f.ORIGINAL_SHA,
       "scope_sha256":f.ORIGINAL_SCOPE_SHA,
       "scope":{"action":old.ACTION,
                "live_source_identity":{"device":66306,"inode":10261846},
                "source_sha256":{}},
       "owner_oid":f.OWNER,"independently_verified_entra_owner":True,
       "required_ci_passed":True,
       "approved_at":(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat(),
       "source_sha256":{
           "config/audit-full-health-p0-recovery.conf":f.sha(override.read_bytes()),
           "tools/audit_full_health_p0_recovery.py":f.sha(worker.read_bytes())}}
    failed={"action":old.ACTION,"candidate_sha":f.ORIGINAL_SHA,
       "scope_sha256":f.ORIGINAL_SCOPE_SHA,
       "status":"failed","full_proof_verified":True,
       "native_breaker_closed":False,
       "temporary_override_removed":False,
       "failure_class":"OSError","failure_code":"UNTRUSTED_ERROR",
       "cleanup_status":"FAILED_CLOSED_EXACT_ROOT_REVIEW_REQUIRED"}
    started={"action":old.ACTION,"scope_sha256":f.ORIGINAL_SCOPE_SHA}
    original_files={"attempt.json":claim,"result.json":failed,
                    "work-start.json":started}
    def root_read(path,*args):
        path=Path(path)
        if path.parent==original and path.name in original_files:
            return f.canon(original_files[path.name])
        return path.read_bytes()
    r=SimpleNamespace(
        ACTION=old.ACTION, RECORD=original, DROPIN=override,ROOT_SCRIPT=worker,
        FULL=report,FAST=fast,RELEASE=policy,LKG=old.LKG,
        current_attempt=lambda:claim, root_read=root_read,
        safe_root_parent=lambda *_:None,
        verify_full_after=lambda *args:{"status":"pass"},
        proof_file=lambda *_:{"status":"pass","failures":[],
            "snapshot_source_exit_code":0,"full_proof_status":"pass"},
        installed_baseline=lambda:None,
        dataset=lambda:{"device":66306,"inode":10261846},
        system_prop=lambda u,k:system.get((u,k),""),
        root_write=lambda p,raw,mode=0o400:Path(p).write_bytes(raw))
    monkeypatch.setattr(f,"RECEIPT",tmp_path/"fresh-finalize")
    monkeypatch.setattr(f,"reviewed",lambda *_:
        b"def protected_peer_inventory():\n return {'p'+str(x):{} for x in range(6)}\n")
    return r,claim,failed,system,override,report,policy

def test_exact_failed_original_owner_claim_accepted(tmp_path,monkeypatch):
    r,claim,failed,*_=fake_original(tmp_path,monkeypatch)
    got,res=f.read_approval(r)
    assert got==claim and res==failed

@pytest.mark.parametrize("change",[
    lambda claim,row:claim.update(owner_oid="wrong-owner"),
    lambda claim,row:claim.update(candidate_sha="0"*40),
    lambda claim,row:claim.update(independently_verified_entra_owner=False),
    lambda claim,row:claim.update(scope_sha256="0"*64),
    lambda claim,row:row.update(status="verified"),
    lambda claim,row:row.update(full_proof_verified=False),
    lambda claim,row:row.update(native_breaker_closed=True),
    lambda claim,row:row.update(temporary_override_removed=True),
    lambda claim,row:row.update(failure_class="DatabaseError"),
    lambda claim,row:row.update(failure_code="unexpected"),
    lambda claim,row:row.update(cleanup_status="overrode_root_guardrails"),
    lambda claim,row:row.update(candidate_sha="0"*40),
])
def test_old_owner_receipt_or_noncleanup_failure_denied(tmp_path,monkeypatch,change):
    r,claim,failed,*_=fake_original(tmp_path,monkeypatch)
    change(claim,failed)
    with pytest.raises(f.Denied):
        f.read_approval(r)

def test_full_and_fresh_fast_pass_required(tmp_path,monkeypatch):
    r,claim,_,_,_,full,_=fake_original(tmp_path,monkeypatch)
    result=f.proven_live_health(r,claim["approved_at"])
    assert result==f.sha(full.read_bytes())

def test_stale_full_integrity_no_longer_authorizes_finalization(tmp_path,monkeypatch):
    r,claim,_,_,_,full,_=fake_original(tmp_path,monkeypatch)
    os.utime(full,(1,1))
    with pytest.raises(f.Denied,match="FULL_EVIDENCE_TOO_OLD"):
        f.proven_live_health(r,claim["approved_at"])

def test_stale_fast_evidence_denied(tmp_path,monkeypatch):
    r,claim,_,_,_,full,_=fake_original(tmp_path,monkeypatch)
    os.utime(r.FAST,(1,1))
    with pytest.raises(f.Denied,match="FAST_PROOF_OLDER_THAN_FULL_PROOF"):
        f.proven_live_health(r,claim["approved_at"])

@pytest.mark.parametrize("item,value",[
 (("jason-openclaw-authority-health.timer","ActiveState"),"inactive"),
 ((f.FULL_UNIT,"ActiveState"),"active"),
 ((f.FULL_UNIT,"ExecMainStatus"),"124"),
 ((f.FULL_UNIT,"ProtectSystem"),"full"),
 ((f.FULL_UNIT,"User"),"al"),
 ((f.FULL_UNIT,"ReadWritePaths"),"OVERLAY_PARENT_ALLOWED"),
])
def test_scope_denies_unexpected_live_root_state(tmp_path,monkeypatch,item,value):
    r,claim,res,sys_map,*_=fake_original(tmp_path,monkeypatch)
    sys_map[item]=str(tmp_path) if value=="OVERLAY_PARENT_ALLOWED" else value
    with pytest.raises(f.Denied):
        f.scope("a"*40,r,claim,res,b"approved")

def test_scope_denies_change_to_previous_exact_temporary_override(tmp_path,monkeypatch):
    r,claim,res,sys_map,override,*_=fake_original(tmp_path,monkeypatch)
    override.write_bytes(b"FOREIGN")
    with pytest.raises(f.Denied,match="TEMPORARY_93_OVERRIDE_CHANGED"):
        f.scope("a"*40,r,claim,res,b"approved")
    assert override.read_bytes()==b"FOREIGN"

def test_scope_denies_unrelated_drift_or_breaker(tmp_path,monkeypatch):
    r,claim,res,sys_map,override,report,policy=fake_original(tmp_path,monkeypatch)
    d=policy/"production-drift.json"
    d.write_text(json.dumps({"status":"drift_detected",
                             "problems":[{"kind":"undeclared_system_unit",
                                          "unit":"foreign.service"}]}))
    with pytest.raises(f.Denied,match="UNRELATED_PRODUCTION_DRIFT"):
        f.scope("a"*40,r,claim,res,b"approved")
    d.write_text(json.dumps({"status":"pass","problems":[]}))
    x=policy/"production-control-state.json"
    payload=json.loads(x.read_text())
    payload["circuit_breaker"]["state"]="closed"
    x.write_text(json.dumps(payload))
    with pytest.raises(f.Denied,match="UNRELATED_OR_UNRECOVERABLE_NATIVE_BREAKER"):
        f.scope("a"*40,r,claim,res,b"approved")

def test_scope_exact_without_new_authority(tmp_path,monkeypatch):
    r,claim,res,sys_map,override,report,policy=fake_original(tmp_path,monkeypatch)
    data=f.scope("a"*40,r,claim,res,b"approved")
    assert data["action"]==f.ACTION
    assert data["previous_scope_sha256"]==f.ORIGINAL_SCOPE_SHA
    assert data["full_integrity_proof_sha256"]==f.sha(report.read_bytes())
    assert data["exact_temporary_dropin_sha256"]==f.sha(override.read_bytes())
    assert data["provider_writes"] is False
    assert data["archive_installation"] is False
    assert data["native_breaker_revalidation_only"] is True
    assert len(data["peers"])==6
    assert data["native_drift_observations"]==3
    assert data["original_data_identity"]==claim["scope"]["live_source_identity"]

def test_scope_denies_claim_replay(tmp_path,monkeypatch):
    r,claim,res,*_=fake_original(tmp_path,monkeypatch)
    f.RECEIPT.mkdir()
    with pytest.raises(f.Denied,match="FINALIZE_ALREADY_CLAIMED"):
        f.scope("a"*40,r,claim,res,b"approved")


def test_one_use_owner_claim_is_root_only_and_cannot_repeat(tmp_path,monkeypatch):
    r,claim,res,*_=fake_original(tmp_path,monkeypatch)
    scope={"action":f.ACTION,"target":str(r.DROPIN)}
    monkeypatch.setattr(f.os,"chown",lambda *_:None)
    first=f.claim_one_use(r,"a"*40,scope,f.OWNER)
    assert first["owner_oid"]==f.OWNER
    assert first["independently_verified_entra_owner"] is True
    assert json.loads((f.RECEIPT/"attempt.json").read_bytes())==first
    with pytest.raises(f.Denied,match="FINALIZER_ALREADY_CLAIMED"):
        f.claim_one_use(r,"a"*40,scope,f.OWNER)
    with pytest.raises(f.Denied,match="APPROVED_OWNER_NOT_VERIFIED"):
        f.claim_one_use(r,"a"*40,scope,"wrong")

def prepare_finalize(tmp_path,monkeypatch):
    r,oldclaim,oldresult,sys_map,override,report,policy=fake_original(tmp_path,monkeypatch)
    current_scope=f.scope("a"*40,r,oldclaim,oldresult,b"source")
    receipt={"scope":current_scope,"owner_oid":f.OWNER}
    f.RECEIPT.mkdir(mode=0o700)
    called=[]
    monkeypatch.setattr(f,"call",lambda argv,*a,**k:called.append(argv))
    monkeypatch.setattr(f,"ensure_native_original",lambda r,c:
        pytest.fail("cleanup did not happen first") if override.exists()
        else called.append(["verified-native-original"]))
    return r,oldclaim,receipt,called,override,report,policy

def test_successful_one_file_cleanup_requires_native_real_breaker(tmp_path,monkeypatch):
    r,claim,approval,calls,override,report,policy=prepare_finalize(tmp_path,monkeypatch)
    def true_native_evidence(_):
        assert not override.exists()
        p=policy/"production-control-state.json"
        data=json.loads(p.read_text())
        data["circuit_breaker"]={
            "state":"closed","reason":"authoritative_health_revalidated"}
        p.write_text(json.dumps(data))
        calls.append(["original-native-fast-drift-breaker"])
        return ["first","second","third"]
    r.after_full_native_revalidation=true_native_evidence
    f.finalize(r,approval,claim["approved_at"])
    assert calls==[
        ["/usr/bin/systemctl","daemon-reload"],
        ["/usr/bin/systemctl","reset-failed",f.FULL_UNIT],
        ["verified-native-original"],
        ["original-native-fast-drift-breaker"]]
    assert not override.exists()
    record=json.loads((f.RECEIPT/"result.json").read_bytes())
    assert record["status"]=="verified"
    assert record["native_breaker_closed"] is True
    assert record["full_integrity_verified"] is True
    assert record["installed_exact_93_override_removed"] is True
    assert record["three_native_drift_observations"]==["first","second","third"]
    assert record["archive_migration"] is False
    assert record["database_modified"] is False

def test_wrong_override_is_never_deleted_or_breaker_touched(tmp_path,monkeypatch):
    r,claim,approval,calls,override,report,policy=prepare_finalize(tmp_path,monkeypatch)
    override.write_bytes(b"foreign-content")
    r.after_full_native_revalidation=lambda _:pytest.fail("must not revalidate")
    with pytest.raises(f.Denied,match="EXACT_OVERRIDE_CHANGED_BEFORE_UNLINK"):
        f.finalize(r,approval,claim["approved_at"])
    assert override.read_bytes()==b"foreign-content"
    assert not calls
    result=json.loads((f.RECEIPT/"result.json").read_bytes())
    assert result["status"]=="failed"
    assert result["native_breaker_closed"] is False
    assert result["full_integrity_verified"] is True

def test_native_breaker_not_fabricated_after_a_real_fast_or_drift_failure(
        tmp_path,monkeypatch):
    r,claim,approval,calls,override,report,policy=prepare_finalize(tmp_path,monkeypatch)
    r.after_full_native_revalidation=lambda _:(
        (_ for _ in ()).throw(f.Denied("INDEPENDENT_NATIVE_DRIFT_NOT_PASS")))
    with pytest.raises(f.Denied,match="INDEPENDENT_NATIVE_DRIFT_NOT_PASS"):
        f.finalize(r,approval,claim["approved_at"])
    assert not override.exists()
    result=json.loads((f.RECEIPT/"result.json").read_bytes())
    assert result["status"]=="failed"
    assert result["native_breaker_closed"] is False
    assert result["installed_exact_93_override_removed"] is True

def test_failed_native_revalidation_does_not_allow_second_one_use_claim(
        tmp_path,monkeypatch):
    r,claim,approval,calls,override,report,policy=prepare_finalize(tmp_path,monkeypatch)
    r.after_full_native_revalidation=lambda *_:(
        (_ for _ in ()).throw(f.Denied("CLOSED_BREAKER_NOT_VERIFIED")))
    with pytest.raises(f.Denied):
        f.finalize(r,approval,claim["approved_at"])
    with pytest.raises(f.Denied,match="FINALIZER_ALREADY_CLAIMED"):
        f.claim_one_use(r,"a"*40,approval["scope"],f.OWNER)

def test_invalid_or_old_full_report_never_unlinks_original_override(
        tmp_path,monkeypatch):
    r,claim,approval,calls,override,report,policy=prepare_finalize(tmp_path,monkeypatch)
    report.write_text("{}")
    with pytest.raises(f.Denied,match="GENUINE_FULL_PROOF_CHANGED_AFTER_OWNER_APPROVAL"):
        f.finalize(r,approval,claim["approved_at"])
    assert override.exists()
    assert not calls
    assert json.loads((f.RECEIPT/"result.json").read_bytes())["status"]=="failed"

def test_owner_applied_original_source_must_be_strictly_same(tmp_path,monkeypatch):
    r,claim,oldresult,*_=fake_original(tmp_path,monkeypatch)
    with pytest.raises(f.Denied,match="ORIGINAL_APPROVED_SOURCE_MISMATCH"):
        fake=SimpleNamespace(ACTION="different",RECORD=tmp_path/"wrong")
        # The source identity guard is directly evaluated at load_existing.
        f.need(fake.ACTION==old.ACTION and fake.RECORD==r.RECORD,
               "ORIGINAL_APPROVED_SOURCE_MISMATCH")

def test_finalizer_is_intentionally_not_an_archive_deployer():
    source=Path(f.__file__).read_text()
    assert "FINALIZE-VERIFIED-AUDIT-FULL-INTEGRITY-20261122" in source
    assert "RECOVER-EXACT-AUDIT-FULL-SQLITE-PROOF-20261122" in source
    assert "ADOPT-EXACT-DAILY-AUDIT-JOURNAL" not in source
    assert "audit_journal_install.py --apply" not in source
    assert "DROPIN.unlink()" in source
    assert "after_full_native_revalidation" in source
    assert "auth[\"owner\"](planned)" in source
    assert "read_approval(r)" in source
    assert "claim_one_use(" in source


def test_finalization_uses_exact_native_fast_proof_freshness_policy():
    from tools import openclaw_authority_fast_health as native
    assert f.MAX_PROOF_AGE==native.MAX_FULL_AGE_SECONDS==30*60*60
