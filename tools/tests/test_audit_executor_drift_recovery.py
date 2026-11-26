"""Exact safety rollback for two undeclared temporary Root audit watcher units.

Unit tests are on disposable synthetic paths only; never touch live systemd.
"""
from __future__ import annotations
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess

import pytest

from tools import audit_executor_drift_recovery as retired


def fixture(tmp_path,monkeypatch):
    source_root=Path(__file__).resolve().parents[2]
    base=tmp_path/"etc-systemd"
    base.mkdir()
    evidence=tmp_path/"root-owned"
    evidence.mkdir()
    spool=tmp_path/"protected-transitions"
    for d in (spool/"requests",spool/"results"):
        d.mkdir(parents=True,exist_ok=True)
    auditpub=tmp_path/"audit-requests"
    auditpub.mkdir()
    executor=tmp_path/"trusted-executor.py"
    executor.write_bytes((source_root/"tools/audit_journal_owner_native_worker.py").read_bytes())
    policy=tmp_path/"root-audit-policy.json"
    policy.write_text(json.dumps({
        "action":"ADOPT-EXACT-DAILY-AUDIT-JOURNAL",
        "candidate_sha":retired.CANDIDATE,
        "rollback_sha":retired.REV,
        "worker_sha256":retired.EXECUTOR_SHA,
        "global_freeze_unchanged":True,
        "one_use_executor":True,
        "standing_authority":False,
    }))
    control=tmp_path/"production-control-state.json"
    drift=tmp_path/"production-drift.json"
    state={"watcher":True,"native_runs":0,"watchdog_runs":0,
           "fail_command":None,"others_modified":False}
    for name,hashvalue in retired.UNIT_SHA.items():
        data=(source_root/"infrastructure/jason-audit-journal-owner-executor"/name).read_bytes()
        assert retired.digest(data)==hashvalue
        (base/name).write_bytes(data)
    control.write_text(json.dumps({
      "schema_version":"1.0",
      "circuit_breaker":{
         "state":"open","source":"production_drift_watchdog",
         "reason":"continuous_production_drift_detected"},
      "last_known_good":{
         "manifest":{"complete":True,"revision":retired.REV}}
    }))
    drift.write_text(json.dumps({
      "status":"drift_detected",
      "problems":[{
         "kind":"undeclared_installed_system_unit","unit":n,"state":"active"
       } for n in retired.UNIT_SHA]
    }))
    survivor=base/"jason-unrelated-important.service"
    survivor.write_bytes(b"must-survive\n")
    monkeypatch.setattr(retired,"BASE",base)
    monkeypatch.setattr(retired,"ARTIFACT_ROOT",evidence)
    monkeypatch.setattr(retired,"RECORD",evidence/"safe-retire")
    monkeypatch.setattr(retired,"TRANSITIONS",spool)
    monkeypatch.setattr(retired,"PUBLIC",auditpub)
    monkeypatch.setattr(retired,"AUDIT_INSTALLED",tmp_path/"not-installed")
    monkeypatch.setattr(retired,"EXECUTOR",executor)
    monkeypatch.setattr(retired,"POLICY",policy)
    monkeypatch.setattr(retired,"CONTROL",control)
    monkeypatch.setattr(retired,"DRIFT",drift)
    # The strict Root-owned inode/mode checks run separately in UID0
    # no-network/no-host-mount integration fixtures. Unit tests exercise the
    # real authorized drift state transitions and exact filename/hash checks.
    monkeypatch.setattr(retired,"source_custody",
                        lambda **kwargs: (
                          retired.require(not retired.RECORD.exists(),
                              "RETIRED_RECEIPT_ALREADY_PRESENT")
                          if not kwargs.get("resume") else None
                        ))
    monkeypatch.setattr(retired,"safe_read",
                        lambda path,uid,mode,max_bytes=150000:Path(path).read_bytes())
    # Standalone unit tests execute as UID1000 on GitHub. Actual isolated
    # UID0 integration tests exercise Root chown/custody without these mocks.
    monkeypatch.setattr(retired.os,"chown",lambda *args,**kw:None)
    monkeypatch.setattr(retired.os,"fchown",lambda *args,**kw:None)
    original_lstat=Path.lstat
    def virtual_root_receipt(path,*args,**kw):
        st=original_lstat(path,*args,**kw)
        if Path(path)==retired.RECORD:
            return SimpleNamespace(st_mode=st.st_mode,st_uid=0,
                                   st_nlink=st.st_nlink,st_size=st.st_size)
        return st
    monkeypatch.setattr(Path,"lstat",virtual_root_receipt)
    monkeypatch.setattr(retired,"audit_spool_empty",
                        lambda:retired.require(
                            not retired.AUDIT_INSTALLED.exists(),
                            "ARCHIVE_TRANSACTION_ALREADY_STARTED"))
    real_run=subprocess.run
    def running(cmd,**kwargs):
        if len(cmd)>=4 and cmd[:3]==["/usr/bin/systemctl","is-active","--quiet"]:
            return SimpleNamespace(
                returncode=0 if cmd[3]==retired.WATCH and state["watcher"] else 3)
        return real_run(cmd,**kwargs)
    monkeypatch.setattr(retired.subprocess,"run",running)
    def command(*args,timeout=90):
        key=" ".join(args[1:])
        if state["fail_command"] and state["fail_command"] in key:
            raise RuntimeError("simulated exact systemd failure")
        if args[1:3]==("disable","--now"):
            assert args[3]==retired.WATCH
            state["watcher"]=False
        if args[1:3]==("start",retired.WATCHDOG):
            state["watchdog_runs"]+=1
            drift.write_text(json.dumps({"status":"pass","problems":[]}))
        return ""
    monkeypatch.setattr(retired,"command",command)
    def native():
        state["native_runs"]+=1
        obj=json.loads(control.read_text())
        obj["circuit_breaker"]={
            "state":"closed","reason":"root_verified_revalidate",
            "revalidated_revision":retired.REV,
        }
        control.write_text(json.dumps(obj))
        return {"request_id":"a"*32,"success":True,
                "action":"revalidate","revision":retired.REV}
    monkeypatch.setattr(retired,"launch_native_revalidate",native)
    return base,evidence,state,control,drift,survivor


def test_preflight_is_non_mutating_and_only_expected_unit_files(tmp_path,monkeypatch):
    base,evidence,state,control,drift,survivor=fixture(tmp_path,monkeypatch)
    before={p.name:p.read_bytes() for p in base.iterdir()}
    summary=retired.preflight()
    assert summary["candidate"]==retired.CANDIDATE
    assert set(summary["files"])==set(retired.UNIT_SHA)
    assert {p.name:p.read_bytes() for p in base.iterdir()}==before
    assert not retired.RECORD.exists()
    assert json.loads(control.read_text())["circuit_breaker"]["state"]=="open"


def test_exact_two_unit_rollback_then_native_root_verified_close(tmp_path,monkeypatch):
    base,evidence,state,control,drift,survivor=fixture(tmp_path,monkeypatch)
    original=survivor.read_bytes()
    retired.apply(retired.preflight())
    assert all(not (base/name).exists() for name in retired.UNIT_SHA)
    assert survivor.read_bytes()==original
    assert retired.EXECUTOR.exists() and retired.POLICY.exists()
    assert state["native_runs"]==1 and state["watchdog_runs"]==1
    assert json.loads(drift.read_text())["status"]=="pass"
    assert json.loads(control.read_text())["circuit_breaker"]=={
        "state":"closed","reason":"root_verified_revalidate",
        "revalidated_revision":retired.REV}
    assert (retired.RECORD/"result.json").exists()
    assert all((retired.RECORD/name).read_bytes() for name in retired.UNIT_SHA)


def test_any_extra_drift_blocks_exact_retire(tmp_path,monkeypatch):
    base,evidence,state,control,drift,survivor=fixture(tmp_path,monkeypatch)
    record=json.loads(drift.read_text())
    record["problems"].append({
        "kind":"undeclared_installed_system_unit",
        "unit":"jason-important.service","state":"active"
    })
    drift.write_text(json.dumps(record))
    with pytest.raises(retired.Refused,match="DRIFT_NOT_EXACT_AUDIT_UNIT_ONLY"):
        retired.preflight()
    assert (base/retired.WATCH).exists() and not retired.RECORD.exists()


def test_tampered_new_unit_blocks_retire(tmp_path,monkeypatch):
    base,evidence,state,control,drift,survivor=fixture(tmp_path,monkeypatch)
    (base/retired.SERVICE).write_bytes(b"malicious modified service\n")
    with pytest.raises(retired.Refused,match="ROOT_INSTALLED_UNIT_SOURCE_DRIFT"):
        retired.preflight()


def test_wrong_production_breaker_blocks_retire(tmp_path,monkeypatch):
    base,evidence,state,control,drift,survivor=fixture(tmp_path,monkeypatch)
    obj=json.loads(control.read_text())
    obj["circuit_breaker"]["reason"]="unrelated_security_event"
    control.write_text(json.dumps(obj))
    with pytest.raises(retired.Refused,match="BREAK_NOT_ONLY_EXPECTED_DRIFT"):
        retired.preflight()


def test_record_already_exists_cannot_start_new_retire(tmp_path,monkeypatch):
    base,evidence,state,control,drift,survivor=fixture(tmp_path,monkeypatch)
    retired.RECORD.mkdir()
    with pytest.raises(retired.Refused,match="RETIRED_RECEIPT_ALREADY_PRESENT"):
        retired.preflight()


def test_interrupt_during_watchdog_can_resume_safely(tmp_path,monkeypatch):
    base,evidence,state,control,drift,survivor=fixture(tmp_path,monkeypatch)
    state["fail_command"]="start "+retired.WATCHDOG
    with pytest.raises(RuntimeError,match="simulated exact systemd"):
        retired.apply(retired.preflight())
    assert not (base/retired.WATCH).exists()
    assert not (base/retired.SERVICE).exists()
    assert retired.RECORD.exists()
    assert state["native_runs"]==0
    assert survivor.read_bytes()==b"must-survive\n"
    state["fail_command"]=None
    resumed=retired.resume_preflight()
    assert resumed["resuming"] is True
    retired.apply(resumed)
    assert json.loads(control.read_text())["circuit_breaker"]["state"]=="closed"
    assert state["native_runs"]==1
    assert (retired.RECORD/"result.json").exists()


def test_interrupt_before_disable_resumes_only_exact_watcher(tmp_path,monkeypatch):
    base,evidence,state,control,drift,survivor=fixture(tmp_path,monkeypatch)
    state["fail_command"]="disable --now"
    with pytest.raises(RuntimeError):
        retired.apply(retired.preflight())
    assert (base/retired.WATCH).exists() and retired.RECORD.exists()
    state["fail_command"]=None
    retired.apply(retired.resume_preflight())
    assert state["watcher"] is False
    assert not (base/retired.WATCH).exists()
    assert state["native_runs"]==1


def test_interrupt_after_root_revalidate_resumes_without_double_revalidation(
        tmp_path,monkeypatch):
    base,evidence,state,control,drift,survivor=fixture(tmp_path,monkeypatch)
    retired.apply(retired.preflight())
    assert state["native_runs"]==1
    retired.apply(retired.resume_preflight())
    assert state["native_runs"]==1
    assert (retired.RECORD/"result.json").exists()


def test_changed_backup_denies_retry(tmp_path,monkeypatch):
    base,evidence,state,control,drift,survivor=fixture(tmp_path,monkeypatch)
    state["fail_command"]="disable --now"
    with pytest.raises(RuntimeError):
        retired.apply(retired.preflight())
    saved=retired.RECORD/retired.SERVICE
    saved.chmod(0o600)
    saved.write_bytes(b"changed backup")
    saved.chmod(0o400)
    with pytest.raises(retired.Refused,match="ORIGINAL_UNIT_BACKUP_CHANGED"):
        retired.resume_preflight()


def test_unrelated_external_drift_denies_resume(tmp_path,monkeypatch):
    base,evidence,state,control,drift,survivor=fixture(tmp_path,monkeypatch)
    state["fail_command"]="start "+retired.WATCHDOG
    with pytest.raises(RuntimeError):
        retired.apply(retired.preflight())
    drift.write_text(json.dumps({
       "status":"drift_detected",
       "problems":[{"kind":"failed_system_unit","unit":"jason-critical.service"}]
    }))
    with pytest.raises(retired.Refused,match="DIFFERENT_DRIFT_INCIDENT_DETECTED"):
        retired.resume_preflight()


def test_source_has_no_generic_root_shell_or_forced_breaker_clear():
    source=Path(retired.__file__).read_text()
    for forbidden in ("shell=True","os.system(","set_last_known_good",
                      "production-control-state.json').write",
                      "os.environ['SUDO_"):
        assert forbidden not in source
    assert '"revalidate"' in source
    assert 'root_verified_revalidate' in source
