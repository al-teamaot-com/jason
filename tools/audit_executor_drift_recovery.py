#!/usr/bin/env python3
"""Safely retire exactly two newly installed audit units and revalidate LKG.

Emergency inverse of previously approved audit-only 2026-11-22 Root bootstrap.
NO generic production release, freeze exception, database change, restart of
long-lived service, new authority or modification of Root desired-state policy.
Root execution must be explicit and use the source-pinned private copy.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys
from uuid import uuid4

BASE = Path("/etc/systemd/system")
ARTIFACT_ROOT = Path("/var/lib/jason-owner-release")
RECORD = ARTIFACT_ROOT / "audit-journal-executor-safe-retire-20261122"
CONTROL = Path("/var/lib/jason/openclaw/release-manager/production-control-state.json")
DRIFT = Path("/var/lib/jason/openclaw/release-manager/production-drift.json")
TRANSITIONS = Path("/var/lib/jason/openclaw/release-manager/protected-transitions")
EXECUTOR = Path("/usr/local/lib/jason/audit-journal-owner-executor/worker.py")
POLICY = Path("/etc/jason-owner-release/audit-journal-owner-executor-v1.json")
PUBLIC = Path("/var/lib/jason/authority/audit-journal-release")
AUDIT_INSTALLED = Path("/var/lib/jason-audit-journal")
REV = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
CANDIDATE = "d189663e441a1def14cb7494762e74e0b9d9f0e0"
UNIT_SHA = {
    "jason-audit-journal-owner-executor.service":
        "d0e7d9bda2374fc9ac3a8894ce3956b02260d409afd5306d8f3486be2de7e95c",
    "jason-audit-journal-owner-executor.path":
        "9f490ed478b882f0582437d4cc60c6961695aa93da726647c7046cf100361059",
}
EXECUTOR_SHA = "c916398d16a1a12270c5f0273f01dda576b3ac6ffbd25e906094135f84b59813"
POLICY_SHA = None  # Root-only content verified by exact candidate/worker scope.
WATCH = "jason-audit-journal-owner-executor.path"
SERVICE = "jason-audit-journal-owner-executor.service"
WATCHDOG = "jason-production-drift-watchdog.service"
TRANSITION = "jason-release-control-transition.service"
READBACK = "jason-release-control-readback.service"

class Refused(PermissionError):
    pass

def require(ok: bool, reason: str) -> None:
    if not ok:
        raise Refused("AUDIT_OWNER_BOOTSTRAP_SAFE_ROLLBACK_" + reason)

def command(*args: str, timeout: int=90) -> str:
    result = subprocess.run(args,capture_output=True,text=True,check=False,timeout=timeout,cwd="/")
    require(result.returncode == 0, "COMMAND_FAILED_" + args[1].replace("-", "_")[:55])
    return result.stdout.strip()

def digest(raw: bytes) -> str:
    return sha256(raw).hexdigest()

def jsonbytes(value: dict) -> bytes:
    return (json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()

def safe_read(path: Path,uid: int,mode: int,max_bytes: int=150_000) -> bytes:
    info=path.lstat()
    require(not path.is_symlink() and stat.S_ISREG(info.st_mode)
            and info.st_uid==uid and stat.S_IMODE(info.st_mode)==mode
            and info.st_nlink==1 and 0<info.st_size<=max_bytes,
            "FILE_CUSTODY_"+path.name)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        observed=os.fstat(fd)
        require((info.st_dev,info.st_ino,info.st_size)==
                (observed.st_dev,observed.st_ino,observed.st_size),
                "FILE_CHANGED_"+path.name)
        raw=os.read(fd,max_bytes+1)
        require(len(raw)==info.st_size,"FILE_SHORT_READ_"+path.name)
        return raw
    finally:
        os.close(fd)

def root_doc(path: Path) -> dict:
    row=json.loads(safe_read(path,0,0o600,2_000_000))
    require(isinstance(row,dict),"ROOT_OBJECT_REQUIRED_"+path.name)
    return row

def source_custody(*, resume: bool=False) -> None:
    require(os.geteuid()==0 and sys.flags.isolated==1,
            "ISOLATED_ROOT_REQUIRED")
    current=Path(__file__)
    meta=current.lstat()
    require(current.is_absolute() and str(current).startswith("/run/jason-")
            and not current.is_symlink() and meta.st_uid==0
            and stat.S_IMODE(meta.st_mode)==0o400 and meta.st_nlink==1,
            "ROOT_PRIVATE_PINNED_SCRIPT_REQUIRED")
    parent=ARTIFACT_ROOT.lstat()
    require(not ARTIFACT_ROOT.is_symlink() and stat.S_ISDIR(parent.st_mode)
            and parent.st_uid==0 and stat.S_IMODE(parent.st_mode)==0o700,
            "ROOT_EVIDENCE_PARENT_NOT_TRUSTED")
    if not resume:
        require(not os.path.lexists(RECORD),"RETIRED_RECEIPT_ALREADY_PRESENT")

def audit_spool_empty() -> None:
    for kind in ("requests","results","processed","offers","owner-approvals"):
        p=PUBLIC/kind
        m=p.lstat()
        require(not p.is_symlink() and stat.S_ISDIR(m.st_mode)
                and m.st_uid==1000 and stat.S_IMODE(m.st_mode)==0o700,
                "PUBLIC_SPOOL_UNTRUSTED_"+kind)
        require(not any(p.iterdir()),"AUDIT_REQUEST_OR_OWNER_OFFER_ALREADY_PUBLISHED")
    stage=ARTIFACT_ROOT/"audit-journal-signed-stage"
    if stage.exists():
        m=stage.lstat()
        require(not stage.is_symlink() and stat.S_ISDIR(m.st_mode)
                and m.st_uid==0 and stat.S_IMODE(m.st_mode)==0o700,
                "ROOT_STAGE_UNTRUSTED")
        require(not any(stage.iterdir()),"ROOT_OWNER_STAGE_ALREADY_PUBLISHED")
    require(not AUDIT_INSTALLED.exists(),"ARCHIVE_TRANSACTION_ALREADY_STARTED")

def preflight() -> dict:
    source_custody()
    require(digest(safe_read(EXECUTOR,0,0o444))==EXECUTOR_SHA,
            "INSTALLED_ROOT_EXECUTOR_UNEXPECTED")
    policy=root_doc(POLICY)
    require(policy.get("action")=="ADOPT-EXACT-DAILY-AUDIT-JOURNAL"
            and policy.get("candidate_sha")==CANDIDATE
            and policy.get("rollback_sha")==REV
            and policy.get("worker_sha256")==EXECUTOR_SHA
            and policy.get("global_freeze_unchanged") is True
            and policy.get("one_use_executor") is True
            and policy.get("standing_authority") is False,
            "OWNER_BOOTSTRAP_POLICY_SCOPE_MISMATCH")
    proof={}
    for name,expected in UNIT_SHA.items():
        path=BASE/name
        raw=safe_read(path,0,0o644,50_000)
        require(digest(raw)==expected,"ROOT_INSTALLED_UNIT_SOURCE_DRIFT_"+name)
        proof[name]=raw
    require(subprocess.run(["/usr/bin/systemctl","is-active","--quiet",WATCH],
                           capture_output=True,timeout=10).returncode==0,
            "EXACT_WATCHER_NOT_ACTIVE")
    require(subprocess.run(["/usr/bin/systemctl","is-active","--quiet",SERVICE],
                           capture_output=True,timeout=10).returncode!=0,
            "AUDIT_ROOT_EXECUTOR_ALREADY_RUNNING")
    audit_spool_empty()
    drift=root_doc(DRIFT)
    actual={(row.get("kind"),row.get("unit")) for row in drift.get("problems",[])
            if isinstance(row,dict)}
    expected={("undeclared_installed_system_unit",name) for name in UNIT_SHA}
    require(drift.get("status")=="drift_detected" and actual==expected
            and len(drift.get("problems",[]))==2,
            "DRIFT_NOT_EXACT_AUDIT_UNIT_ONLY")
    control=root_doc(CONTROL)
    breaker=control.get("circuit_breaker") or {}
    require(breaker.get("state")=="open"
            and breaker.get("reason")=="continuous_production_drift_detected"
            and breaker.get("source")=="production_drift_watchdog",
            "BREAK_NOT_ONLY_EXPECTED_DRIFT")
    lkg=(control.get("last_known_good") or {}).get("manifest") or {}
    require(lkg.get("complete") is True and lkg.get("revision")==REV,
            "IMMUTABLE_LKG_MISMATCH")
    require(not os.path.lexists(RECORD),"ONE_TIME_RETIRE_RECORD_ALREADY_EXISTS")
    return {"files":proof,"candidate":CANDIDATE,
            "previous_breaker":"open","lkg":REV,
            "observed_at":datetime.now(timezone.utc).isoformat()}

def exclusive(path: Path,raw: bytes,mode: int,uid: int=0) -> None:
    require(not os.path.lexists(path),"EXACT_OUTPUT_ALREADY_EXISTS_"+path.name)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    try:
        with os.fdopen(fd,"wb",closefd=False) as stream:
            os.fchmod(fd,mode)
            os.fchown(fd,uid,uid)
            stream.write(raw)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)

def prepare_retire_receipt(pre: dict) -> None:
    os.mkdir(RECORD,mode=0o700)
    os.chown(RECORD,0,0)
    os.chmod(RECORD,0o700)
    for name,raw in pre["files"].items():
        exclusive(RECORD/name,raw,0o400)
    exclusive(RECORD/"intent.json",jsonbytes({
        "schema_version":"1.0",
        "action":"rollback_only_the_two_unlisted_temporary_audit_executor_units",
        "candidate_sha":CANDIDATE,
        "verified_root_source_sha256":UNIT_SHA,
        "original_global_freeze_unchanged":True,
        "existing_worker_and_root_policy_retained":True,
        "intent_recorded_at":datetime.now(timezone.utc).isoformat(),
    }),0o400)
    folder=os.open(RECORD,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(folder)
    finally:os.close(folder)

def launch_native_revalidate() -> dict:
    reqfolder=TRANSITIONS/"requests"
    resfolder=TRANSITIONS/"results"
    for path in (reqfolder,resfolder):
        meta=path.lstat()
        require(not path.is_symlink() and stat.S_ISDIR(meta.st_mode)
                and meta.st_uid==1000 and stat.S_IMODE(meta.st_mode)==0o700,
                "ORIGINAL_ROOT_TRANSITION_SPOOL_UNTRUSTED")
    rid=uuid4().hex
    # The original Root worker independently proves the immutable LKG and
    # regenerates real Root drift; this request is intent, not clearance.
    intent={"request_id":rid,"action":"revalidate","revision":REV,
            "release_id":"","reason":"exact_bootstrap_unit_safe_retirement"}
    exclusive(reqfolder/(rid+".json"),jsonbytes(intent),0o600,1000)
    command("/usr/bin/systemctl","start",TRANSITION,timeout=100)
    reply=json.loads(safe_read(resfolder/(rid+".json"),1000,0o600,20000))
    require(reply.get("request_id")==rid
            and reply.get("action")=="revalidate"
            and reply.get("revision")==REV and reply.get("success") is True,
            "ROOT_INDEPENDENT_REVALIDATION_DENIED")
    # Keep immutable Root-only audit evidence before removing transient reply.
    exclusive(RECORD/"root-revalidation.json",jsonbytes({
        "schema_version":"1.0","request_id":rid,
        "action":"revalidate","revision":REV,"success":True,
        "verified_at":datetime.now(timezone.utc).isoformat(),
    }),0o400)
    os.unlink(resfolder/(rid+".json"))
    command("/usr/bin/systemctl","start",READBACK,timeout=100)
    return reply

def resume_preflight() -> dict:
    source_custody(resume=True)
    meta=RECORD.lstat()
    require(not RECORD.is_symlink() and stat.S_ISDIR(meta.st_mode)
            and meta.st_uid==0 and stat.S_IMODE(meta.st_mode)==0o700,
            "ROOT_RETIRE_RECEIPT_CUSTODY")
    intent=json.loads(safe_read(RECORD/"intent.json",0,0o400,10000))
    require(intent.get("schema_version")=="1.0" and
            intent.get("candidate_sha")==CANDIDATE and
            intent.get("verified_root_source_sha256")==UNIT_SHA and
            intent.get("original_global_freeze_unchanged") is True,
            "EXACT_EARLIER_RETIRE_INTENT_NOT_TRUSTED")
    files={}
    for name,expected in UNIT_SHA.items():
        raw=safe_read(RECORD/name,0,0o400,50000)
        require(digest(raw)==expected,"ORIGINAL_UNIT_BACKUP_CHANGED_"+name)
        if os.path.lexists(BASE/name):
            require(safe_read(BASE/name,0,0o644,50000)==raw,
                    "LIVE_TEMPORARY_UNIT_CHANGED_"+name)
        files[name]=raw
    require(digest(safe_read(EXECUTOR,0,0o444))==EXECUTOR_SHA,
            "ROOT_EXECUTOR_CHANGED_DURING_ROLLBACK")
    policy=root_doc(POLICY)
    require(policy.get("candidate_sha")==CANDIDATE
            and policy.get("worker_sha256")==EXECUTOR_SHA
            and policy.get("rollback_sha")==REV,
            "RETAINED_ROOT_POLICY_CHANGED")
    audit_spool_empty()
    control=root_doc(CONTROL)
    breaker=control.get("circuit_breaker") or {}
    require(breaker.get("state")=="open" or (
                breaker.get("state")=="closed"
                and breaker.get("reason")=="root_verified_revalidate"
                and breaker.get("revalidated_revision")==REV),
            "UNEXPECTED_PROTECTED_BREAKER_STATE")
    drift=root_doc(DRIFT)
    problems=drift.get("problems") or []
    permitted={("undeclared_installed_system_unit",name) for name in UNIT_SHA}
    require(all(isinstance(item,dict) and
                (item.get("kind"),item.get("unit")) in permitted
                for item in problems),
            "DIFFERENT_DRIFT_INCIDENT_DETECTED")
    return {"files":files,"candidate":CANDIDATE,"lkg":REV,
            "resuming":True,"previous_breaker":breaker["state"]}


def revalidate_retired_units(pre: dict) -> None:
    # Disable exactly this watcher if it remains enabled after interruption.
    if os.path.lexists(BASE/WATCH):
        command("/usr/bin/systemctl","disable","--now",WATCH,timeout=35)
    for unit in (WATCH,SERVICE):
        code=subprocess.run(["/usr/bin/systemctl","is-active","--quiet",unit],
                            capture_output=True,check=False,timeout=15)
        require(code.returncode!=0,"TEMPORARY_AUDIT_UNIT_STILL_RUNNING_"+unit)
    # A request must not arrive between the first inspection and stopping
    # the watcher; never silently discard an exact Owner stage or job.
    audit_spool_empty()
    for name,raw in pre["files"].items():
        path=BASE/name
        if os.path.lexists(path):
            require(safe_read(path,0,0o644,50_000)==raw,
                    "UNIT_CHANGED_DURING_RETIRE_"+name)
            os.unlink(path)
    command("/usr/bin/systemctl","daemon-reload",timeout=35)
    # A static unit can no longer be loaded after removal, so reset-failed
    # would itself fail with "unit not found" and strand an otherwise clean
    # recovery. The independent Root watchdog is the acceptance criterion.
    # The watchdog deliberately leaves the breaker open on PASS.
    command("/usr/bin/systemctl","start",WATCHDOG,timeout=100)
    drift=root_doc(DRIFT)
    require(drift.get("status")=="pass" and drift.get("problems")==[],
            "ROOT_WATCHDOG_NOT_CLEAN_AFTER_RETIRE")
    control=root_doc(CONTROL)
    breaker=control.get("circuit_breaker") or {}
    if (breaker.get("state")!="closed" or
            breaker.get("reason")!="root_verified_revalidate" or
            breaker.get("revalidated_revision")!=REV):
        reply=launch_native_revalidate()
        rid=reply["request_id"]
    else:
        rid="already_root_verified"
    control=root_doc(CONTROL)
    breaker=control.get("circuit_breaker") or {}
    require(breaker.get("state")=="closed"
            and breaker.get("reason")=="root_verified_revalidate"
            and breaker.get("revalidated_revision")==REV,
            "NATIVE_ROOT_VERIFICATION_NOT_CLOSED")
    require(not any((BASE/name).exists() for name in UNIT_SHA),
            "UNDECLARED_AUDIT_UNIT_STILL_INSTALLED")
    require(digest(safe_read(EXECUTOR,0,0o444))==EXECUTOR_SHA,
            "RETAINED_ROOT_EXECUTOR_CHANGED")
    require(root_doc(POLICY).get("candidate_sha")==CANDIDATE,
            "ROOT_POLICY_CHANGED_DURING_REVALIDATION")
    proof={
        "schema_version":"1.0",
        "status":"closed_verified_native_lkg_after_narrow_audit_unit_retirement",
        "revision":REV,"candidate":CANDIDATE,
        "root_revalidation_request_id":rid,
        "global_freeze_changed":False,"audit_source_deleted":False,
        "production_database_changed":False,
        "installed_root_worker_retained":True,
        "audit_daily_archive_deployed":False,
        "verified_at":datetime.now(timezone.utc).isoformat(),
    }
    existing=RECORD/"result.json"
    if existing.exists():
        old=json.loads(safe_read(existing,0,0o400,12000))
        require(old.get("status")==proof["status"] and
                old.get("revision")==REV and
                old.get("candidate")==CANDIDATE,
                "UNEXPECTED_PRIOR_RETIRE_RESULT")
    else:
        exclusive(existing,jsonbytes(proof),0o400)
    print("AUDIT_EXECUTOR_TEMP_UNIT_ROLLBACK=VERIFIED",flush=True)
    print("NATIVE_ROOT_BREAKER=CLOSED",flush=True)
    print("ORIGINAL_DATABASE_UNCHANGED=true",flush=True)
    print("OWNER_ROOT_EXECUTOR_RETAINED=true",flush=True)
    print("ARCHIVE_NOT_YET_DEPLOYED=true",flush=True)


def apply(pre: dict) -> None:
    if not pre.get("resuming"):
        prepare_retire_receipt(pre)
    revalidate_retired_units(pre)

def main() -> None:
    parser=argparse.ArgumentParser()
    g=parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--preflight-only",action="store_true")
    g.add_argument("--apply",action="store_true")
    g.add_argument("--resume",action="store_true")
    args=parser.parse_args()
    evidence=resume_preflight() if args.resume else preflight()
    print("EXACT_TWO_TEMPORARY_AUDIT_UNITS_ONLY=VERIFIED",flush=True)
    print("LKG="+evidence["lkg"],flush=True)
    print("ROOT_NATIVE_BREAKER_CURRENTLY="+evidence["previous_breaker"].upper(),flush=True)
    if args.preflight_only:
        print("PRODUCTION_MUTATIONS=NONE",flush=True)
        return
    apply(evidence)

if __name__=="__main__":
    try:main()
    except Exception as exc:
        code=(str(exc).split(":")[0] if isinstance(exc,Refused)
              else type(exc).__name__)
        print("AUDIT_BOOTSTRAP_SAFE_RETIRE=DENIED:"+code,file=sys.stderr)
        raise SystemExit(2)
