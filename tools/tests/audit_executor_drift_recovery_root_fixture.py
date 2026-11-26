"""Isolated UID0 exact watcher-retirement + Root LKG revalidation acceptance.

Runs under Python -I -B in a Linux container with no network, Docker socket,
host bind mount, service bus, or Root access to the user's live server.
"""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile

assert os.geteuid()==0
assert sys.flags.isolated==1
assert not Path("/var/run/docker.sock").exists()
assert not Path("/var/lib/jason/authority").exists()

with tempfile.TemporaryDirectory(prefix="exact-audit-temporary-root-recovery-",dir="/tmp") as tmp:
    base=Path(tmp)
    base.chmod(0o755)
    private_script=Path("/run/jason-audit-retire-fixture.py")
    assert not private_script.exists()
    private_script.write_bytes(Path("/test-source/audit_executor_drift_recovery.py").read_bytes())
    private_script.chmod(0o400)
    spec=importlib.util.spec_from_file_location("native_exact_audit_retirement",str(private_script))
    r=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(r)

    root_dir=base/"systemd"
    root_dir.mkdir(mode=0o755)
    root_policy_dir=base/"root-policy"
    root_policy_dir.mkdir(mode=0o755)
    root_owner=base/"root-owner"
    root_owner.mkdir(mode=0o700)
    root_owner.chmod(0o700)
    control_root=base/"control"
    control_root.mkdir(mode=0o700)
    public=base/"public-audit"
    public.mkdir(mode=0o700)
    os.chown(public,1000,1000)
    public.chmod(0o700)
    for sub in ("requests","results","processed","offers","owner-approvals"):
        p=public/sub
        p.mkdir(mode=0o700)
        os.chown(p,1000,1000)
        p.chmod(0o700)
    stage=root_owner/"audit-journal-signed-stage"
    stage.mkdir(mode=0o700)
    original_control=control_root/"production-control-state.json"
    original_drift=control_root/"production-drift.json"
    worker=base/"trusted-worker.py"
    worker.write_bytes(Path("/test-source/audit_journal_owner_native_worker.py").read_bytes())
    worker.chmod(0o444)
    installed_policy=root_policy_dir/"audit-policy.json"
    installed_policy.write_text(json.dumps({
        "schema_version":"1.0",
        "action":"ADOPT-EXACT-DAILY-AUDIT-JOURNAL",
        "candidate_sha":r.CANDIDATE,
        "rollback_sha":r.REV,
        "worker_sha256":r.EXECUTOR_SHA,
        "global_freeze_unchanged":True,
        "one_use_executor":True,
        "standing_authority":False,
    }))
    installed_policy.chmod(0o600)
    original_control.write_text(json.dumps({
       "schema_version":"1.0",
       "last_known_good":{"manifest":{"revision":r.REV,"complete":True}},
       "circuit_breaker":{
           "state":"open","source":"production_drift_watchdog",
           "reason":"continuous_production_drift_detected"
       },
    }))
    original_control.chmod(0o600)
    original_drift.write_text(json.dumps({
       "schema_version":"1.0","status":"drift_detected",
       "problems":[
          {"kind":"undeclared_installed_system_unit","unit":n,
           "state":"active" if n.endswith(".path") else "inactive"}
          for n in r.UNIT_SHA
       ],
    }))
    original_drift.chmod(0o600)
    names=set(r.UNIT_SHA)
    for name in names:
        p=root_dir/name
        p.write_bytes((Path("/test-source")/name).read_bytes())
        p.chmod(0o644)
    unrelated=root_dir/"jason-real-production-health.service"
    unrelated.write_bytes(b"real service must not change")
    unrelated.chmod(0o644)
    original_unrelated=unrelated.read_bytes()
    reqdir=control_root/"protected-transitions"/"requests"
    resdir=control_root/"protected-transitions"/"results"
    reqdir.mkdir(parents=True)
    resdir.mkdir()
    for p in (reqdir,resdir):
        os.chown(p,1000,1000)
        p.chmod(0o700)
    frozen=base/"original-production-freeze"
    frozen.write_bytes(b"unchanged immutable freeze")
    frozen.chmod(0o600)
    frozen_sha=r.digest(frozen.read_bytes())

    r.BASE=root_dir
    r.ARTIFACT_ROOT=root_owner
    r.RECORD=root_owner/"audit-journal-executor-safe-retire-20261122"
    r.CONTROL=original_control
    r.DRIFT=original_drift
    r.TRANSITIONS=control_root/"protected-transitions"
    r.EXECUTOR=worker
    r.POLICY=installed_policy
    r.PUBLIC=public
    r.AUDIT_INSTALLED=base/"never-installed-archive"

    state={"watcher_running":True,"root_revalidate_seen":False,
           "drift_watchdog_runs":0,"original_unit_files_removed":False}
    original_run=r.subprocess.run
    def mock_subprocess(cmd,*args,**kwargs):
        if cmd[:3]==["/usr/bin/systemctl","is-active","--quiet"]:
            unit=cmd[3]
            active=unit==r.WATCH and state["watcher_running"]
            return subprocess.CompletedProcess(cmd,0 if active else 3)
        raise AssertionError("no unapproved host/systemd subprocess")
    r.subprocess.run=mock_subprocess

    def mock_command(*args,timeout=90):
        assert args[0]=="/usr/bin/systemctl"
        if args[1:3]==("disable","--now"):
            assert args[3]==r.WATCH
            state["watcher_running"]=False
            return ""
        if args[1]=="daemon-reload":
            state["original_unit_files_removed"]=all(not (root_dir/name).exists()
                                                    for name in r.UNIT_SHA)
            assert state["original_unit_files_removed"]
            return ""
        if args[1:3]==("start",r.WATCHDOG):
            assert state["original_unit_files_removed"]
            state["drift_watchdog_runs"]+=1
            original_drift.write_text(json.dumps({
               "schema_version":"1.0","status":"pass","problems":[]
            }))
            return ""
        if args[1:3]==("start",r.TRANSITION):
            assert state["drift_watchdog_runs"]==1
            requests=list(reqdir.glob("*.json"))
            assert len(requests)==1
            req=json.loads(requests[0].read_bytes())
            assert req["action"]=="revalidate"
            assert req["revision"]==r.REV
            assert req["release_id"]==""
            info=requests[0].lstat()
            assert info.st_uid==1000 and stat.S_IMODE(info.st_mode)==0o600
            reply={
               "request_id":req["request_id"],"success":True,
               "action":"revalidate","revision":r.REV,
            }
            result=resdir/requests[0].name
            result.write_text(json.dumps(reply))
            os.chown(result,1000,1000)
            result.chmod(0o600)
            requests[0].unlink()
            control=json.loads(original_control.read_text())
            control["circuit_breaker"]={
              "state":"closed","reason":"root_verified_revalidate",
              "revalidated_revision":r.REV,
            }
            original_control.write_text(json.dumps(control))
            state["root_revalidate_seen"]=True
            return ""
        if args[1:3]==("start",r.READBACK):
            assert state["root_revalidate_seen"]
            return ""
        raise AssertionError("unexpected Root command "+str(args))
    r.command=mock_command

    before=r.preflight()
    assert before["lkg"]==r.REV and before["previous_breaker"]=="open"
    assert state["watcher_running"]
    assert not r.RECORD.exists()
    r.apply(before)
    assert not state["watcher_running"]
    assert state["root_revalidate_seen"]
    assert state["drift_watchdog_runs"]==1
    assert not any((root_dir/name).exists() for name in r.UNIT_SHA)
    assert unrelated.read_bytes()==original_unrelated
    assert r.EXECUTOR.read_bytes()==Path("/test-source/audit_journal_owner_native_worker.py").read_bytes()
    assert r.POLICY.exists()
    assert not r.AUDIT_INSTALLED.exists()
    assert frozen_sha==r.digest(frozen.read_bytes())
    root_records=list(r.RECORD.iterdir())
    assert len(root_records)==5,root_records
    for path in root_records:
        info=path.lstat()
        assert info.st_uid==0
        assert stat.S_IMODE(info.st_mode)==0o400
    assert r.RECORD.lstat().st_uid==0
    assert stat.S_IMODE(r.RECORD.lstat().st_mode)==0o700
    assert json.loads(r.DRIFT.read_text())["status"]=="pass"
    control=json.loads(r.CONTROL.read_text())
    assert control["circuit_breaker"]["state"]=="closed"
    assert control["circuit_breaker"]["reason"]=="root_verified_revalidate"
    assert control["last_known_good"]["manifest"]["revision"]==r.REV
    # Re-running a fully accepted retirement is an audited NOOP, not a new
    # authorization or a second Root production transition.
    r.apply(r.resume_preflight())
    assert state["drift_watchdog_runs"]==2
    assert state["root_revalidate_seen"]
    assert unrelated.read_bytes()==original_unrelated

    print(json.dumps({
      "status":"PASS","isolated_root":True,
      "uid1000_transition_request_0600":True,
      "root_0400_backups_and_0700_receipt":True,
      "two_exact_unlisted_units_removed":True,
      "native_root_revalidation_verified":True,
      "original_lkg_preserved":True,
      "root_worker_and_policy_retained":True,
      "unrelated_systemd_units_untouched":True,
      "original_freeze_untouched":True,
      "audit_archive_database_untouched":True,
      "network":"disabled","host_mounts":False,
    },sort_keys=True))
