"""Source-only, synthetic P0 full health recovery tests. No Root or host edits."""
from datetime import datetime,timezone
from pathlib import Path
import json
import os
import sqlite3
import stat
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from tools import audit_full_health_p0_recovery as r
from tools import audit_full_health_p0_snapshot as snap
from tools import audit_full_health_p0_operational as checker

ROOT=Path(__file__).resolve().parents[2]

@pytest.fixture
def complete_proof():
    files={}
    names={
      "authority":"/var/lib/jason/authority/authority.sqlite3",
      "replay":"/var/lib/jason/openclaw/replay.sqlite3",
      "security_audit":"/var/lib/jason/openclaw/security-audit.sqlite3",
      "orchestration_audit":str(r.LIVE),
    }
    for k,path in names.items():
        files[k]={"path":path,"present":True,"mode":"0o600","integrity":"ok"}
    return {"status":"pass","failures":[],"snapshot_source_exit_code":0,
     "provider_contacted":False,"provider_credentials_used":False,
     "files":files,"backup_restore_proof":{
       "backup_integrity":"ok","restore_integrity":"ok",
       "backup_mode":"0o600","restore_mode":"0o600","counts_match":True},
     "trusted_key_registry":{"present":True,"mode":"0o600","active_records":1},
     "delegations":{"expired_active_records":0}}

def write_report(tmp_path,monkeypatch,data):
    path=tmp_path/"full.json"
    path.write_text(json.dumps(data))
    path.chmod(0o600)
    monkeypatch.setattr(r,"FULL",path)
    # GitHub's unprivileged runner has a variable UID. Supply only the
    # synthetic lstat UID for this disposable test file, leaving the actual
    # production UID=1000 check in recovery.py unchanged and executable.
    original=Path.lstat
    def synthetic_uid(self,*args,**kwargs):
        meta=original(self,*args,**kwargs)
        if self!=path:return meta
        from types import SimpleNamespace
        return SimpleNamespace(st_mode=meta.st_mode,st_uid=1000,
             st_nlink=meta.st_nlink,st_size=meta.st_size,
             st_mtime=meta.st_mtime)
    monkeypatch.setattr(Path,"lstat",synthetic_uid)
    return path

def test_one_use_scope_constants_and_full_sqlite_non_bypass():
    assert r.ACTION=="RECOVER-EXACT-AUDIT-FULL-SQLITE-PROOF-20261122"
    assert r.CHILD_DEADLINE==21000 and r.JOB_DEADLINE==21600
    assert r.UNIT=="jason-openclaw-authority-full-integrity.service"
    assert r.DROPIN.name=="93-audit-full-health-p0-recovery.conf"
    assert snap.DEADLINE==21000
    assert snap.TRUSTED_ENTRYPOINT==r.ROOT_BASE/"openclaw_authority_live_audit_full_snapshot.py"
    assert snap.AUDIT==r.LIVE
    assert len(r.SOURCES)==5
    assert "PRAGMA integrity_check" in Path(checker.__file__).read_text()
    assert "PRAGMA quick_check" not in Path(checker.__file__).read_text()
    assert r.RECORD.parent==Path("/var/lib/jason-owner-release")
    assert r.LKG=="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"

def test_real_tiny_full_integrity_and_corruption(tmp_path):
    path=tmp_path/"clean.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE note (id INTEGER PRIMARY KEY, value TEXT)")
        db.executemany("INSERT INTO note(value) VALUES(?)",[(str(n),) for n in range(100)])
    assert checker.sqlite_integrity(path)=="ok"
    path.write_bytes(b"not-a-sqlite-database")
    with pytest.raises(sqlite3.DatabaseError):
        checker.sqlite_integrity(path)

@pytest.mark.parametrize("mutate",[
    lambda x:x.update(status="fail"),
    lambda x:x.update(snapshot_source_exit_code=124),
    lambda x:x.update(provider_contacted=True),
    lambda x:x["files"]["orchestration_audit"].update(integrity="not-run"),
    lambda x:x["files"]["orchestration_audit"].update(path="/tmp/wrong"),
    lambda x:x["files"].pop("replay"),
    lambda x:x["backup_restore_proof"].update(counts_match=False),
    lambda x:x["backup_restore_proof"].update(restore_integrity="failed"),
    lambda x:x["trusted_key_registry"].update(active_records=0),
    lambda x:x["delegations"].update(expired_active_records=1),
])
def test_no_partial_or_fabricated_full_proof(tmp_path,monkeypatch,complete_proof,mutate):
    mutate(complete_proof)
    write_report(tmp_path,monkeypatch,complete_proof)
    with pytest.raises(r.Denied):
        r.verify_full_after(datetime.now(timezone.utc).isoformat())

def test_real_complete_proof_requires_freshness(tmp_path,monkeypatch,complete_proof):
    p=write_report(tmp_path,monkeypatch,complete_proof)
    assert r.verify_full_after(datetime.fromtimestamp(p.stat().st_mtime-10,timezone.utc).isoformat())==complete_proof
    with pytest.raises(r.Denied,match="FULL_EVIDENCE_NOT_FRESH"):
        r.verify_full_after(datetime.fromtimestamp(p.stat().st_mtime+60,timezone.utc).isoformat())

def test_source_not_root_refuses_production_entry():
    with pytest.raises(r.Denied,match="EXACT_ISOLATED_ROOT_REQUIRED"):
        r.source_bootstrap("a"*40)

def test_no_previous_claim_cannot_reuse_same_target(tmp_path,monkeypatch):
    rec=tmp_path/"claimed"
    rec.mkdir()
    monkeypatch.setattr(r,"RECORD",rec)
    monkeypatch.setattr(r,"ROOT_BASE",tmp_path/"not-yet")
    with pytest.raises(r.Denied,match="ONE_USE_RECOVERY_ALREADY_CLAIMED"):
        r.no_previous_claim()

def test_current_baseline_requires_actual_92_not_old_emergency(monkeypatch):
    live={
       str(r.FULL_DROPIN):r.EXPECTED_FULL_DROPIN,
       str(r.FAST_DROPIN):r.EXPECTED_FAST_DROPIN,
       str(r.CURRENT_WRAPPER):r.EXPECTED_FULL_WRAPPER,
    }
    monkeypatch.setattr(r,"root_read",lambda p,*a:bytes.fromhex("00") if str(p) not in live else b"a")
    monkeypatch.setattr(r,"sha",lambda raw:next(iter(live.values())) if raw==b"a" else "wrong")
    with pytest.raises(r.Denied,match="CURRENT_INSTALLED_SOURCE_CHANGED"):
        r.installed_baseline()

def test_proof_claim_requires_independently_verified_owner(tmp_path,monkeypatch):
    rec=tmp_path/"private"
    rec.mkdir(mode=0o700)
    mono={"action":r.ACTION,"owner_oid":r.OWNER,
          "independently_verified_entra_owner":False,
          "status":"claimed_before_root_files_or_job",
          "scope":{"source_sha256":{}},
          "scope_sha256":"bogus","source_sha256":{},
          "required_ci_passed":True}
    (rec/"attempt.json").write_text(json.dumps(mono))
    monkeypatch.setattr(r,"RECORD",rec)
    monkeypatch.setattr(r,"safe_root_parent",lambda p:None)
    monkeypatch.setattr(r,"root_read",lambda p,*a:p.read_bytes())
    with pytest.raises(r.Denied,match="ROOT_SIGNED_SCOPE_CLAIM_INVALID"):
        r.current_attempt()

def test_existing_native_full_unit_only_no_transient_or_unknown_service(monkeypatch):
    calls=[]
    monkeypatch.setattr(r,"command",lambda argv,**kw:calls.append(list(argv)))
    monkeypatch.setattr(r,"system_prop",lambda unit,key:
        str(r.ROOT_SCRIPT) if key=="ExecStart" else "root")
    assert r.schedule_worker()==r.UNIT
    assert calls==[
      ["/usr/bin/systemctl","daemon-reload"],
      ["/usr/bin/systemctl","reset-failed",r.UNIT],
      ["/usr/bin/systemctl","--no-block","start",r.UNIT],
    ]
    assert all("systemd-run" not in " ".join(argv) for argv in calls)

def test_no_watchdog_or_breaker_action_before_real_full_pass(monkeypatch):
    commands=[]
    monkeypatch.setattr(r,"verify_full_after",lambda *_: (_ for _ in ()).throw(r.Denied("NOT_A_PASS")))
    monkeypatch.setattr(r,"system",lambda *a,**kw:commands.append(a))
    with pytest.raises(r.Denied,match="NOT_A_PASS"):
        r.after_full_native_revalidation("2026-11-22T00:00:00+00:00")
    assert commands==[]

def test_worker_consumed_proof_and_native_verify(monkeypatch,tmp_path):
    record=tmp_path/"private"
    record.mkdir()
    monkeypatch.setattr(r,"RECORD",record)
    proof={"action":r.ACTION,"candidate_sha":"a"*40,
           "scope_sha256":"aabb","approved_at":"2026-11-22T00:00:00+00:00",
           "scope":{"live_source_identity":{"device":1,"inode":2}}}
    monkeypatch.setattr(r,"assert_worker_environment",lambda:None)
    monkeypatch.setattr(r,"current_attempt",lambda:proof)
    monkeypatch.setattr(r,"installed_baseline",lambda:None)
    monkeypatch.setattr(r,"health_gate",lambda **kwargs:None)
    monkeypatch.setattr(r,"dataset",lambda:{"device":1,"inode":2})
    monkeypatch.setattr(r,"run_full",lambda:0)
    monkeypatch.setattr(r,"verify_full_after",lambda *_:True)
    monkeypatch.setattr(r,"after_full_native_revalidation",lambda *_:["a","b","c"])
    monkeypatch.setattr(r,"root_write",lambda path,data,mode=0o400:path.write_bytes(data))
    monkeypatch.setattr(r,"rollback_override",lambda *_:None)
    monkeypatch.setattr(r,"root_read",lambda *_:b"reviewed")
    r.worker()
    result=json.loads((record/"result.json").read_text())
    assert result["status"]=="verified" and result["full_proof_verified"] is True
    assert result["native_breaker_closed"] is True and result["provider_writes"] is False

def test_worker_failed_full_proof_cannot_claim_success(monkeypatch,tmp_path):
    record=tmp_path/"private";record.mkdir()
    monkeypatch.setattr(r,"RECORD",record)
    monkeypatch.setattr(r,"assert_worker_environment",lambda:None)
    monkeypatch.setattr(r,"current_attempt",lambda:{"candidate_sha":"a"*40,
        "scope_sha256":"aabb","approved_at":"2026-11-22T00:00:00+00:00",
        "scope":{"live_source_identity":{"device":1,"inode":2}}})
    monkeypatch.setattr(r,"installed_baseline",lambda:None)
    monkeypatch.setattr(r,"health_gate",lambda **kwargs:None)
    monkeypatch.setattr(r,"dataset",lambda:{"device":1,"inode":2})
    monkeypatch.setattr(r,"run_full",lambda:124)
    downstream=Mock()
    monkeypatch.setattr(r,"DROPIN",tmp_path/"nonexistent")
    monkeypatch.setattr(r,"after_full_native_revalidation",downstream)
    monkeypatch.setattr(r,"root_write",lambda path,data,mode=0o400:path.write_bytes(data))
    with pytest.raises(r.Denied,match="GENUINE_FULL_SQLITE_PROOF_EXIT_NONZERO"):
        r.worker()
    result=json.loads((record/"result.json").read_text())
    assert result["status"]=="failed" and result["native_breaker_closed"] is False
    downstream.assert_not_called()


def test_approved_override_has_exact_one_use_full_scanner_only():
    p=ROOT/"config/audit-full-health-p0-recovery.conf"
    raw=p.read_text()
    assert "User=root" in raw and "ExecStart=" in raw
    assert raw.count("ExecStart=/usr/bin/python3 -I -B ")==1
    assert "--worker" in raw and "TimeoutStartSec=21600" in raw
    assert "ReadOnlyPaths=" in raw and "ReadWritePaths=" in raw
    assert "jason-audit-full-health-p0" not in raw
    assert "ExecStartPost" not in raw


def test_current_root_recovery_refuses_obsolete_overlay_by_design():
    source=(ROOT/"tools/audit_full_health_p0_recovery.py").read_text()
    assert "EXPIRED_EMERGENCY_OVERRIDE_REAPPEARED" in source
    assert "jason-openclaw-authority-health.service.d/92-owner-live-audit-location.conf" in source
    assert "jason-openclaw-authority-full-integrity.service.d/92-owner-live-audit-location.conf" in source
    assert "ONE_USE_WORKER_ALREADY_STARTED" in source
    assert "production-control-state.json" in source


def test_worker_does_not_replay_a_previous_claim(monkeypatch,tmp_path):
    record=tmp_path/"private";record.mkdir()
    (record/"work-start.json").write_text("already claimed")
    monkeypatch.setattr(r,"RECORD",record)
    monkeypatch.setattr(r,"assert_worker_environment",lambda:None)
    monkeypatch.setattr(r,"current_attempt",lambda:{
        "candidate_sha":"a"*40,"scope_sha256":"claimed",
        "scope":{"live_source_identity":{"inode":1,"device":2}}})
    monkeypatch.setattr(r,"installed_baseline",lambda:None)
    monkeypatch.setattr(r,"health_gate",lambda **kwargs:None)
    monkeypatch.setattr(r,"dataset",lambda:{"inode":1,"device":2})
    with pytest.raises(r.Denied,match="ONE_USE_WORKER_ALREADY_STARTED"):
        r.worker()


def test_known_current_failed_health_is_only_eligible_root_state(monkeypatch):
    control={"circuit_breaker":{"state":"open","reason":"continuous_production_drift_detected"},
             "last_known_good":{"manifest":{"revision":r.LKG}}}
    drift={"status":"drift_detected","problems":[
        {"kind":"failed_system_unit","state":"failed",
         "unit":"jason-openclaw-authority-health.service"}]}
    monkeypatch.setattr(r,"root_read",lambda p,*args:
        json.dumps(control if p.name=="production-control-state.json" else drift).encode())
    def state(path):return ({
       "ActiveState":"failed","ExecMainStatus":"124",
    } if "full-integrity" in path else {
       "ActiveState":"failed"
    })
    monkeypatch.setattr(r,"system_prop",lambda unit,key:
        "active" if unit.endswith(".timer") else state(unit).get(key,"active"))
    monkeypatch.setattr(r,"proof_file",lambda p:{
       "status":"fail",
       "failures": (["operational_health_timeout"] if p==r.FULL
                   else ["full_integrity_proof_missing_stale_or_invalid"]),
       "snapshot_source_exit_code":124})
    assert r.health_gate() is None
    with pytest.raises(r.Denied,match="ACTUAL_SYSTEMD_HEALTH_CHANGED"):
        r.health_gate(full_unit_must_be_failed=False)

@pytest.mark.parametrize("changed",["breaker","drift","full","fast"])
def test_unrelated_health_changes_are_denied(monkeypatch,changed):
    control={"circuit_breaker":{"state":"open","reason":"continuous_production_drift_detected"},
             "last_known_good":{"manifest":{"revision":r.LKG}}}
    drift={"status":"drift_detected","problems":[{
        "kind":"failed_system_unit","state":"failed",
        "unit":"jason-openclaw-authority-health.service"}]}
    if changed=="breaker":control["circuit_breaker"]["state"]="closed"
    if changed=="drift":drift["problems"].append({
       "kind":"undeclared_installed_system_unit","state":"active","unit":"rogue.service"})
    monkeypatch.setattr(r,"root_read",lambda p,*a:
        json.dumps(control if p.name=="production-control-state.json" else drift).encode())
    monkeypatch.setattr(r,"system_prop",lambda unit,key:
        "124" if key=="ExecMainStatus" else ("failed" if key=="ActiveState" and unit.endswith(".service") else "active"))
    monkeypatch.setattr(r,"proof_file",lambda p:{
       "status":"fail",
       "failures": (["bogus"] if (changed=="full" and p==r.FULL)
                    or (changed=="fast" and p==r.FAST)
                    else ["operational_health_timeout"] if p==r.FULL
                    else ["full_integrity_proof_missing_stale_or_invalid"]),
       "snapshot_source_exit_code":124})
    with pytest.raises(r.Denied):
        r.health_gate()

def test_scope_no_breaker_bypass_and_only_existing_health_service(monkeypatch):
    monkeypatch.setattr(r,"installed_baseline",lambda:None)
    monkeypatch.setattr(r,"health_gate",lambda:None)
    monkeypatch.setattr(r,"dataset",lambda:{"inode":14,"device":5})
    monkeypatch.setattr(r,"no_previous_claim",lambda:None)
    monkeypatch.setattr(r,"root_read",lambda p,*args:b"reviewed")
    c={"peers":lambda:{f"peer-{i}":{"image":f"sha256:{i}","id":f"{i}"} for i in range(6)}}
    fake_peer_source=("def protected_peer_inventory(): return "+
        repr(c["peers"]())+"\n").encode()
    monkeypatch.setattr(r,"exact_source",lambda candidate,name:fake_peer_source)
    blobs={name:name.encode() for name in r.SOURCES}
    scope=r.review_scope("a"*40,blobs,c)
    assert scope["protected_peers_source_sha256"]==r.sha(fake_peer_source)
    assert scope["isolated_preproduction_shadow_health_is_observed_not_a_core_dependency"] is True
    assert scope["action"]==r.ACTION
    assert scope["native_root_breaker_bypass_allowed"] is False
    assert scope["audit_data_deletion_allowed"] is False
    assert scope["audit_db_schema_change_allowed"] is False
    assert scope["existing_root_state_sha256"]!= {}
    assert scope["installation_targets"][-1]==r.UNIT
    assert r.UNIT in scope["installation_targets"]
    assert scope["queue_cutover"] is False
    assert scope["full_child_timeout_seconds"]==21000
    assert scope["temporary_override_must_be_removed_before_breaker_revalidation"] is True

def test_rollback_removes_only_exact_override(tmp_path,monkeypatch):
    name=tmp_path/"93-exact.conf"
    raw=b"owned-bounded-content\n"
    name.write_bytes(raw)
    monkeypatch.setattr(r,"DROPIN",name)
    monkeypatch.setattr(r,"root_read",lambda p,*a:p.read_bytes())
    calls=[]
    monkeypatch.setattr(r,"command",lambda a,**kw:calls.append(a))
    r.rollback_override({"config/audit-full-health-p0-recovery.conf":raw})
    assert not name.exists()
    assert calls==[["/usr/bin/systemctl","daemon-reload"]]

def test_rollback_never_removes_changed_or_replaced_data(tmp_path,monkeypatch):
    name=tmp_path/"93-foreign.conf"
    name.write_bytes(b"FOREIGN!")
    monkeypatch.setattr(r,"DROPIN",name)
    monkeypatch.setattr(r,"root_read",lambda p,*a:p.read_bytes())
    monkeypatch.setattr(r,"command",lambda a,**kw:pytest.fail("NO systemd on mismatch"))
    with pytest.raises(r.Denied,match="ROOT_OVERRIDE_CHANGED_NO_DELETE"):
        r.rollback_override({"config/audit-full-health-p0-recovery.conf":b"reviewed"})
    assert name.read_bytes()==b"FOREIGN!"

def test_fail_closed_root_write_requires_no_preexisting_file(tmp_path,monkeypatch):
    name=tmp_path/"immutable.json"
    name.write_text("older")
    monkeypatch.setattr(r,"safe_root_parent",lambda *_:None)
    with pytest.raises(FileExistsError):
        r.root_write(name,b"changed")
    assert name.read_text()=="older"

def test_full_sqlite_timeout_worker_kills_only_own_process_group(monkeypatch):
    fake=Mock()
    fake.pid=44332
    fake.wait.side_effect=[__import__("subprocess").TimeoutExpired("scanner",100),0]
    spawned=[]
    monkeypatch.setattr(r.subprocess,"Popen",lambda *a,**k:(spawned.append((a,k)),fake)[1])
    killed=[]
    monkeypatch.setattr(r.os,"killpg",lambda pid,sig:killed.append((pid,sig)))
    with pytest.raises(r.Denied,match="EXACT_SIX_HOUR"):
        r.run_full()
    assert spawned and spawned[0][1]["start_new_session"] is True
    assert killed and killed[0][0]==44332
    assert killed[0][1]==__import__("signal").SIGTERM

def test_worker_cleanup_precedes_native_breaker_revalidation(monkeypatch,tmp_path):
    record=tmp_path/"private";record.mkdir()
    monkeypatch.setattr(r,"RECORD",record)
    monkeypatch.setattr(r,"assert_worker_environment",lambda:None)
    monkeypatch.setattr(r,"current_attempt",lambda:{
       "candidate_sha":"a"*40,"scope_sha256":"s","approved_at":"2026-11-22T00:00:00+00:00",
       "scope":{"live_source_identity":{"inode":1,"device":2}}})
    monkeypatch.setattr(r,"installed_baseline",lambda:None)
    monkeypatch.setattr(r,"health_gate",lambda **kwargs:None)
    monkeypatch.setattr(r,"dataset",lambda:{"inode":1,"device":2})
    monkeypatch.setattr(r,"run_full",lambda:0)
    monkeypatch.setattr(r,"verify_full_after",lambda *_:True)
    monkeypatch.setattr(r,"root_read",lambda *_:b"reviewed")
    monkeypatch.setattr(r,"root_write",lambda p,d,mode=0o400:p.write_bytes(d))
    order=[]
    monkeypatch.setattr(r,"rollback_override",lambda *_:order.append("override-removed"))
    monkeypatch.setattr(r,"after_full_native_revalidation",lambda *_:(order.append("native-verified") or ["a","b","c"]))
    r.worker()
    assert order==["override-removed","native-verified"]
    assert json.loads((record/"result.json").read_text())["temporary_override_removed"] is True

def test_incomplete_or_failed_full_service_cannot_revalidate_even_if_root_claimed(monkeypatch):
    acted=[]
    monkeypatch.setattr(r,"verify_full_after",lambda *_:(_ for _ in ()).throw(r.Denied("INTEGRITY_MISSING")))
    monkeypatch.setattr(r,"system",lambda *a,**k:acted.append(a))
    with pytest.raises(r.Denied,match="INTEGRITY_MISSING"):
        r.after_full_native_revalidation("2026-11-22T05:00:00+00:00")
    assert acted==[]
