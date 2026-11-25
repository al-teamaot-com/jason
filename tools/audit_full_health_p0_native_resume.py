#!/usr/bin/env python3
"""Finish the unfinished *same* Owner-approved P0 native revalidation once.

No new Owner action, no Entra challenge, no archive install, no new Root worker.
The existing Root-owned prior Entra Owner exact-action claim is authoritative
only for the still-incomplete work *within that exact previously approved
scope*. Its already-done 93 cleanup is NOT replayed.

This is recovery from a post-approval KeyError in the previously-reviewed
finalizer. Immutable Root receipts and the original reviewed source must
prove the exact partial completion before any native action is permitted.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import threading
import time

REPO=Path(__file__).resolve().parents[1]
PREVIOUS_FINALIZER="tools/audit_full_health_p0_finalize.py"
CURRENT_SOURCE="tools/audit_full_health_p0_native_resume.py"
APPROVED_FINALIZER_SHA="e7131fb36d65c96d630a3417611d02cda666e972"
APPROVED_FINALIZER_SOURCE_SHA256="a2f3713e0c91e6612abdb71b76694d642ce67051e53633770dfc30959451d3c8"
APPROVED_FINALIZER_SCOPE_SHA256="74e53eef7fb774546c3cb6eebb3ad1cdabeb32030265cd825075de00a077abe7"
ACTION="FINALIZE-VERIFIED-AUDIT-FULL-INTEGRITY-20261122"
OWNER_OID="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
RECEIPT=Path("/var/lib/jason-owner-release/audit-full-health-p0-native-resume-20261122")
PROOF_WINDOW_SECONDS=30*3600
AUDIT_RECORD=Path("/var/lib/jason-audit-journal/control/release-status.json")
NATIVE_ROOT_CONTROLLER=Path("/usr/local/lib/jason/release_control_transition_worker.py")
NATIVE_ROOT_CONTROLLER_SHA="02ce315d9e96e1e655c3465f5fc2761661f78e5ced5b13f849680a85f2a1ff7e"
NATIVE_ROOT_UNIT=Path("/etc/systemd/system/jason-release-control-transition.service")
NATIVE_ROOT_UNIT_SHA="759837f9c873ebe2964031343166e1b59e7f99aab76c8d89c506c09aaffd3192"
NATIVE_READBACK_WORKER=Path("/usr/local/lib/jason/release_control_bridge_worker.py")
NATIVE_READBACK_WORKER_SHA="a5a1eee07ca5afd26fd204e6575eb6c709c3fd6d5cd0b0b2a719694e16dadfec"
NATIVE_READBACK_UNIT=Path("/etc/systemd/system/jason-release-control-readback.service")
NATIVE_READBACK_UNIT_SHA="7b6b55bfcfb9b0a88b2c4705bd87a740b61c1c2f6182d73ea09ec211d17e3b83"
NATIVE_REQUESTS=Path("/var/lib/jason/openclaw/release-manager/protected-transitions/requests")
FAST="jason-openclaw-authority-health.service"
FULL="jason-openclaw-authority-full-integrity.service"
SAFE=("GIT_CONFIG_NOSYSTEM=1","GIT_CONFIG_GLOBAL=/dev/null",
      "GIT_OPTIONAL_LOCKS=0","GIT_NO_REPLACE_OBJECTS=1",
      "GIT_GRAFT_FILE=/dev/null","GIT_CONFIG_COUNT=2",
      "GIT_CONFIG_KEY_0=core.fsmonitor","GIT_CONFIG_VALUE_0=false",
      "GIT_CONFIG_KEY_1=core.hooksPath","GIT_CONFIG_VALUE_1=/dev/null")
RUN_USER=("/usr/sbin/runuser","-u","al","--","/usr/bin/env",*SAFE)

class Denied(PermissionError):pass
def need(value,reason):
    if not value:raise Denied("AUDIT_P0_AUTHORIZED_NATIVE_RESUME_"+reason)
def sha(b):return sha256(b).hexdigest()
def canon(x):return json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def reviewed_git(candidate,name):
    p=REPO/name;m=p.lstat()
    need(not p.is_symlink() and stat.S_ISREG(m.st_mode)
         and m.st_uid==1000 and m.st_nlink==1 and not m.st_mode&0o022
         and 0<m.st_size<2000000,
         "CURRENT_PROTECTED_MAIN_SOURCE_CUSTODY:"+name)
    raw=p.read_bytes()
    result=subprocess.run([*RUN_USER,"/usr/bin/git","-C",str(REPO),
                           "show",candidate+":"+name],
                          cwd="/",capture_output=True,check=False,timeout=45)
    need(result.returncode==0 and raw==result.stdout,
         "CURRENT_PROTECTED_MAIN_SOURCE_MISMATCH:"+name)
    return raw
def original_reviewed_bytes():
    p=subprocess.run([*RUN_USER,"/usr/bin/git","-C",str(REPO),
                      "show",APPROVED_FINALIZER_SHA+":"+PREVIOUS_FINALIZER],
                     cwd="/",capture_output=True,check=False,timeout=45)
    need(p.returncode==0 and sha(p.stdout)==APPROVED_FINALIZER_SOURCE_SHA256,
         "PREVIOUS_APPROVED_EXECUTED_SOURCE_NOT_RETRIEVABLE")
    return p.stdout
def load_previous_finalizer(candidate):
    source=reviewed_git(candidate,PREVIOUS_FINALIZER)
    need(sha(source)==APPROVED_FINALIZER_SOURCE_SHA256
         and source==original_reviewed_bytes(),
         "PREVIOUS_APPROVED_EXECUTED_SOURCE_CHANGED")
    ns={"__name__":"reviewed_p0_original_finalizer",
        "__file__":str(REPO/PREVIOUS_FINALIZER)}
    exec(compile(source,ns["__file__"],"exec"),ns)
    return ns
def utc_age(iso):
    value=datetime.fromisoformat(str(iso).replace("Z","+00:00"))
    need(value.tzinfo is not None,"EVIDENCE_TIMESTAMP_NO_TZ")
    return (datetime.now(timezone.utc)-value).total_seconds()
def check_root_state(f,r,old,prior,claim,failed,candidate,source):
    """Validate partial completion without reusing original one-use worker."""
    need(not os.path.lexists(RECEIPT),"ALREADY_RESUMED_OR_CLAIMED")
    r.safe_root_parent(RECEIPT.parent)
    need(claim.get("candidate_sha")==APPROVED_FINALIZER_SHA
         and claim.get("scope_sha256")==APPROVED_FINALIZER_SCOPE_SHA256
         and claim.get("owner_oid")==OWNER_OID
         and claim.get("independently_verified_entra_owner") is True
         and claim.get("status")=="exact_one_use_claimed_before_root_mutation",
         "EXACT_PREVIOUS_OWNER_ENTRA_CLAIM_NOT_VERIFIED")
    approved=claim.get("scope")
    need(isinstance(approved,dict)
         and sha(canon(approved))==APPROVED_FINALIZER_SCOPE_SHA256
         and approved.get("action")==ACTION
         and approved.get("candidate_sha")==APPROVED_FINALIZER_SHA
         and approved.get("rollback_sha")==r.LKG
         and approved.get("policy")=={"candidate_sha":APPROVED_FINALIZER_SHA,
                                      "rollback_sha":r.LKG}
         and approved.get("source_sha256")==APPROVED_FINALIZER_SOURCE_SHA256
         and approved.get("native_breaker_revalidation_only") is True
         and approved.get("native_drift_observations")==3
         and approved.get("only_change_delete_exact_93_and_restore_existing_health") is True
         and approved.get("provider_writes") is False
         and approved.get("database_writes") is False
         and approved.get("archive_installation") is False
         and approved.get("data_reclamation") is False
         and approved.get("root_unit_restart") is False
         and approved.get("queue_cutover") is False,
         "EXACT_PREVIOUS_OWNER_ACTION_OR_SCOPE_CHANGED")
    need(approved.get("installation_targets")==[
          str(r.DROPIN),FULL,FAST]
         and approved.get("temporary_override_target")==str(r.DROPIN)
         and approved.get("original_data_identity")==prior["scope"]["live_source_identity"]
         and approved.get("original_root_worker_sha256")==
               sha(r.root_read(r.ROOT_SCRIPT,100000))
         and approved.get("previous_owner_claim_sha256")==
               sha(r.root_read(r.RECORD/"attempt.json",200000))
         and approved.get("previous_worker_result_sha256")==
               sha(r.root_read(r.RECORD/"result.json",200000))
         and approved.get("previous_scope_sha256")==old["ORIGINAL_SCOPE_SHA"],
         "PREVIOUS_SIGNED_SOURCE_AND_ORIGINAL_SCOPE_CHANGED")
    need(0<=utc_age(claim.get("claimed_at"))<=PROOF_WINDOW_SECONDS,
         "EXACT_PREVIOUS_OWNER_APPROVAL_WINDOW_EXPIRED")
    need(failed.get("action")==ACTION
         and failed.get("scope_sha256")==APPROVED_FINALIZER_SCOPE_SHA256
         and failed.get("status")=="failed"
         and failed.get("failure_class")=="KeyError"
         and failed.get("failure_code")=="SENSITIVE_DETAILS_REDACTED"
         and failed.get("full_integrity_verified") is True
         and failed.get("installed_exact_93_override_removed") is True
         and failed.get("native_breaker_closed") is False
         and failed.get("database_modified") is False
         and failed.get("archive_migration") is False,
         "NOT_EXACT_KNOWN_POST_OWNER_PARTIAL_FAILURE")
    need(not os.path.lexists(r.DROPIN),
         "TEMPORARY_93_MUST_BE_ALREADY_REMOVED")
    need(r.system_prop(FULL,"User")=="al"
         and f["CURRENT_92"] in r.system_prop(FULL,"ExecStart")
         and r.system_prop(FULL,"ProtectSystem")=="strict"
         and r.system_prop(FULL,"ActiveState")=="inactive"
         and r.system_prop(FULL,"TimeoutStartUSec") in ("1h 35min","5700000000"),
         "REVIEWED_ORIGINAL_HEALTH_92_NOT_RESTORED")
    r.installed_baseline()
    now_identity=r.dataset()
    need(now_identity==approved["original_data_identity"],
         "APPROVED_CANONICAL_DATABASE_DEVICE_INODE_CHANGED")
    # The original broken finalizer read "live_source_identity" from this
    # new scope instead of its valid "original_data_identity" value.
    # Verify the correct signed identity without mutating either receipt.
    need("live_source_identity" not in approved,
         "PREVIOUS_KEY_ERROR_NOT_EXACT_IDENTIFIED")
    f["proven_live_health"](r,prior["approved_at"])
    need(sha(r.FULL.read_bytes())==approved["full_integrity_proof_sha256"],
         "GENUINE_FULL_PROOF_CHANGED_AFTER_APPROVAL")
    need(r.proof_file(r.FAST).get("status")=="pass",
         "NATIVE_FAST_HEALTH_NO_LONGER_PASS")
    for timer in ("jason-openclaw-authority-full-integrity.timer",
                  "jason-openclaw-authority-health.timer",
                  "jason-production-drift-watchdog.timer"):
        need(r.system_prop(timer,"ActiveState")=="active",
             "NATIVE_HEALTH_WATCHDOG_TIMER_MISSING:"+timer)
    policy=json.loads(r.root_read(
          r.RELEASE/"production-control-state.json",200000))
    drift=json.loads(r.root_read(r.RELEASE/"production-drift.json",200000))
    need(policy.get("circuit_breaker",{}).get("state")=="open"
         and policy["circuit_breaker"].get("reason")==
               "continuous_production_drift_detected"
         and policy.get("last_known_good",{}).get("manifest",{}).get("revision")==r.LKG
         and drift.get("status")=="pass" and drift.get("problems")==[]
         and 0<=utc_age(drift.get("observed_at"))<=300,
         "NATIVE_BREAKER_OR_DRIFT_NOT_IN_APPROVED_STATE")
    need(not os.path.lexists(AUDIT_RECORD),
         "ARCHIVE_WORK_ALREADY_STARTED")
    peer_raw=reviewed_git(candidate,"tools/audit_journal_release_scope.py")
    peer_ns={"__name__":"approved_read_only_production_peer_inventory",
             "__file__":str(REPO/"tools/audit_journal_release_scope.py")}
    exec(compile(peer_raw,peer_ns["__file__"],"exec"),peer_ns)
    peers=peer_ns["protected_peer_inventory"]()
    need(peers==approved["peers"],"PREVIOUS_OWNER_APPROVED_PEERS_CHANGED")
    return {
        "action":ACTION,"continuation":"unperformed_native_revalidation_only",
        "candidate_sha":candidate,"rollback_sha":r.LKG,
        "original_owner_candidate_sha":APPROVED_FINALIZER_SHA,
        "original_owner_oid":OWNER_OID,
        "original_owner_exact_scope_sha256":APPROVED_FINALIZER_SCOPE_SHA256,
        "original_owner_claim_sha256":sha(r.root_read(f["RECEIPT"]/"attempt.json",200000)),
        "original_failed_result_sha256":sha(r.root_read(f["RECEIPT"]/"result.json",200000)),
        "original_reviewed_source_sha256":APPROVED_FINALIZER_SOURCE_SHA256,
        "current_reviewed_resume_source_sha256":sha(source),
        "real_full_proof_sha256":sha(r.FULL.read_bytes()),
        "original_data_identity":now_identity,
        "recorded_production_peers":peers,
        "actions_remaining":["existing_fast_health_oneshot",
                             "three_native_drift_observations",
                             "native_root_breaker_revalidation"],
        "delete_or_replace_files":False,"new_owner_approval":False,
        "provider_writes":False,"data_reclamation":False,
        "archive_installation":False,"new_release":False,
        "no_reexecution_of_old_root_worker":True
    }


def load_root_source(candidate):
    need(os.geteuid()==0 and sys.flags.isolated==1
         and re.fullmatch("[0-9a-f]{40}",candidate or ""),
         "ROOT_ISOLATED_EXACT_MAIN_ONLY")
    verified=reviewed_git(candidate,CURRENT_SOURCE)
    need(Path(__file__).resolve(strict=True)==REPO/CURRENT_SOURCE
         and sha(Path(__file__).read_bytes())==sha(verified),
         "EXECUTED_SOURCE_NOT_VERIFIED_FROM_CURRENT_MAIN")
    f=load_previous_finalizer(candidate)
    r,auth,_=f["load_existing"](candidate)
    need(f["ACTION"]==ACTION and f["OWNER"]==OWNER_OID,
         "ORIGINAL_FINALIZER_ACTION_OR_IDENTITY_CHANGED")
    return f,r,auth,verified

def read_existing_exact_claim(f,r):
    previous_owner,original_result=f["read_approval"](r)
    prior=json.loads(r.root_read(f["RECEIPT"]/"attempt.json",200000))
    failed=json.loads(r.root_read(f["RECEIPT"]/"result.json",200000))
    return previous_owner,original_result,prior,failed

def claim_one_use(r,candidate,scope):
    need(not os.path.lexists(RECEIPT),"REPEATED_USE_DENIED")
    r.safe_root_parent(RECEIPT.parent)
    RECEIPT.mkdir(mode=0o700)
    os.chown(RECEIPT,0,0)
    os.chmod(RECEIPT,0o700)
    value={"schema_version":"1.0","action":ACTION,
           "continuation":"previous_owner_approved_native_revalidation",
           "source_candidate_sha":candidate,
           "scope":scope,"scope_sha256":sha(canon(scope)),
           "original_owner_oid":OWNER_OID,
           "original_entra_approval_reused_only_within_same_exact_scope":True,
           "one_use_native_resume":True,
           "claimed_at":datetime.now(timezone.utc).isoformat()}
    r.root_write(RECEIPT/"attempt.json",canon(value),0o400)
    return value

def reviewed_native_root_controller(r):
    # Allow only the already-installed root-governed transition worker.
    for p,hash_value,mode in (
        (NATIVE_ROOT_CONTROLLER,NATIVE_ROOT_CONTROLLER_SHA,0o755),
        (NATIVE_ROOT_UNIT,NATIVE_ROOT_UNIT_SHA,0o644),
        (NATIVE_READBACK_WORKER,NATIVE_READBACK_WORKER_SHA,0o755),
        (NATIVE_READBACK_UNIT,NATIVE_READBACK_UNIT_SHA,0o644)):
        m=p.lstat()
        need(stat.S_ISREG(m.st_mode) and not p.is_symlink()
             and (m.st_uid,m.st_gid)==(0,0)
             and stat.S_IMODE(m.st_mode)==mode
             and m.st_nlink==1 and sha(p.read_bytes())==hash_value,
             "ORIGINAL_GOVERNED_ROOT_TRANSITION_CHANGED")
    need(r.system_prop("jason-release-control-transition.service","User")=="root"
         and r.system_prop("jason-release-control-transition.service","ProtectSystem")=="strict"
         and r.system_prop("jason-release-control-transition.service","ActiveState")=="inactive"
         and r.system_prop("jason-release-control-readback.service","User")=="root"
         and r.system_prop("jason-release-control-readback.service","ProtectSystem")=="strict"
         and r.system_prop("jason-release-control-readback.service","ActiveState")=="inactive",
         "NATIVE_ROOT_TRANSITION_UNIT_DRIFT")
    m=NATIVE_REQUESTS.lstat()
    need(stat.S_ISDIR(m.st_mode) and not NATIVE_REQUESTS.is_symlink()
         and (m.st_uid,m.st_gid)==(1000,1000)
         and stat.S_IMODE(m.st_mode)==0o700,
         "NATIVE_ROOT_REQUEST_CUSTODY_CHANGED")
    need(not list(NATIVE_REQUESTS.iterdir()),"UNRELATED_ROOT_REQUEST_PENDING")

def dispatch_only_exact_native_request(r,stop,outcome):
    """Activate existing Root service once when its reviewed native request arrives.

    No timer, daemon, or helper is installed; no raw mutation of breaker JSON.
    The Root worker itself independently evaluates drift and protected LKG.
    """
    deadline=time.monotonic()+150
    try:
        while not stop.is_set() and time.monotonic()<deadline:
            paths=list(NATIVE_REQUESTS.iterdir())
            if paths:
                need(len(paths)==1,"MULTIPLE_ROOT_TRANSITION_REQUESTS")
                p=paths[0];meta=p.lstat()
                need(stat.S_ISREG(meta.st_mode) and not p.is_symlink()
                     and (meta.st_uid,meta.st_gid)==(1000,1000)
                     and stat.S_IMODE(meta.st_mode)==0o600
                     and meta.st_nlink==1 and 1<=meta.st_size<=4096,
                     "UNTRUSTED_ROOT_REQUEST")
                row=json.loads(p.read_bytes())
                need(re.fullmatch("[0-9a-f]{32}",p.stem or "")
                     and p.suffix==".json"
                     and row.get("request_id")==p.stem
                     and row.get("action")=="revalidate"
                     and row.get("revision")==r.LKG
                     and row.get("release_id")==""
                     and row.get("reason")==""
                     and set(row)=={"request_id","action","revision",
                                   "release_id","reason"},
                     "WRONG_OR_FOREIGN_ROOT_TRANSITION_INTENT")
                result=subprocess.run(["/usr/bin/systemctl","start",
                   "jason-release-control-transition.service"],cwd="/",
                   capture_output=True,text=True,timeout=90,check=False)
                need(result.returncode==0,"NATIVE_ROOT_TRANSITION_WORKER_FAILED")
                outcome["native_controller_started"]=True
                # Stage E deliberately retired both *timers*. This one-use
                # Root-attested readback is needed for the original native
                # caller to observe the independently closed breaker.
                published=subprocess.run(["/usr/bin/systemctl","start",
                     "jason-release-control-readback.service"],cwd="/",
                     capture_output=True,text=True,timeout=60,check=False)
                need(published.returncode==0,"NATIVE_ROOT_READBACK_FAILED")
                outcome["native_readback_published"]=True
                return
            time.sleep(0.2)
        if not stop.is_set():
            raise Denied("REVIEWED_NATIVE_ROOT_REVALIDATION_REQUEST_NEVER_APPEARED")
    except BaseException as exc:
        outcome["error"]=exc

def finish_native(r,prior_old,approved,resume_record):
    row={"schema_version":"1.0","action":ACTION,
         "original_owner_oid":OWNER_OID,
         "original_owner_exact_scope_sha256":APPROVED_FINALIZER_SCOPE_SHA256,
         "resume_scope_sha256":sha(canon(resume_record["scope"])),
         "state":"failed","native_breaker_closed":False,
         "genuine_full_integrity_verified":False,
         "archive_installation":False,"archive_data_reclamation":False,
         "provider_writes":False,"replayed_93_cleanup":False,
         "started_at":datetime.now(timezone.utc).isoformat()}
    try:
        verified=r.verify_full_after(prior_old["approved_at"])
        need(sha(r.FULL.read_bytes())==resume_record["scope"]["real_full_proof_sha256"],
             "ORIGINAL_GENUINE_FULL_PROOF_NO_LONGER_MATCHES")
        row["genuine_full_integrity_verified"]=True
        need(not os.path.lexists(r.DROPIN),
             "DELETED_93_MUST_NOT_REAPPEAR")
        need(r.dataset()==resume_record["scope"]["original_data_identity"],
             "DB_INODE_OR_MOUNT_CHANGED_BEFORE_NATIVE_REVALIDATION")
        # The original Root-approved native procedure invokes its reviewed
        # non-root caller, while a narrow Root watcher invokes only the
        # original installed native Root worker to service its exact request.
        reviewed_native_root_controller(r)
        stop=threading.Event();outcome={}
        thread=threading.Thread(target=dispatch_only_exact_native_request,
                                args=(r,stop,outcome),daemon=True)
        thread.start()
        try:
            native_samples=r.after_full_native_revalidation(prior_old["approved_at"])
        finally:
            stop.set();thread.join(timeout=95)
        need(not thread.is_alive() and not outcome.get("error"),
             "NATIVE_ROOT_TRANSITION_DISPATCH_FAILED")
        need(outcome.get("native_controller_started") is True
             and outcome.get("native_readback_published") is True,
             "REVIEWED_ROOT_CONTROL_AND_READBACK_WORKERS_NOT_OBSERVED")
        need(isinstance(native_samples,list)
             and len(native_samples)==len(set(native_samples))==3,
             "THREE_REAL_NATIVE_DRIFT_PROOFS_REQUIRED")
        actual=json.loads(r.root_read(
            r.RELEASE/"production-control-state.json",150000))
        need(actual.get("circuit_breaker",{}).get("state")=="closed"
             and actual["circuit_breaker"].get("reason")==
                 "root_verified_revalidate"
             and actual["circuit_breaker"].get("revalidated_revision")==r.LKG,
             "ROOT_NATIVE_BREAKER_NOT_INDEPENDENTLY_CLOSED")
        r.installed_baseline()
        need(not os.path.lexists(r.DROPIN),
             "DELETED_93_REAPPEARED_AFTER_NATIVE_CHECK")
        row["three_native_drift_observations"]=native_samples
        row["native_root_controller_started"]=True
        row["native_root_readback_published"]=True
        row["native_breaker_closed"]=True
        row["state"]="verified"
        print("PREVIOUS_EXACT_ENTRA_OWNER_APPROVAL=VERIFIED_AND_REUSED_SAME_SCOPE",flush=True)
        print("GENUINE_4_DATABASE_AND_RESTORED_AUTHORITY=PASS",flush=True)
        print("ORIGINAL_92_HEALTH_RESTORED=PASS",flush=True)
        print("THREE_NATIVE_ROOT_DRIFT_OBSERVATIONS=PASS",flush=True)
        print("ROOT_GOVERNED_BREAKER=CLOSED",flush=True)
        print("AUDIT_ARCHIVE_STILL_SEPARATELY_GOVERNED=true",flush=True)
    except Exception as exc:
        row["failure_class"]=type(exc).__name__
        row["failure_code"]=(str(exc).split(":")[0][:130]
            if isinstance(exc,Denied) else "SENSITIVE_DETAILS_REDACTED")
        raise
    finally:
        row["completed_at"]=datetime.now(timezone.utc).isoformat()
        r.root_write(RECEIPT/"result.json",canon(row),0o400)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--candidate-sha",required=True)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight-only",action="store_true")
    mode.add_argument("--resume-existing-exact-owner",action="store_true")
    args=parser.parse_args()
    candidate=args.candidate_sha
    f,r,auth,source=load_root_source(candidate)
    with auth["locks"]():
        f["verified_ci"](candidate,r)
        original,old_result,prior,failed=read_existing_exact_claim(f,r)
        planned=check_root_state(f,r,f,original,prior,failed,candidate,source)
        print("P0_SAME_OWNER_AUTHORIZED_NATIVE_REVALIDATION_PREFLIGHT=PASS",flush=True)
        print("CURRENT_REVIEWED_MAIN_SHA="+candidate,flush=True)
        print("ORIGINAL_APPROVED_MAIN_SHA="+APPROVED_FINALIZER_SHA,flush=True)
        print("PREVIOUS_APPROVED_ACTION="+ACTION,flush=True)
        print("PREVIOUS_APPROVED_SCOPE_SHA256="+APPROVED_FINALIZER_SCOPE_SHA256,flush=True)
        print("REMAINING_NATIVE_ONLY_SCOPE_SHA256="+sha(canon(planned)),flush=True)
        if args.preflight_only:
            print("NO_NEW_APPROVAL_PROMPT_OR_PRODUCTION_MUTATION=true",flush=True)
            return
        again=check_root_state(f,r,f,original,prior,failed,candidate,source)
        need(planned==again,"EXACT_PARTIALLY_COMPLETED_OWNER_SCOPE_CHANGED")
        record=claim_one_use(r,candidate,planned)
        finish_native(r,original,prior,record)

if __name__=="__main__":
    try:main()
    except Exception as exc:
        message=(str(exc).split(":")[0][:110] if isinstance(exc,Denied)
                 else "SENSITIVE_DETAILS_REDACTED")
        print("AUDIT_NATIVE_EXACT_AUTHORIZED_RESUME=DENIED "+
              type(exc).__name__+":"+message,file=sys.stderr)
        raise SystemExit(2)
