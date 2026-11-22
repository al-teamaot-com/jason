#!/usr/bin/env python3
"""Exact, one-use Owner-governed finalization of a *genuine* P0 SQLite PASS.

Repairs only the read-only systemd-sandbox cleanup failure of the already
completed, independently approved full integrity proof. No SQLite rescan,
data modification, release deployment, generic Root console, or breaker bypass.
This helper is run only directly by an authenticated Owner's sudo-capable
terminal, outside the original systemd ProtectSystem=strict mount namespace.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import argparse
from hashlib import sha256
import json
import os
import re
import stat
import subprocess
import sys
import time

REPO=Path(__file__).resolve().parents[1]
PREVIOUS=Path("tools/audit_full_health_p0_recovery.py")
ORIGINAL_SHA="8f8228f83ff80250e1500f7da5fe7d3ca848dc26"
ORIGINAL_SCOPE_SHA="14da3648487c0edc9f624fd65fa0b409dc6e61db9fab39707f6fe4907c7b183a"
ACTION="FINALIZE-VERIFIED-AUDIT-FULL-INTEGRITY-20261122"
OWNER="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
RECEIPT=Path("/var/lib/jason-owner-release/audit-full-health-p0-finalize-20261122")
MAX_PROOF_AGE=30*3600
FULL_UNIT="jason-openclaw-authority-full-integrity.service"
FAST_UNIT="jason-openclaw-authority-health.service"
CURRENT_92="/usr/local/lib/jason/authority-health-live-audit/openclaw_authority_live_audit_full_snapshot.py"
SAFE=("GIT_CONFIG_NOSYSTEM=1","GIT_CONFIG_GLOBAL=/dev/null",
      "GIT_OPTIONAL_LOCKS=0","GIT_NO_REPLACE_OBJECTS=1",
      "GIT_GRAFT_FILE=/dev/null","GIT_CONFIG_COUNT=2",
      "GIT_CONFIG_KEY_0=core.fsmonitor","GIT_CONFIG_VALUE_0=false",
      "GIT_CONFIG_KEY_1=core.hooksPath","GIT_CONFIG_VALUE_1=/dev/null")
U=("/usr/sbin/runuser","-u","al","--","/usr/bin/env",*SAFE)

class Denied(PermissionError):pass
def need(value,why):
    if not value:raise Denied("AUDIT_P0_FINALIZE_"+why)
def sha(raw):return sha256(raw).hexdigest()
def canon(row):return json.dumps(row,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def call(argv,timeout=60):
    p=subprocess.run(argv,cwd="/",text=True,capture_output=True,
                     timeout=timeout,check=False)
    need(p.returncode==0,"COMMAND_FAILED:"+Path(argv[0]).name)
    return p.stdout.strip()
def reviewed(candidate,name):
    p=REPO/name;m=p.lstat()
    need(not p.is_symlink() and stat.S_ISREG(m.st_mode) and m.st_uid==1000
         and m.st_nlink==1 and not m.st_mode&0o022 and m.st_size<2000000,
         "UNTRUSTED_SOURCE:"+name)
    raw=p.read_bytes()
    result=subprocess.run([*U,"/usr/bin/git","-C",str(REPO),"show",
                           candidate+":"+name],cwd="/",capture_output=True,
                          timeout=45,check=False)
    need(result.returncode==0 and result.stdout==raw,
         "EXACT_MAIN_SOURCE_DRIFT:"+name)
    return raw

def load_existing(candidate):
    need(os.geteuid()==0 and sys.flags.isolated==1
         and re.fullmatch("[0-9a-f]{40}",candidate or ""),
         "ISOLATED_ROOT_REQUIRED")
    raw=reviewed(candidate,str(PREVIOUS))
    namespace={"__name__":"original_approved_p0_primitives",
               "__file__":str(REPO/PREVIOUS)}
    exec(compile(raw,namespace["__file__"],"exec"),namespace)
    r=type("OriginalP0",(),namespace)
    need(r.ACTION=="RECOVER-EXACT-AUDIT-FULL-SQLITE-PROOF-20261122"
         and str(r.RECORD)=="/var/lib/jason-owner-release/audit-full-health-p0-20261122",
         "ORIGINAL_APPROVED_SOURCE_MISMATCH")
    blobs,controls,auth=r.source_bootstrap(candidate)
    return r,auth,raw

def read_approval(r):
    claim=r.current_attempt()
    need(claim.get("candidate_sha")==ORIGINAL_SHA
         and claim.get("scope_sha256")==ORIGINAL_SCOPE_SHA
         and claim.get("scope",{}).get("action")==r.ACTION
         and claim.get("owner_oid")==OWNER
         and claim.get("independently_verified_entra_owner") is True
         and claim.get("required_ci_passed") is True,
         "EXACT_PREVIOUS_OWNER_CLAIM_NOT_FOUND")
    row=json.loads(r.root_read(r.RECORD/"result.json",200000))
    need(row.get("action")==r.ACTION
         and row.get("candidate_sha")==ORIGINAL_SHA
         and row.get("scope_sha256")==ORIGINAL_SCOPE_SHA
         and row.get("status")=="failed"
         and row.get("full_proof_verified") is True
         and row.get("native_breaker_closed") is False
         and row.get("temporary_override_removed") is False
         and row.get("failure_class")=="OSError"
         and row.get("failure_code")=="UNTRUSTED_ERROR"
         and row.get("cleanup_status")=="FAILED_CLOSED_EXACT_ROOT_REVIEW_REQUIRED",
         "NOT_THE_EXACT_FAILED_FINALIZATION")
    started=json.loads(r.root_read(r.RECORD/"work-start.json",100000))
    need(started.get("scope_sha256")==ORIGINAL_SCOPE_SHA
         and started.get("action")==r.ACTION,
         "PREVIOUS_ONE_USE_WORK_RECORD_MISSING")
    return claim,row

def proven_live_health(r,approved_at):
    report=r.verify_full_after(approved_at)
    m=r.FULL.lstat()
    age=time.time()-m.st_mtime
    need(0<=age<=MAX_PROOF_AGE,"FULL_EVIDENCE_TOO_OLD")
    fresh=r.proof_file(r.FAST)
    need(fresh.get("status")=="pass"
         and fresh.get("failures")==[]
         and fresh.get("snapshot_source_exit_code")==0
         and fresh.get("full_proof_status")=="pass",
         "LATEST_FAST_HEALTH_NOT_PASS")
    need(r.FAST.stat().st_mtime>=r.FULL.stat().st_mtime,
         "FAST_PROOF_OLDER_THAN_FULL_PROOF")
    return sha(r.FULL.read_bytes())

def scope(candidate,r,claim,previous,source):
    r.installed_baseline()
    fp=proven_live_health(r,claim["approved_at"])
    identity=r.dataset()
    need(identity==claim["scope"]["live_source_identity"],
         "APPROVED_DATABASE_IDENTITY_CHANGED")
    dropin=r.root_read(r.DROPIN,200000)
    need(sha(dropin)==claim["source_sha256"]["config/audit-full-health-p0-recovery.conf"],
         "TEMPORARY_93_OVERRIDE_CHANGED")
    need(r.system_prop(FULL_UNIT,"ActiveState")=="failed"
         and r.system_prop(FULL_UNIT,"ExecMainStatus")=="2"
         and r.system_prop(FAST_UNIT,"ActiveState") in ("inactive","failed"),
         "EXPECTED_POST_PROOF_SERVICE_FAILURE_CHANGED")
    writable=r.system_prop(FULL_UNIT,"ReadWritePaths").split()
    writable_paths=[Path(x.lstrip("-+")) for x in writable]
    need(r.system_prop(FULL_UNIT,"User")=="root"
         and r.system_prop(FULL_UNIT,"ProtectSystem")=="strict"
         and not any(p==r.DROPIN or p in r.DROPIN.parents
                     for p in writable_paths),
         "ORIGINAL_SANDBOX_FAILURE_CAUSE_CHANGED")
    for name in ("jason-openclaw-authority-full-integrity.timer",
                 "jason-openclaw-authority-health.timer",
                 "jason-production-drift-watchdog.timer"):
        need(r.system_prop(name,"ActiveState")=="active",
             "WATCHDOG_TIMER_MISSING:"+name)
    control=json.loads(r.root_read(r.RELEASE/"production-control-state.json",150000))
    need(control.get("circuit_breaker",{}).get("state")=="open"
         and control["circuit_breaker"].get("reason")=="continuous_production_drift_detected"
         and (control.get("last_known_good",{}).get("manifest",{}).get("revision"))==r.LKG,
         "UNRELATED_OR_UNRECOVERABLE_NATIVE_BREAKER")
    drift=json.loads(r.root_read(r.RELEASE/"production-drift.json",150000))
    need(drift.get("status") in ("pass","drift_detected")
         and drift.get("problems") in (
             [],[{"kind":"failed_system_unit","unit":FAST_UNIT,"state":"failed"}],
             [{"kind":"failed_system_unit","unit":FULL_UNIT,"state":"failed"}],
             [{"kind":"failed_system_unit","unit":FAST_UNIT,"state":"failed"},
              {"kind":"failed_system_unit","unit":FULL_UNIT,"state":"failed"}]),
         "UNRELATED_PRODUCTION_DRIFT_FOUND")
    need(not os.path.lexists(RECEIPT),
         "FINALIZE_ALREADY_CLAIMED")
    r.safe_root_parent(RECEIPT.parent)
    exact=reviewed(candidate,"tools/audit_journal_release_scope.py")
    ns={"__name__":"exact_audit_repair_peer_inventory",
        "__file__":str(REPO/"tools/audit_journal_release_scope.py")}
    exec(compile(exact,ns["__file__"],"exec"),ns)
    peers=ns["protected_peer_inventory"]()
    need(len(peers)==6,"PROTECTED_PEERS_CHANGED")
    need(sha(r.root_read(r.ROOT_SCRIPT,100000))==
         claim["source_sha256"]["tools/audit_full_health_p0_recovery.py"],
         "ACTUAL_USED_ROOT_WORKER_CHANGED")
    return {"schema_version":"1.0","action":ACTION,
            "candidate_sha":candidate,"rollback_sha":r.LKG,
            "previous_approved_action":r.ACTION,
            "previous_owner_claim_sha256":sha(r.root_read(r.RECORD/"attempt.json",200000)),
            "previous_worker_result_sha256":sha(r.root_read(r.RECORD/"result.json",200000)),
            "previous_scope_sha256":ORIGINAL_SCOPE_SHA,
            "source_sha256":sha(source),
            "full_integrity_proof_sha256":fp,
            "original_root_worker_sha256":sha(r.root_read(r.ROOT_SCRIPT,100000)),
            "exact_temporary_dropin_sha256":sha(dropin),
            "temporary_override_target":str(r.DROPIN),
            "native_health_service":FULL_UNIT,
            "native_breaker_revalidation_only":True,
            "provider_writes":False,"database_writes":False,
            "archive_installation":False,"data_reclamation":False,
            "root_unit_restart":False,"fast_health_oneshot":True,
            "native_drift_observations":3,
            "only_change_delete_exact_93_and_restore_existing_health":True,
            "existing_lkg_and_freezes_unchanged":True,
            "original_data_identity":identity,
            "peers":peers}


def verified_ci(candidate,r):
    r.ci(candidate)
    raw=reviewed(candidate,"tools/pmv4_e_ci_refresh.py")
    ns={"__name__":"p0_finalize_protected_main_ci",
        "__file__":str(REPO/"tools/pmv4_e_ci_refresh.py")}
    exec(compile(raw,ns["__file__"],"exec"),ns)
    attest=ns["load_pinned_attestor"](ns["SOURCE"],production=True)
    result=attest["gh_api"](
       "repos/al-teamaot-com/jason/actions/workflows/audit-full-health-finalize.yml/"
       "runs?head_sha="+candidate+"&event=push&per_page=100",
       "{total:.total_count,rows:[.workflow_runs[]|"
       "{sha:.head_sha,branch:.head_branch,event,status,conclusion}]}",
    )
    rows=result.get("rows",[])
    need(result.get("total")==len(rows)
         and len([x for x in rows if x.get("sha")==candidate
                  and x.get("branch")=="main" and x.get("event")=="push"
                  and x.get("status")=="completed"
                  and x.get("conclusion")=="success"])==1,
         "EXACT_PROTECTED_MAIN_FINALIZE_CI_NOT_PASSED")

def claim_one_use(r,candidate,reviewed_scope,actor):
    need(actor==OWNER,"APPROVED_OWNER_NOT_VERIFIED")
    need(not os.path.lexists(RECEIPT),"FINALIZER_ALREADY_CLAIMED")
    r.safe_root_parent(RECEIPT.parent)
    RECEIPT.mkdir(mode=0o700)
    os.chown(RECEIPT,0,0)
    os.chmod(RECEIPT,0o700)
    row={"schema_version":"1.0","action":ACTION,
         "candidate_sha":candidate,"owner_oid":actor,
         "independently_verified_entra_owner":True,
         "scope":reviewed_scope,"scope_sha256":sha(canon(reviewed_scope)),
         "claimed_at":datetime.now(timezone.utc).isoformat(),
         "status":"exact_one_use_claimed_before_root_mutation"}
    r.root_write(RECEIPT/"attempt.json",canon(row),0o400)
    return row

def ensure_native_original(r,claim):
    need(not os.path.lexists(r.DROPIN),"TEMPORARY_93_OVERRIDE_NOT_REMOVED")
    need(r.system_prop(FULL_UNIT,"User")=="al",
         "ORIGINAL_FULL_UNIT_USER_NOT_RESTORED")
    need(CURRENT_92 in r.system_prop(FULL_UNIT,"ExecStart"),
         "ORIGINAL_FULL_UNIT_EXECSTART_NOT_RESTORED")
    need(r.system_prop(FULL_UNIT,"ProtectSystem")=="strict",
         "ORIGINAL_FULL_UNIT_SECURITY_CHANGED")
    need(r.system_prop(FULL_UNIT,"TimeoutStartUSec")=="1h 35min"
         or r.system_prop(FULL_UNIT,"TimeoutStartUSec")=="5700000000",
         "ORIGINAL_FULL_UNIT_TIMEOUT_NOT_RESTORED")
    r.installed_baseline()
    need(r.dataset()==claim["scope"]["live_source_identity"],
         "ORIGINAL_DATABASE_IDENTITY_DRIFT")

def finalize(r,claim,approved_at):
    status={"schema_version":"1.0","action":ACTION,
            "scope_sha256":sha(canon(claim["scope"])),
            "status":"failed","native_breaker_closed":False,
            "installed_exact_93_override_removed":False,
            "full_integrity_verified":False,"provider_writes":False,
            "database_modified":False,"archive_migration":False,
            "started_at":datetime.now(timezone.utc).isoformat()}
    try:
        r.verify_full_after(approved_at)
        status["full_integrity_verified"]=True
        need(sha(r.FULL.read_bytes())==claim["scope"]["full_integrity_proof_sha256"],
             "GENUINE_FULL_PROOF_CHANGED_AFTER_OWNER_APPROVAL")
        raw=r.root_read(r.DROPIN,200000)
        need(sha(raw)==claim["scope"]["exact_temporary_dropin_sha256"],
             "EXACT_OVERRIDE_CHANGED_BEFORE_UNLINK")
        # Intentional one-file delete, outside the full-health unit's
        # ProtectSystem=strict read-only /etc mount namespace.
        r.DROPIN.unlink()
        fd=os.open(r.DROPIN.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)
        call(["/usr/bin/systemctl","daemon-reload"],40)
        status["installed_exact_93_override_removed"]=True
        call(["/usr/bin/systemctl","reset-failed",FULL_UNIT],40)
        ensure_native_original(r,claim)
        # The existing signed native code, not this tool, evaluates
        # the real fast check, three watchdog observations, and breaker.
        stamps=r.after_full_native_revalidation(approved_at)
        need(len(stamps)==len(set(stamps))==3,
             "THREE_INDEPENDENT_DRIFT_SAMPLES_NOT_VERIFIED")
        status["three_native_drift_observations"]=stamps
        state=json.loads(r.root_read(
              r.RELEASE/"production-control-state.json",150000))
        need(state.get("circuit_breaker",{}).get("state")=="closed"
             and state["circuit_breaker"].get("reason")
                 =="authoritative_health_revalidated",
             "NATIVE_BREAKER_NOT_INDEPENDENTLY_CLOSED")
        status["native_breaker_closed"]=True
        status["status"]="verified"
        print("EXACT_93_TEMPORARY_ROOT_OVERRIDE=REMOVED",flush=True)
        print("GENUINE_FOUR_DATABASE_SQLITE_AND_RESTORE=PASS",flush=True)
        print("NATIVE_FAST_HEALTH_AND_DRIFT=PASS",flush=True)
        print("NATIVE_RELEASE_BREAKER=CLOSED",flush=True)
    except Exception as exc:
        status["failure_class"]=type(exc).__name__
        status["failure_code"]=(str(exc).split(":")[0][:120]
          if isinstance(exc,Denied) else "SENSITIVE_DETAILS_REDACTED")
        # No rollback by recreating a one-use 93 Root worker. The normal
        # full-health unit is strictly safer and contains the real proof.
        raise
    finally:
        status["completed_at"]=datetime.now(timezone.utc).isoformat()
        r.root_write(RECEIPT/"result.json",canon(status),0o400)

def main():
    parser=argparse.ArgumentParser()
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight-only",action="store_true")
    mode.add_argument("--apply",action="store_true")
    parser.add_argument("--candidate-sha",required=True)
    args=parser.parse_args()
    candidate=args.candidate_sha
    r,auth,previous_source=load_existing(candidate)
    own_source=reviewed(candidate,"tools/audit_full_health_p0_finalize.py")
    need(sha(own_source)==sha(Path(__file__).read_bytes()),
         "REVIEWED_FINALIZE_SOURCE_NOT_EXECUTED")
    with auth["locks"]():
        verified_ci(candidate,r)
        prior,prior_result=read_approval(r)
        planned=scope(candidate,r,prior,prior_result,own_source)
        print("P0_GENUINE_FULL_HEALTH_FINALIZATION_PREFLIGHT=PASS",flush=True)
        print("REVIEWED_SOURCE_SHA="+candidate,flush=True)
        print("EXACT_SCOPE_SHA256="+sha(canon(planned)),flush=True)
        print("ORIGINAL_APPROVED_SCOPE_SHA256="+ORIGINAL_SCOPE_SHA,flush=True)
        if args.preflight_only:
            print("NO_OWNER_AUTH_OR_PRODUCTION_MUTATION=true",flush=True)
            return
        actor=auth["owner"](planned)
        need(actor==OWNER,"VERIFIED_EXACT_LICENSED_OWNER_MISSING")
        again=scope(candidate,r,prior,prior_result,own_source)
        need(planned==again,"LIVE_EXACT_RELEASE_SCOPE_CHANGED_DURING_APPROVAL")
        receipt=claim_one_use(r,candidate,planned,actor)
        finalize(r,receipt,prior["approved_at"])

if __name__=="__main__":
    try:main()
    except Exception as exc:
        value=(str(exc).split(":")[0][:100]
               if isinstance(exc,Denied) else "SENSITIVE_DETAILS_REDACTED")
        print("AUDIT_P0_FINALIZE=DENIED "+
              type(exc).__name__+":"+value,file=sys.stderr)
        raise SystemExit(2)
