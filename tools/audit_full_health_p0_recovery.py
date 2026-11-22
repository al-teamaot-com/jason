#!/usr/bin/env python3
"""One exact Owner-authenticated, transient full SQLite proof recovery.

The existing obsolete V2 helper is never used. Root execution is locked to a
clean, reviewed protected-Main source and independently verified Owner action.
Only a real complete four-database integrity+restore PASS can restore native
health; the production breaker is never edited or manually cleared.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time

SOURCE_ROOT=Path(__file__).resolve().parents[1]
REPO=SOURCE_ROOT
ROOT_BASE=Path("/usr/local/lib/jason/audit-full-health-p0-20261122")
RECORD=Path("/var/lib/jason-owner-release/audit-full-health-p0-20261122")
ROOT_SCRIPT=ROOT_BASE/"recovery.py"
FULL=Path("/var/lib/jason/openclaw/operational-full-health.json")
FAST=Path("/var/lib/jason/openclaw/operational-health.json")
RELEASE=Path("/var/lib/jason/openclaw/release-manager")
LIVE=Path("/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3")
ARCHIVE=Path("/srv/jason/archive")
LKG="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
OWNER="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
ACTION="RECOVER-EXACT-AUDIT-FULL-SQLITE-PROOF-20261122"
CORE_SHA="64f451c03fe75b70c80462938d1199f35ce73b82f6b2ef4891e3c7d9c879e432"
EXPECTED_FULL_DROPIN="06bce21acc3ebbbfd4314c62c442f221c697daae02784d2d99753873677629da"
EXPECTED_FAST_DROPIN="12173fbb4207f1b435e2aebfac066d07e33198761ab4baeb359e647092d65bc3"
EXPECTED_FULL_WRAPPER="e3b709bab3d16a69e461af8741ea2ef41fad45030dd8a7349a10597fa5e680e8"
FREEZE_SHA="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
HOLD_SHA="11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0"
UNIT="jason-openclaw-authority-full-integrity.service"
DROPIN=Path("/etc/systemd/system/jason-openclaw-authority-full-integrity.service.d/93-audit-full-health-p0-recovery.conf")
CHILD_DEADLINE=21000
JOB_DEADLINE=21600
SOURCES={
 "tools/audit_full_health_p0_recovery.py":"recovery.py",
 "tools/audit_full_health_p0_snapshot.py":"openclaw_authority_live_audit_full_snapshot.py",
 "tools/audit_full_health_p0_operational.py":"openclaw_authority_operational_health.py",
 "tools/openclaw_authority_health_snapshot.py":"openclaw_authority_health_snapshot.py",
 "config/audit-full-health-p0-recovery.conf":"reviewed-override.conf",
}
SAFE=("GIT_CONFIG_NOSYSTEM=1","GIT_CONFIG_GLOBAL=/dev/null",
      "GIT_OPTIONAL_LOCKS=0","GIT_NO_REPLACE_OBJECTS=1",
      "GIT_GRAFT_FILE=/dev/null","GIT_CONFIG_COUNT=2",
      "GIT_CONFIG_KEY_0=core.fsmonitor","GIT_CONFIG_VALUE_0=false",
      "GIT_CONFIG_KEY_1=core.hooksPath","GIT_CONFIG_VALUE_1=/dev/null")
U=("/usr/sbin/runuser","-u","al","--","/usr/bin/env",*SAFE)
FULL_DROPIN=Path("/etc/systemd/system/jason-openclaw-authority-full-integrity.service.d/92-owner-live-audit-location.conf")
FAST_DROPIN=Path("/etc/systemd/system/jason-openclaw-authority-health.service.d/92-owner-live-audit-location.conf")
CURRENT_WRAPPER=Path("/usr/local/lib/jason/authority-health-live-audit/openclaw_authority_live_audit_full_snapshot.py")

class Denied(PermissionError):pass
def need(ok,why):
    if not ok:raise Denied("AUDIT_P0_"+why)
def canonical(value):return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def sha(raw):return sha256(raw).hexdigest()

def command(argv,*,timeout=60,check=True):
    p=subprocess.run(list(argv),cwd="/",capture_output=True,text=True,
                     timeout=timeout,check=False)
    if check:need(p.returncode==0,"COMMAND_FAILED:"+Path(argv[0]).name)
    return p

def git(*args):
    return command([*U,"/usr/bin/git","-C",str(REPO),*args],timeout=40).stdout.strip()

def exact_source(candidate,name):
    p=REPO/name
    m=p.lstat()
    need(not p.is_symlink() and stat.S_ISREG(m.st_mode)
         and m.st_uid==1000 and m.st_nlink==1 and not m.st_mode&0o022
         and 0<m.st_size<=2_000_000,"UNTRUSTED_SOURCE:"+name)
    raw=p.read_bytes()
    check=command([*U,"/usr/bin/git","-C",str(REPO),"show",candidate+":"+name],timeout=35)
    need(raw==check.stdout.encode(),"SOURCE_NOT_FROM_EXACT_MAIN:"+name)
    return raw

def root_read(p,max_bytes=1000000):
    m=p.lstat()
    need(not p.is_symlink() and stat.S_ISREG(m.st_mode)
         and (m.st_uid,m.st_gid)==(0,0) and not m.st_mode&0o022
         and m.st_nlink==1 and m.st_size<=max_bytes,"ROOT_BYTES_UNTRUSTED:"+p.name)
    raw=p.read_bytes()
    need(len(raw)==m.st_size,"ROOT_BYTES_CHANGED:"+p.name)
    return raw

def proof_file(p):
    m=p.lstat()
    need(not p.is_symlink() and stat.S_ISREG(m.st_mode) and m.st_uid==1000
         and stat.S_IMODE(m.st_mode)==0o600 and m.st_nlink==1
         and 0<m.st_size<200000,"HEALTH_EVIDENCE_UNTRUSTED:"+p.name)
    return json.loads(p.read_bytes())

def system_prop(unit,key):
    return command(["/usr/bin/systemctl","show",unit,"-p",key,"--value"],
                   timeout=12).stdout.strip()

def installed_baseline():
    for p,want in ((FULL_DROPIN,EXPECTED_FULL_DROPIN),
                   (FAST_DROPIN,EXPECTED_FAST_DROPIN),
                   (CURRENT_WRAPPER,EXPECTED_FULL_WRAPPER)):
        need(sha(root_read(p))==want,"CURRENT_INSTALLED_SOURCE_CHANGED:"+p.name)
    need(not Path("/etc/systemd/system/jason-openclaw-authority-health.service.d/"
                  "91-owner-emergency-full-proof-degraded.conf").exists(),
         "EXPIRED_EMERGENCY_OVERRIDE_REAPPEARED")
    need(Path("/opt/jason/current").resolve(strict=True).name==LKG,
         "PRODUCTION_BASELINE_CHANGED")
    need(sha((RELEASE/"production-deployment-freeze").read_bytes())==FREEZE_SHA,
         "PRODUCTION_FREEZE_CHANGED")
    need(sha((RELEASE/"auto-promotion-incident-hold").read_bytes())==HOLD_SHA,
         "PRODUCTION_HOLD_CHANGED")

def health_gate(*, full_unit_must_be_failed=True):
    control=json.loads(root_read(RELEASE/"production-control-state.json",130000))
    drift=json.loads(root_read(RELEASE/"production-drift.json",130000))
    need(control.get("circuit_breaker",{}).get("state")=="open"
         and control["circuit_breaker"].get("reason")=="continuous_production_drift_detected"
         and ((control.get("last_known_good") or {}).get("manifest") or {}).get("revision")==LKG
         and drift.get("status")=="drift_detected"
         and drift.get("problems")==[{"kind":"failed_system_unit","state":"failed",
                                      "unit":"jason-openclaw-authority-health.service"}],
         "UNRELATED_OR_CLOSED_PRODUCTION_BREAKER")
    value=proof_file(FULL)
    need(value.get("status")=="fail"
         and value.get("failures")==["operational_health_timeout"]
         and value.get("snapshot_source_exit_code")==124,
         "UNRELATED_FULL_HEALTH_FAILURE")
    fast=proof_file(FAST)
    need(fast.get("status")=="fail"
         and fast.get("failures")==["full_integrity_proof_missing_stale_or_invalid"],
         "UNRELATED_FAST_HEALTH_FAILURE")
    full_state=system_prop(UNIT,"ActiveState")
    need((full_state=="failed" and system_prop(UNIT,"ExecMainStatus")=="124"
          if full_unit_must_be_failed else full_state in ("activating","active"))
         and system_prop("jason-openclaw-authority-health.service","ActiveState")=="failed",
         "ACTUAL_SYSTEMD_HEALTH_CHANGED")
    for timer in ("jason-openclaw-authority-full-integrity.timer",
                  "jason-openclaw-authority-health.timer","jason-production-drift-watchdog.timer"):
        need(system_prop(timer,"ActiveState")=="active","HEALTH_TIMER_NOT_ACTIVE:"+timer)

def dataset():
    a=LIVE.lstat();archive=ARCHIVE.stat()
    need(not LIVE.is_symlink() and stat.S_ISREG(a.st_mode)
         and (a.st_uid,a.st_gid)==(1000,1000)
         and stat.S_IMODE(a.st_mode)==0o600 and a.st_nlink==1
         and 0<a.st_size<=68719476736 and a.st_dev!=archive.st_dev,
         "UNTRUSTED_LIVE_SQLITE")
    need(os.statvfs(ARCHIVE).f_bavail*os.statvfs(ARCHIVE).f_frsize>24*1024**3,
         "ARCHIVE_SCRATCH_INSUFFICIENT")
    need(os.statvfs(LIVE.parent).f_bavail*os.statvfs(LIVE.parent).f_frsize>3*1024**3,
         "SYSTEM_WAL_SPACE_INSUFFICIENT")
    return {"device":a.st_dev,"inode":a.st_ino}

def no_previous_claim():
    need(not os.path.lexists(RECORD) and not os.path.lexists(ROOT_BASE),
         "ONE_USE_RECOVERY_ALREADY_CLAIMED")
    need(not os.path.lexists(DROPIN),"ONE_USE_OVERRIDE_ALREADY_PRESENT")
    for p in (ROOT_BASE.parent,RECORD.parent):
        m=p.lstat()
        need(not p.is_symlink() and m.st_uid==m.st_gid==0
             and not m.st_mode&0o022,"UNTRUSTED_TARGET_PARENT:"+p.name)

def source_bootstrap(candidate):
    need(os.geteuid()==0 and sys.flags.isolated==1
         and re.fullmatch("[0-9a-f]{40}",candidate or "") is not None,
         "EXACT_ISOLATED_ROOT_REQUIRED")
    need(git("rev-parse","HEAD")==candidate
         and git("status","--porcelain","--untracked-files=all")==""
         and git("ls-remote","origin","refs/heads/main").split()[0]==candidate,
         "CURRENT_CLEAN_PROTECTED_MAIN_REQUIRED")
    blobs={name:exact_source(candidate,name) for name in SOURCES}
    old=exact_source(candidate,"tools/audit_journal_install.py")
    need(sha(old)==CORE_SHA,"PREVIOUS_APPROVED_TRUST_CORE_CHANGED")
    ns={"__name__":"reviewed_audit_root_primitives",
        "__file__":str(REPO/"tools/audit_journal_install.py")}
    exec(compile(old,str(REPO/"tools/audit_journal_install.py"),"exec"),ns)
    c,auth=ns["primitives"](candidate)
    return blobs,c,auth

def ci(candidate):
    raw=exact_source(candidate,"tools/pmv4_e_ci_refresh.py")
    n={"__name__":"exact_current_recovery_ci",
       "__file__":str(REPO/"tools/pmv4_e_ci_refresh.py")}
    exec(compile(raw,n["__file__"],"exec"),n)
    att=n["load_pinned_attestor"](n["SOURCE"],production=True)
    n["paginate_required_checks"](att)
    proof=att["verify_ci"](candidate)
    need(proof.get("required_ci_passed") is True
         and proof.get("protected_main")==candidate
         and proof.get("protected_main_ancestor") is True,
         "PROTECTED_MAIN_CI_NOT_PASSED")
    result=att["gh_api"](
       "repos/al-teamaot-com/jason/actions/workflows/audit-full-health-p0-recovery.yml/"
       "runs?head_sha="+candidate+"&event=push&per_page=100",
       "{total:.total_count,rows:[.workflow_runs[]|"
       "{sha:.head_sha,branch:.head_branch,event,status,conclusion}]}"
    )
    rows=result.get("rows",[])
    need(result.get("total")==len(rows)
         and len([x for x in rows if x.get("sha")==candidate
                  and x.get("branch")=="main" and x.get("event")=="push"
                  and x.get("status")=="completed" and x.get("conclusion")=="success"])==1,
         "EXACT_P0_HEALTH_RECOVERY_CI")
    return proof

def review_scope(candidate,blobs,c):
    installed_baseline()
    health_gate()
    identity=dataset()
    no_previous_claim()
    raw=exact_source(candidate,"tools/audit_journal_release_scope.py")
    module={"__name__":"exact_audit_recovery_peer_scope",
            "__file__":str(REPO/"tools/audit_journal_release_scope.py")}
    exec(compile(raw,module["__file__"],"exec"),module)
    peers=module["protected_peer_inventory"]()
    need(len(peers)==6,"UNEXPECTED_PROTECTED_CONTAINER_SET")
    return {
      "schema_version":"1.0","action":ACTION,
      "policy":{"candidate_sha":candidate,"rollback_sha":LKG},
      "installation_targets":[str(ROOT_BASE),str(RECORD),str(DROPIN),UNIT],
      "source_sha256":{name:sha(raw) for name,raw in blobs.items()},
      "existing_root_state_sha256":{
          str(p):sha(root_read(p)) for p in (FULL_DROPIN,FAST_DROPIN,CURRENT_WRAPPER)},
      "live_source_identity":identity,
      "protected_peers":peers,
      "protected_peers_source_sha256":sha(raw),
      "isolated_preproduction_shadow_health_is_observed_not_a_core_dependency":True,
      "freeze_sha256":FREEZE_SHA,"hold_sha256":HOLD_SHA,
      "queue_cutover":False,"audit_data_deletion_allowed":False,
      "audit_db_schema_change_allowed":False,
      "full_integrity_algorithm":"PRAGMA integrity_check (no quick_check)",
      "all_four_db_full_checks_required":True,"authority_backup_restore_required":True,
      "full_child_timeout_seconds":CHILD_DEADLINE,
      "transient_worker_timeout_seconds":JOB_DEADLINE,
      "same_canonical_live_audit_path":str(LIVE),
      "temporarily_installed_persistent_systemd_units":0,
      "temporary_override_must_be_removed_before_breaker_revalidation":True,
      "original_systemd_unit_bytes_modified":False,"native_root_breaker_bypass_allowed":False,
      "native_breaker_revalidate_only_after_true_pass":True,
      "provider_writes_allowed":False,"service_restarts_allowed":False,
      "health_oneshot_start_after_proof_allowed":True,
      "exact_one_use_owner_claim":True,
      "archive_source_release_not_authorized_by_this_action":True,
      "original_core_and_container_images_unchanged":True,
      "source_release_only_until_authenticated_owner_receipt":True,
    }


def safe_root_parent(path):
    m=path.lstat()
    need(not path.is_symlink() and stat.S_ISDIR(m.st_mode)
         and (m.st_uid,m.st_gid)==(0,0) and not m.st_mode&0o022,
         "ROOT_PARENT_UNTRUSTED:"+path.name)

def root_write(path,raw,mode=0o400):
    safe_root_parent(path.parent)
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,mode)
    try:
        os.fchown(fd,0,0)
        os.fchmod(fd,mode)
        with os.fdopen(fd,"wb",closefd=False) as f:
            f.write(raw);f.flush();os.fsync(f.fileno())
    finally:os.close(fd)
    fd=os.open(path.parent,os.O_DIRECTORY|os.O_RDONLY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)

def record_attempt(candidate,scope,blobs,actor,ci_evidence):
    need(actor==OWNER,"EXACT_LICENSED_OWNER_REQUIRED")
    safe_root_parent(RECORD.parent)
    safe_root_parent(ROOT_BASE.parent)
    need(not os.path.lexists(RECORD) and not os.path.lexists(ROOT_BASE),
         "ONE_USE_ATTEMPT_ALREADY_EXISTS")
    RECORD.mkdir(mode=0o700);os.chown(RECORD,0,0);os.chmod(RECORD,0o700)
    now=datetime.now(timezone.utc).isoformat()
    row={"schema_version":"1.0","action":ACTION,
         "status":"claimed_before_root_files_or_job","candidate_sha":candidate,
         "rollback_sha":LKG,"owner_oid":actor,
         "independently_verified_entra_owner":True,
         "approved_at":now,"claimed_at":now,
         "scope":scope,"scope_sha256":sha(canonical(scope)),
         "source_sha256":{name:sha(raw) for name,raw in blobs.items()},
         "required_ci_passed":ci_evidence.get("required_ci_passed") is True,
         "provider_writes_allowed":False,"native_breaker_bypass_allowed":False}
    root_write(RECORD/"attempt.json",canonical(row),0o400)
    return row

def install_trusted_source(blobs):
    need(not os.path.lexists(ROOT_BASE),"PREEXISTING_ROOT_HEALTH_CODE")
    need(not os.path.lexists(DROPIN),"PREEXISTING_P0_OVERRIDE")
    ROOT_BASE.mkdir(mode=0o755);os.chown(ROOT_BASE,0,0)
    for name,target in SOURCES.items():
        root_write(ROOT_BASE/target,blobs[name],0o444)
        need(sha(root_read(ROOT_BASE/target))==sha(blobs[name]),
             "ROOT_SOURCE_WRITE_FAILED:"+target)
    root_write(DROPIN,blobs["config/audit-full-health-p0-recovery.conf"],0o644)
    need(sha(root_read(DROPIN))==sha(blobs["config/audit-full-health-p0-recovery.conf"]),
         "ROOT_OVERRIDE_WRITE_FAILED")

def schedule_worker():
    # Reuse the already-declared native full-health unit; there is NO
    # undeclared transient systemd unit and no native desired-state exception.
    command(["/usr/bin/systemctl","daemon-reload"],timeout=35)
    need(system_prop(UNIT,"ExecStart").find(str(ROOT_SCRIPT))!=-1,
         "REVIEWED_ROOT_WORKER_NOT_LOADED")
    need(system_prop(UNIT,"User")=="root","ROOT_WORKER_USER_NOT_LOADED")
    command(["/usr/bin/systemctl","reset-failed",UNIT],timeout=35)
    command(["/usr/bin/systemctl","--no-block","start",UNIT],timeout=40)
    return UNIT

def rollback_override(blobs):
    raw=blobs["config/audit-full-health-p0-recovery.conf"]
    need(sha(root_read(DROPIN))==sha(raw),"ROOT_OVERRIDE_CHANGED_NO_DELETE")
    DROPIN.unlink()
    fd=os.open(DROPIN.parent,os.O_DIRECTORY|os.O_RDONLY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)
    command(["/usr/bin/systemctl","daemon-reload"],timeout=45)
    need(not os.path.lexists(DROPIN),"ROOT_OVERRIDE_REMOVAL_FAILED")

def current_attempt():
    safe_root_parent(RECORD)
    proof=json.loads(root_read(RECORD/"attempt.json",200000))
    need(proof.get("action")==ACTION
         and proof.get("owner_oid")==OWNER
         and proof.get("independently_verified_entra_owner") is True
         and proof.get("status")=="claimed_before_root_files_or_job"
         and proof.get("required_ci_passed") is True
         and proof.get("scope_sha256")==sha(canonical(proof["scope"])),
         "ROOT_SIGNED_SCOPE_CLAIM_INVALID")
    need(proof.get("source_sha256")
         ==proof["scope"].get("source_sha256"),"APPROVED_SOURCE_CLOSURE_CHANGED")
    for name,target in SOURCES.items():
        need(sha(root_read(ROOT_BASE/target))==proof["source_sha256"][name],
             "APPROVED_ROOT_FILE_CHANGED:"+target)
    return proof

def assert_worker_environment():
    need(os.geteuid()==0 and sys.flags.isolated==1
         and Path(__file__).resolve(strict=True)==ROOT_SCRIPT
         and ROOT_SCRIPT.stat().st_uid==0,
         "TRUSTED_IMMUTABLE_ROOT_WORKER_REQUIRED")
    cgroup=Path("/proc/self/cgroup").read_text()
    need(UNIT in cgroup,"ONLY_APPROVED_NATIVE_FULL_UNIT_MAY_EXECUTE")
    need(sha(root_read(DROPIN))==sha(root_read(ROOT_BASE/"reviewed-override.conf")),
         "APPROVED_NATIVE_ROOT_OVERRIDE_CHANGED")

def run_full():
    argv=["/usr/sbin/runuser","-u","al","--","/usr/bin/python3","-B",
          str(ROOT_BASE/"openclaw_authority_live_audit_full_snapshot.py"),
          "--output",str(FULL)]
    p=subprocess.Popen(argv,cwd="/",start_new_session=True,
                       stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    try:
        return p.wait(timeout=CHILD_DEADLINE+120)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid,signal.SIGTERM)
        try:p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=20)
        raise Denied("EXACT_SIX_HOUR_INTEGRITY_WORKER_TIMEOUT")

def verify_full_after(approved_at):
    m=FULL.lstat()
    at=datetime.fromisoformat(approved_at)
    need(not FULL.is_symlink() and stat.S_ISREG(m.st_mode)
         and m.st_uid==1000 and stat.S_IMODE(m.st_mode)==0o600
         and m.st_mtime>=at.timestamp()
         and m.st_nlink==1 and m.st_size<=200000,
         "FULL_EVIDENCE_NOT_FRESH_OR_OWNED")
    row=json.loads(FULL.read_bytes())
    need(row.get("status")=="pass" and row.get("failures")==[]
         and row.get("snapshot_source_exit_code")==0
         and row.get("provider_contacted") is False
         and row.get("provider_credentials_used") is False,
         "FULL_PROOF_NOT_PASS")
    paths={
        "authority":"/var/lib/jason/authority/authority.sqlite3",
        "replay":"/var/lib/jason/openclaw/replay.sqlite3",
        "security_audit":"/var/lib/jason/openclaw/security-audit.sqlite3",
        "orchestration_audit":str(LIVE),
    }
    files=row.get("files")
    need(isinstance(files,dict) and set(files)==set(paths)
         and all(isinstance(files[k],dict)
                 and files[k].get("path")==v
                 and files[k].get("integrity")=="ok"
                 and files[k].get("mode")=="0o600"
                 and files[k].get("present") is True
                 for k,v in paths.items()),"FOUR_FULL_DATABASE_PROOFS_MISSING")
    backup=row.get("backup_restore_proof",{})
    need(isinstance(backup,dict)
         and all(backup.get(k)==v for k,v in (
             ("backup_integrity","ok"),("restore_integrity","ok"),
             ("backup_mode","0o600"),("restore_mode","0o600"),
             ("counts_match",True))),"RESTORED_AUTHORITY_PROOF_MISSING")
    keys=row.get("trusted_key_registry",{})
    need(isinstance(keys,dict) and keys.get("present") is True
         and keys.get("mode")=="0o600" and
         int(keys.get("active_records",0))>=1,
         "ROOT_AUTHORITY_KEYS_NOT_PROVEN")
    need((row.get("delegations") or {}).get("expired_active_records")==0,
         "EXPIRED_ACTIVE_AUTHORITY_FOUND")
    return row

def system(*args,timeout=90):
    return command(["/usr/bin/systemctl",*args],timeout=timeout).stdout.strip()

def after_full_native_revalidation(approved_at):
    verify_full_after(approved_at)
    # Restoring a failed health unit is allowed only after genuine full PASS.
    system("reset-failed","jason-openclaw-authority-health.service")
    system("start","jason-openclaw-authority-health.service")
    latest=proof_file(FAST)
    need(latest.get("status")=="pass" and latest.get("failures")==[]
         and latest.get("snapshot_source_exit_code")==0
         and latest.get("full_proof_status")=="pass",
         "NORMAL_FAST_HEALTH_NOT_PASSED")
    stamps=[]
    for i in range(3):
        if i:time.sleep(17)
        system("start","jason-production-drift-watchdog.service")
        drift=json.loads(root_read(RELEASE/"production-drift.json",130000))
        need(drift.get("status")=="pass" and drift.get("problems")==[],
             "INDEPENDENT_DRIFT_NOT_PASSED")
        stamp=drift.get("observed_at")
        need(stamp and stamp not in stamps,"REPEATED_DRIFT_OBSERVATION")
        stamps.append(stamp)
    code=("import sys;from pathlib import Path;"
          "sys.path.insert(0,'/home/al/.local/lib/jason');"
          "import release_manager_host_runner as r;"
          "r.revalidate_circuit_breaker(Path('/var/lib/jason/openclaw/release-manager'))")
    command(["/usr/sbin/runuser","-u","al","--","/usr/bin/python3","-c",code],
            timeout=145)
    control=json.loads(root_read(RELEASE/"production-control-state.json",130000))
    need(control.get("circuit_breaker",{}).get("state")=="closed",
         "NATIVE_ROOT_BREAKER_NOT_CLOSED")
    return stamps

def worker():
    assert_worker_environment()
    attempt=current_attempt()
    scope=attempt["scope"]
    installed_baseline()
    health_gate(full_unit_must_be_failed=False)
    need(dataset()==scope["live_source_identity"],
         "INDEPENDENT_SOURCE_IDENTITY_CHANGED")
    need(not (RECORD/"result.json").exists()
         and not (RECORD/"work-start.json").exists(),
         "ONE_USE_WORKER_ALREADY_STARTED")
    root_write(RECORD/"work-start.json",canonical({
        "action":ACTION,"scope_sha256":attempt["scope_sha256"],
        "started_at":datetime.now(timezone.utc).isoformat()}),0o400)
    status={"schema_version":"1.0","action":ACTION,
            "candidate_sha":attempt["candidate_sha"],
            "scope_sha256":attempt["scope_sha256"],
            "started_at":datetime.now(timezone.utc).isoformat(),
            "status":"failed","full_proof_verified":False,
            "native_breaker_closed":False,"provider_writes":False,
            "data_reclamation_performed":False}
    try:
        code=run_full()
        need(code==0,"GENUINE_FULL_SQLITE_PROOF_EXIT_NONZERO")
        verify_full_after(attempt["approved_at"])
        status["full_proof_verified"]=True
        rollback_override({"config/audit-full-health-p0-recovery.conf":
                           root_read(ROOT_BASE/"reviewed-override.conf")})
        status["temporary_override_removed"]=True
        status["drift_observations"]=after_full_native_revalidation(
            attempt["approved_at"])
        status["native_breaker_closed"]=True
        status["status"]="verified"
        print("GENUINE_FULL_INTEGRITY_AND_RESTORE=PASS",flush=True)
        print("NATIVE_ROOT_BREAKER=CLOSED",flush=True)
    except Exception as exc:
        status["failure_class"]=type(exc).__name__
        status["failure_code"]=str(exc).split(":")[0][:100] if isinstance(exc,Denied) else "UNTRUSTED_ERROR"
        # Attempt exact rollback of the temporary override even on failure.
        # Unknown or changed bytes are preserved and cause further failure.
        if DROPIN.exists():
            try:
                rollback_override({"config/audit-full-health-p0-recovery.conf":
                                   root_read(ROOT_BASE/"reviewed-override.conf")})
                status["temporary_override_removed"]=True
            except Exception:
                status["temporary_override_removed"]=False
                status["cleanup_status"]="FAILED_CLOSED_EXACT_ROOT_REVIEW_REQUIRED"
        # Never emit fake PASS or directly change native control state.
        raise
    finally:
        status["completed_at"]=datetime.now(timezone.utc).isoformat()
        root_write(RECORD/"result.json",canonical(status),0o400)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--candidate-sha")
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight-only",action="store_true")
    mode.add_argument("--apply",action="store_true")
    mode.add_argument("--worker",action="store_true")
    a=p.parse_args()
    if a.worker:
        need(a.candidate_sha is None,"WORKER_ARGUMENTS_REJECTED")
        return worker()
    candidate=a.candidate_sha
    blobs,c,auth=source_bootstrap(candidate)
    with auth["locks"]():
        ci_proof=ci(candidate)
        scope=review_scope(candidate,blobs,c)
        print("P0_CURRENT_HEALTH_ROOT_PREFLIGHT=PASS",flush=True)
        print("EXACT_SOURCE_SHA="+candidate,flush=True)
        print("EXACT_SCOPE_SHA256="+sha(canonical(scope)),flush=True)
        if a.preflight_only:
            print("NO_OWNER_APPROVAL_REQUESTED_OR_PRODUCTION_ACTION=true",flush=True)
            return
        actor=auth["owner"](scope)
        need(actor==OWNER,"EXACT_AUTHENTICATED_OWNER_MISSING")
        need(review_scope(candidate,blobs,c)==scope,
             "ROOT_STATE_CHANGED_DURING_APPROVAL")
        attempt=record_attempt(candidate,scope,blobs,actor,ci_proof)
        try:
            install_trusted_source(blobs)
            schedule_worker()
            root_write(RECORD/"queue.json",canonical({
                "schema_version":"1.0","action":ACTION,
                "scope_sha256":attempt["scope_sha256"],
                "queued_at":datetime.now(timezone.utc).isoformat(),
                "unit":UNIT,"status":"root_worker_queued",
                "full_proof_pending":True}),0o400)
            print("P0_FULL_SQLITE_PROOF=QUEUED",flush=True)
            print("ONE_USE_VERIFIED_OWNER=CLAIMED",flush=True)
            print("GENUINE_PROOF_AND_ROOT_BREAKER=NOT_YET_ACCEPTED",flush=True)
            print("RESULT="+str(RECORD/"result.json"),flush=True)
        except Exception:
            # Claim remains consumed. Do not delete a potentially queued
            # worker's source files, or overwrite its partial results.
            if not (RECORD/"result.json").exists():
                root_write(RECORD/"bootstrap-failure.json",canonical({
                   "status":"failed_closed","scope_sha256":attempt["scope_sha256"],
                   "at":datetime.now(timezone.utc).isoformat()}),0o400)
            raise

if __name__=="__main__":
    try:
        main()
    except Exception as error:
        print("AUDIT_P0_RECOVERY=DENIED "+type(error).__name__+":"+
              (str(error).split(":")[0][:100] if isinstance(error,Denied)
               else "SENSITIVE_DETAILS_REDACTED"),file=sys.stderr)
        raise SystemExit(2)
