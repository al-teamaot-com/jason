#!/usr/bin/env python3
"""Exact one-Owner root-only A1 watchdog admission, NOT a general policy editor.

One authenticated Ed25519-bound decision authorizes only the optional
jason-pmv4-shadow-gateway allowlist entry. Never starts the shadow, changes
provider authority, weakens drift, restarts systemd or mutates PMv3 services.
The original policy bytes are atomically restored on any failed postflight.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Any, Mapping

TRUSTED = Path("/usr/local/lib/jason/pmv4-trusted")
if os.geteuid() == 0 and TRUSTED.is_dir():
    sys.path.insert(0, str(TRUSTED))
from tools import pmv4_host_release_guard as host_guard
from tools import pmv4_shadow_release as shadow
from tools import pmv4_shadow_ci as ci

ACTION = "pmv4-a1-exact-one-container-root-watchdog-admission-v1"
SOURCE = "860dc8b90cfd1cb847cb0713ac7908b280b2265d"
BASE = "8c2064193d74cc41b52369681febbc0a74fa96f7"
LKG = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
NAME = "jason-pmv4-shadow-gateway"
SOURCE_POLICY_SHA = "db3eaf92b16ccfb3d0bad6bd351ab99bffb84bd9a338bb8321ac7c0691562b50"
OLD_SHA = "4af577ccc02c367607da0c221c288df71ddc72bf4561ee6d7c6a35138f37e61c"
NEW_SHA = "9d3d4a634f2b347b760da80e0dc2bb057d3b35ddcbaf88293bffd47971d0c804"
FREEZE_SHA = "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
HOLD_SHA = "11f0f78904236c36ebd1aeee58f52fcecba035bce33d15ce323b36d36ad5a5a0"
POLICY = Path("/etc/jason/release-readback-recovery/production-desired-state.json")
ROOT_DIR = POLICY.parent
AUDIT = ROOT_DIR / "pmv4-a1-onecontainer-860dc8"
BACKUP = AUDIT / "original-policy.bin"
INTENT = AUDIT / "intent.json"
COMMIT = AUDIT / "committed.json"
RECOVERY = AUDIT / "recovered.json"
STAGED = Path("/run/jason-pmv4-a1-policy-860dc8/installer.py")
PACK = Path("/srv/jason/archive/engineering-artifacts/pmv4-a1-watchdog-860dc8")
PLAN = PACK / "exact-policy-plan.json"
PROOF = PACK / "exact-one-owner-proof.json"
ROOT_KEY = shadow.TRUST_PATH
FREEZE = Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
HOLD = Path("/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold")
SOURCE_REPO = Path("/home/al/.local/lib/jason/engineering-source-repo")
REVIEW_REPO = Path("/srv/jason/archive/engineering-worktrees/pmv4-a1-watchdog-allowlist-20261116")
GIT_PR = "2500"
MAX_POLICY = 131072


class PolicyRootDenied(PermissionError):
    pass


def need(ok:bool, reason:str)->None:
    if not ok:
        raise PolicyRootDenied(reason)


def canon(obj:Mapping[str,Any])->bytes:
    return json.dumps(dict(obj),sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False).encode()


def digest(raw:bytes)->str:
    return sha256(raw).hexdigest()


def object_file(path:Path, *, max_bytes:int=50000)->dict[str,Any]:
    try:
        m=path.lstat()
        need(not path.is_symlink() and stat.S_ISREG(m.st_mode)
             and m.st_nlink==1 and 0<m.st_size<=max_bytes
             and not m.st_mode&0o022,
             "A1_POLICY_SOURCE_FILE_UNTRUSTED")
        v=json.loads(path.read_bytes())
        need(isinstance(v,dict),"A1_POLICY_SOURCE_SCHEMA_NOT_OBJECT")
        return v
    except (OSError,ValueError,TypeError) as exc:
        raise PolicyRootDenied("A1_POLICY_SOURCE_UNAVAILABLE") from exc


def exact_policy(old_bytes:bytes)->bytes:
    need(isinstance(old_bytes,bytes) and 0<len(old_bytes)<=MAX_POLICY,
         "A1_POLICY_ORIGINAL_BYTES_INVALID")
    need(digest(old_bytes)==OLD_SHA,"A1_POLICY_ORIGINAL_SHA_CHANGED")
    try:
        old=json.loads(old_bytes)
    except (ValueError,TypeError) as exc:
        raise PolicyRootDenied("A1_POLICY_ORIGINAL_JSON_UNTRUSTED") from exc
    need(isinstance(old,dict) and old.get("schema_version")=="1.0",
         "A1_POLICY_ORIGINAL_SCHEMA_INVALID")
    names=old.get("allowed_running_containers")
    required=old.get("required_containers")
    need(isinstance(names,list) and isinstance(required,list)
         and all(isinstance(x,str) and x for x in names+required)
         and len(names)==len(set(names)) and len(required)==len(set(required))
         and set(required).issubset(set(names))
         and NAME not in names and NAME not in required,
         "A1_POLICY_CONTAINER_BASELINE_UNTRUSTED")
    new={key:list(value) if isinstance(value,list) else value for key,value in old.items()}
    new["allowed_running_containers"].append(NAME)
    need(set(new)==set(old)
         and all(new[k]==old[k] for k in old if k!="allowed_running_containers")
         and new["required_containers"]==old["required_containers"],
         "A1_POLICY_SCOPE_NOT_EXACT")
    result=(json.dumps(new,sort_keys=True,indent=2,separators=(",",": "))+"\n").encode()
    need(digest(result)==NEW_SHA,"A1_POLICY_CANDIDATE_HASH_NOT_REVIEWED")
    return result


def read_root_original()->bytes:
    need(ROOT_DIR.is_dir() and not ROOT_DIR.is_symlink(),
         "A1_ROOT_POLICY_DIRECTORY_MISSING")
    m=ROOT_DIR.lstat()
    need(m.st_uid==0 and m.st_gid==0 and stat.S_IMODE(m.st_mode)==0o700,
         "A1_ROOT_POLICY_DIRECTORY_UNTRUSTED")
    flags=os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_CLOEXEC",0)
    fd=os.open(POLICY,flags)
    try:
        info=os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_nlink==1
             and info.st_uid==0 and info.st_gid==0
             and stat.S_IMODE(info.st_mode)==0o600
             and 0<info.st_size<=MAX_POLICY,
             "A1_ROOT_POLICY_INODE_UNTRUSTED")
        data=os.read(fd,MAX_POLICY+1)
        need(len(data)==info.st_size,"A1_ROOT_POLICY_READ_LENGTH_CHANGED")
        return data
    finally:
        os.close(fd)


def fixed_plan()->dict[str,Any]:
    script=Path(__file__).resolve(strict=True)
    return {
        "schema_version":"1.0",
        "action":ACTION,
        "source_sha":SOURCE,
        "protected_main_sha":BASE,
        "rollback_sha":BASE,
        "root_executor_sha256":digest(script.read_bytes()),
        "root_original_policy_sha256":OLD_SHA,
        "root_target_policy_sha256":NEW_SHA,
        "source_candidate_policy_sha256":SOURCE_POLICY_SHA,
        "production_lkg":LKG,
        "production_freeze_sha256":FREEZE_SHA,
        "production_hold_sha256":HOLD_SHA,
        "docker_allowance_name":NAME,
        "git_pr_number":GIT_PR,
        "only_add_optional_container":True,
        "production_ticket_runtime_changes":False,
        "drift_watchdog_disabled":False,
        "owner_consents":1,
        "standing_authority":False,
    }


def plan_valid()->dict[str,Any]:
    plan=object_file(PLAN)
    expected=fixed_plan()
    review_head=plan.get("reviewed_pr_head_sha")
    need(set(plan)==set(expected)|{"scope_sha256","reviewed_pr_head_sha"}
         and isinstance(review_head,str) and len(review_head)==40
         and all(x in "0123456789abcdef" for x in review_head)
         and all(plan.get(k)==v for k,v in expected.items())
         and plan["scope_sha256"]==digest(canon({**expected,"reviewed_pr_head_sha":review_head})),
         "A1_POLICY_PLAN_HASH_OR_SCOPE_CHANGED")
    return plan


def root_script_trusted()->None:
    need(os.geteuid()==0,"A1_POLICY_ROOT_REQUIRED")
    path=Path(__file__).resolve(strict=True)
    info=path.lstat()
    need(path==STAGED and not path.is_symlink()
         and stat.S_ISREG(info.st_mode) and info.st_uid==0
         and info.st_gid==0 and info.st_nlink==1
         and stat.S_IMODE(info.st_mode)==0o400,
         "A1_POLICY_ROOT_EXECUTOR_NOT_PINNED")
    m=STAGED.parent.lstat()
    need(stat.S_ISDIR(m.st_mode) and m.st_uid==0 and m.st_gid==0
         and stat.S_IMODE(m.st_mode)==0o700
         and not STAGED.parent.is_symlink(),
         "A1_POLICY_ROOT_STAGE_NOT_TRUSTED")


def run_as_al(args:list[str],*,timeout:int=30)->subprocess.CompletedProcess:
    return subprocess.run(
        ["/usr/sbin/runuser","-u","al","--",*args],
        capture_output=True,text=True,timeout=timeout,check=False,
    )


def source_attestation(reviewed_head:str)->None:
    main=run_as_al(["/usr/bin/gh","api",
                    "repos/al-teamaot-com/jason/branches/main","--jq",".commit.sha"])
    need(main.returncode==0 and main.stdout.strip()==BASE,
         "A1_POLICY_PROTECTED_MAIN_MOVED")
    pr=run_as_al(["/usr/bin/gh","pr","view",GIT_PR,
                  "--repo","al-teamaot-com/jason",
                  "--json","headRefOid,state,isDraft"])
    need(pr.returncode==0,"A1_POLICY_PR_UNAVAILABLE")
    receipt=json.loads(pr.stdout)
    need(receipt=={"headRefOid":reviewed_head,"state":"OPEN","isDraft":True},
         "A1_POLICY_REVIEWED_PR_CHANGED")
    ancestry=run_as_al(["/usr/bin/git","-C",str(REVIEW_REPO),
                        "merge-base","--is-ancestor",SOURCE,reviewed_head])
    need(ancestry.returncode==0,"A1_POLICY_REVIEWED_SOURCE_NOT_ANCESTOR")
    checks=run_as_al(["/usr/bin/gh","pr","checks",GIT_PR,
                      "--repo","al-teamaot-com/jason"])
    need(checks.returncode==0,"A1_POLICY_CI_NOT_ALL_PASS")
    lines=[row.split("\t") for row in checks.stdout.splitlines() if row.strip()]
    need(len(lines)>=10 and all(len(x)>=2 and x[1]=="pass" for x in lines),
         "A1_POLICY_CI_EVIDENCE_INVALID")
    original=run_as_al(["/usr/bin/git","-C",str(SOURCE_REPO),
                        "show",BASE+":config/production-desired-state.json"])
    proposed=run_as_al(["/usr/bin/git","-C",str(REVIEW_REPO),
                        "show",reviewed_head+":config/production-desired-state.json"])
    need(original.returncode==0 and proposed.returncode==0
         and digest(proposed.stdout.encode())==SOURCE_POLICY_SHA,
         "A1_POLICY_GIT_BYTES_CHANGED")
    before=json.loads(original.stdout)
    after=json.loads(proposed.stdout)
    need(set(after)==set(before)
         and NAME not in before["allowed_running_containers"]
         and after["allowed_running_containers"]==before["allowed_running_containers"]+[NAME]
         and all(after[k]==before[k] for k in before if k!="allowed_running_containers"),
         "A1_POLICY_SOURCE_DELTA_NOT_SINGLE_CONTAINER")


def controls_and_host()->host_guard.IndependentHostGuard:
    need(digest(FREEZE.read_bytes())==FREEZE_SHA
         and digest(HOLD.read_bytes())==HOLD_SHA
         and Path("/opt/jason/current").resolve(strict=True).name==LKG,
         "A1_POLICY_FREEZE_HOLD_OR_LKG_CHANGED")
    host=host_guard.IndependentHostGuard()
    need(host.protected_release_status().get("ready") is True
         and host.preexisting_core_health() is True
         and host.host_mutation_quiescent() is True,
         "A1_POLICY_PROTECTED_HOST_NOT_READY")
    return host


def preflight()->tuple[dict[str,Any],host_guard.IndependentHostGuard]:
    root_script_trusted()
    plan=plan_valid()
    source_attestation(plan["reviewed_pr_head_sha"])
    need(not AUDIT.exists() and not AUDIT.is_symlink(),
         "A1_POLICY_OWNER_TRANSACTION_ALREADY_ATTEMPTED")
    exact_policy(read_root_original())
    host=controls_and_host()
    return plan,host


def verify_owner(plan:Mapping[str,Any],*,at:datetime|None=None)->dict[str,Any]:
    record=object_file(PROOF, max_bytes=15000)
    need(set(record)=={"schema_version","action","source_sha",
                       "scope_sha256","approval_id","signed_release"}
         and record["schema_version"]=="1.0" and record["action"]==ACTION
         and record["source_sha"]==SOURCE
         and record["scope_sha256"]==plan["scope_sha256"],
         "A1_POLICY_OWNER_PROOF_SCOPE_MISMATCH")
    public=shadow.read_pinned_root_owner_public_key(
        ROOT_KEY,require_root_owned=True)
    receipt=shadow.verify_exact_owner_release(
        record["signed_release"],public_key=public,
        at=at or datetime.now(timezone.utc),
        expected_candidate_sha=SOURCE,
        expected_rollback_sha=BASE,
        expected_release_id="release-"+SOURCE[:16],
        expected_scope_sha256=plan["scope_sha256"],
        expected_manifest_sha256=digest(canon(plan)),
        expected_freeze_sha256=FREEZE_SHA,
    )
    need(receipt["approval_id"]==record["approval_id"],
         "A1_POLICY_OWNER_APPROVAL_ID_CHANGED")
    return receipt


def write_exclusive(path:Path,data:bytes,*,mode:int=0o600)->None:
    need(not path.exists() and not path.is_symlink()
         and mode==0o600 and len(data)<=MAX_POLICY,
         "A1_POLICY_AUDIT_FILE_ALREADY_EXISTS")
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|
               getattr(os,"O_NOFOLLOW",0),mode)
    try:
        with os.fdopen(fd,"wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
    finally:
        pass
    info=path.lstat()
    need(info.st_uid==os.geteuid() and info.st_gid==os.getegid()
         and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==mode
         and digest(path.read_bytes())==digest(data),
         "A1_POLICY_AUDIT_FILE_NOT_DURABLE")


def fsync_dir(path:Path)->None:
    handle=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(handle)
    finally:os.close(handle)


def replace_policy(data:bytes,*,token:str)->None:
    need(digest(data) in (OLD_SHA,NEW_SHA),
         "A1_POLICY_ATOMIC_REPLACEMENT_NOT_REVIEWED")
    temp=ROOT_DIR/(".pmv4-a1-"+token)
    write_exclusive(temp,data)
    need(POLICY.is_file() and not POLICY.is_symlink(),
         "A1_POLICY_TARGET_CHANGED")
    os.replace(temp,POLICY)
    fsync_dir(ROOT_DIR)
    need(digest(read_root_original())==digest(data),
         "A1_POLICY_ATOMIC_REPLACEMENT_READBACK_FAILED")


def drift_now()->None:
    proc=subprocess.run([
        "/usr/bin/python3","/opt/jason/current/tools/production_drift_guard.py",
        "--config",str(POLICY)
    ],capture_output=True,text=True,check=False,timeout=100)
    need(proc.returncode==0 and len(proc.stdout)<=250000,
         "A1_POLICY_INDEPENDENT_DRIFT_GUARD_FAILED")
    out=json.loads(proc.stdout)
    need(out.get("status")=="pass" and out.get("problems")==[],
         "A1_POLICY_INDEPENDENT_DRIFT_NOT_PASS")


def journal_file(name:Path,record:dict[str,Any])->None:
    write_exclusive(name,canon(record))
    fsync_dir(AUDIT)


def execute()->None:
    plan,host=preflight()
    approval=verify_owner(plan)
    with host.host_release_transaction():
        host._assert_protected_release_state()
        need(host.preexisting_core_health() is True,
             "A1_POLICY_CORE_NOT_HEALTHY_UNDER_HOST_LOCK")
        source_attestation(plan["reviewed_pr_head_sha"])
        need(digest(FREEZE.read_bytes())==FREEZE_SHA
             and digest(HOLD.read_bytes())==HOLD_SHA,
             "A1_POLICY_FREEZE_OR_HOLD_MOVED")
        original=read_root_original()
        target=exact_policy(original)
        need(not AUDIT.exists() and not AUDIT.is_symlink(),
             "A1_POLICY_AUDIT_REPLAY")
        AUDIT.mkdir(mode=0o700)
        fsync_dir(ROOT_DIR)
        now=datetime.now(timezone.utc).isoformat()
        journal_file(INTENT,{
            "action":ACTION,"owner_approval_id":approval["approval_id"],
            "source_sha":SOURCE,"scope_sha256":plan["scope_sha256"],
            "original_sha256":OLD_SHA,"target_sha256":NEW_SHA,
            "started_at":now,"standing_authority":False,
        })
        write_exclusive(BACKUP,original)
        fsync_dir(AUDIT)
        need(digest(BACKUP.read_bytes())==OLD_SHA,
             "A1_POLICY_ROLLBACK_BYTES_NOT_DURABLE")
        try:
            replace_policy(target,token="candidate-860dc8")
            drift_now()
            need(host.preexisting_core_health() is True
                 and host.protected_release_status().get("ready") is True
                 and digest(FREEZE.read_bytes())==FREEZE_SHA
                 and digest(HOLD.read_bytes())==HOLD_SHA,
                 "A1_POLICY_POSTFLIGHT_PRODUCTION_CONTINUITY_FAILED")
            journal_file(COMMIT,{
                "status":"committed","owner_approval_id":approval["approval_id"],
                "source_sha":SOURCE,"scope_sha256":plan["scope_sha256"],
                "original_sha256":OLD_SHA,"target_sha256":NEW_SHA,
                "completed_at":datetime.now(timezone.utc).isoformat(),
                "drift_independently_verified":True,
                "production_ticket_runtime_changed":False,
                "production_freeze_or_hold_changed":False,
            })
        except BaseException:
            # This is the approved original-byte recovery, never general repair.
            try:
                now_bytes=read_root_original()
                if digest(now_bytes)==NEW_SHA:
                    replace_policy(original,token="restore-860dc8")
                need(digest(read_root_original())==OLD_SHA,
                     "A1_POLICY_ORIGINAL_BYTES_NOT_RESTORED")
                journal_file(RECOVERY,{
                    "status":"original_bytes_restored",
                    "owner_approval_id":approval["approval_id"],
                    "original_sha256":OLD_SHA,
                    "restored_at":datetime.now(timezone.utc).isoformat(),
                })
            except BaseException as recovery_error:
                print("A1_POLICY_ROOT_RECOVERY=FAILED_NEEDS_ROOT_REVIEW",file=sys.stderr)
            raise
    print("A1_ROOT_WATCHDOG_EXACT_ONE_NAME=COMMITTED")
    print("OWNER_APPROVAL_ID="+approval["approval_id"])
    print("ORIGINAL_POLICY_HASH="+OLD_SHA)
    print("TARGET_POLICY_HASH="+NEW_SHA)
    print("DRIFT_WATCHDOG_STILL_ENFORCED=true")
    print("PRODUCTION_CORE_FREEZE_HOLD_UNCHANGED=true")


def postflight()->None:
    root_script_trusted()
    plan=plan_valid()
    need(INTENT.is_file() and BACKUP.is_file() and COMMIT.is_file()
         and not RECOVERY.exists(),"A1_POLICY_COMMIT_NOT_DURABLE")
    intent=object_file(INTENT)
    commit=object_file(COMMIT)
    need(digest(BACKUP.read_bytes())==OLD_SHA
         and commit.get("status")=="committed"
         and intent["owner_approval_id"]==commit["owner_approval_id"]
         and intent["scope_sha256"]==plan["scope_sha256"],
         "A1_POLICY_AUDITED_EXACT_BYTES_MISMATCH")
    original_time=datetime.fromisoformat(intent["started_at"])
    end=datetime.fromisoformat(commit["completed_at"])
    need(original_time.tzinfo and end.tzinfo
         and original_time<=end
         and end-original_time<=timedelta(minutes=15),
         "A1_POLICY_AUDIT_TIME_NOT_BOUND")
    owner=verify_owner(plan,at=original_time)
    need(owner["approval_id"]==intent["owner_approval_id"],
         "A1_POLICY_AUDIT_OWNER_MISMATCH")
    need(digest(read_root_original())==NEW_SHA,
         "A1_POLICY_FINAL_HASH_MISMATCH")
    need(digest(FREEZE.read_bytes())==FREEZE_SHA
         and digest(HOLD.read_bytes())==HOLD_SHA,
         "A1_POLICY_GLOBAL_CONTROLS_MOVED")
    host=host_guard.IndependentHostGuard()
    need(host.protected_release_status().get("ready") is True
         and host.preexisting_core_health() is True,
         "A1_POLICY_PROTECTED_HOST_POSTFLIGHT_FAILED")
    drift_now()
    print("A1_WATCHDOG_ROOT_ONE_OWNER_POSTFLIGHT=PASS")
    print("ROOT_ORIGINAL_BYTES_ROLLBACK_PRESERVED=true")


def main()->int:
    parser=argparse.ArgumentParser()
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight",action="store_true")
    mode.add_argument("--execute",action="store_true")
    mode.add_argument("--postflight",action="store_true")
    args=parser.parse_args()
    try:
        if args.preflight:
            preflight()
            print("A1_ROOT_POLICY_INITIAL_PRECHECK=PASS")
            print("OWNER_APPROVAL_NOT_ISSUED=true; ROOT_WRITES=false")
        elif args.execute:execute()
        else:postflight()
        return 0
    except Exception as exc:
        reason=str(exc)
        if not reason or len(reason)>140 or "/" in reason:
            reason="A1_POLICY_ROOT_INTERNAL_DENIAL"
        print("A1_ROOT_POLICY=DENIED "+type(exc).__name__+":"+reason,
              file=sys.stderr,flush=True)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
