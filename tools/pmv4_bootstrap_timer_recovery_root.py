#!/usr/bin/env python3
"""One-use exact Owner/root retirement of an obsolete completed-install timer.

This is NOT a PMv4 cutover or breaker override. The exact stale timer is
superseded; independent scoped catalog recovery and all other guards remain.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
import time
from uuid import uuid4

ACTION = "pmv4-completed-catalog-bootstrap-timer-supersession-v1"
CONFIRM = "APPROVE-EXACT-COMPLETED-CATALOG-BOOTSTRAP-TIMER-RETIREMENT"
ARTIFACTS = Path("/srv/jason/archive/engineering-artifacts")
STAGE = Path("/run")
INSTALL_PLAN = Path("/srv/jason/archive/engineering-evidence/catalog-scoped-root-install-20261117/unsigned-root-install-plan.json")
BOOTSTRAP_TRUST = Path("/etc/jason-owner-release/catalog-scoped-root-bootstrap-trust.json")
INSTALLED_POLICY = Path("/etc/jason-owner-release/catalog-scoped-promotion-installed.json")
ROOT_JOURNALS = Path("/var/lib/jason-catalog-scoped-promotion/root-installer-audit")
SCOPED_TIMER = "jason-catalog-scoped-recovery.timer"
OLD_TIMER = "jason-catalog-root-bootstrap-recovery.timer"
OLD_SERVICE = "jason-catalog-root-bootstrap-recovery.service"
WATCHDOG = "jason-production-drift-watchdog.service"
SOURCE_SHA = "01ba71c54d9dd0391734b16a92d0b292fc457ae9"
FREEZE = Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
HOST_LKG = Path("/opt/jason/current")
CONTROL = Path("/var/lib/jason/openclaw/release-manager/protected-readback/production-control-state.json")
ROOT_POLICY = Path("/etc/jason/release-readback-recovery/production-desired-state.json")
RELEASE_LOCK = Path("/var/lib/jason/openclaw/release-manager/production-transaction.lock")
PMV4_LOCK = Path("/var/lib/jason/pmv4-shadow/control/host-mutation.lock")
AUDIT = Path("/etc/jason-owner-release/pmv4-bootstrap-timer-recovery")
OWNER_HELPER = Path("/usr/local/lib/jason/owner_signer_recovery.py")
OWNER_HELPER_SHA = "24d3632a4b0aa60851a1c82ccb15539eb823dd26afa5a1a2cc8c7afc54d72153"
PROTECTED_CONTAINERS = (
    "jason-runtime", "jason-mcp-pilot", "jason-teams-gateway",
    "openbao",
)
SHADOW = "jason-pmv4-shadow-gateway"
SHA40 = re.compile(r"^[a-f0-9]{40}$")
SHA64 = re.compile(r"^[a-f0-9]{64}$")

class BootstrapTimerRecoveryDenied(PermissionError):
    pass

def need(ok: bool, reason: str) -> None:
    if not ok:
        raise BootstrapTimerRecoveryDenied("BOOTSTRAP_TIMER_" + reason)

def digest(raw: bytes) -> str:
    return sha256(raw).hexdigest()

def canonical(value: dict) -> bytes:
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()

def secure_file(path: Path, *, uid: int, mode: int | None = None, limit: int = 262144) -> bytes:
    need(path.is_absolute() and not path.is_symlink(),"FILE_PATH_UNTRUSTED")
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        st=os.fstat(fd)
        need(stat.S_ISREG(st.st_mode) and st.st_uid==uid and st.st_nlink==1
             and st.st_size <= limit and not st.st_mode & 0o002
             and (mode is None or stat.S_IMODE(st.st_mode)==mode),
             "FILE_METADATA_UNTRUSTED:"+path.name)
        data=os.read(fd,limit+1)
        need(len(data)==st.st_size,"FILE_CHANGED_DURING_READ")
        return data
    finally:os.close(fd)

def jsonfile(path: Path, *, uid: int, mode: int | None = None):
    return json.loads(secure_file(path,uid=uid,mode=mode))

def checked(*args: str, timeout: int = 40, owner: bool = False) -> str:
    argv=(["/usr/sbin/runuser","-u","al","--"] if owner else [])+list(args)
    result=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
    need(result.returncode==0,"NATIVE_READBACK_FAILED:"+Path(args[0]).name)
    return result.stdout.strip()

def systemd_status(unit: str, action: str) -> str:
    need(unit in (SCOPED_TIMER,OLD_TIMER,OLD_SERVICE,WATCHDOG) and
         action in ("is-active","is-enabled"),"SYSTEMD_READ_SCOPE_INVALID")
    r=subprocess.run(["/usr/bin/systemctl",action,unit],capture_output=True,text=True,timeout=15)
    need(r.returncode in (0,1,3),"SYSTEMD_STATUS_UNAVAILABLE")
    return r.stdout.strip()

def protected_containers():
    """Only independently healthy required services must be running."""
    rows={}
    for name in PROTECTED_CONTAINERS:
        r=subprocess.run(["/usr/bin/docker","inspect",name],
                         capture_output=True,text=True,timeout=25)
        need(r.returncode==0,"PROTECTED_CONTAINER_NOT_FOUND:"+name)
        item=json.loads(r.stdout)[0]
        need(item["State"]["Running"] is True,"PROTECTED_CONTAINER_NOT_RUNNING:"+name)
        if name=="jason-runtime":
            need(item["State"].get("Health",{}).get("Status")=="healthy",
                 "PROTECTED_TICKET_CORE_NOT_HEALTHY")
        rows[name]=(item["Id"],item["Image"],item["State"]["StartedAt"])
    return rows


def shadow_identity():
    """Snapshot the shadow as found; never infer that OOM exit is healthy.

    The Owner-signed release pins exactly the stopped state, ID, image,
    OOM marker, exit code, and start/finish timestamps. This recovery
    neither starts nor removes the shadow gateway.
    """
    result=subprocess.run(["/usr/bin/docker","inspect",SHADOW],
                          capture_output=True,text=True,timeout=25)
    need(result.returncode==0,"SHADOW_CONTAINER_INVENTORY_UNAVAILABLE")
    doc=json.loads(result.stdout)
    need(isinstance(doc,list) and len(doc)==1 and isinstance(doc[0],dict),
         "SHADOW_CONTAINER_IDENTITY_UNTRUSTED")
    item=doc[0]
    state=item.get("State",{})
    need(isinstance(state,dict) and
         isinstance(item.get("Id"),str) and
         isinstance(item.get("Image"),str) and
         state.get("Status") in ("running","exited","created") and
         type(state.get("OOMKilled")) is bool and
         type(state.get("ExitCode")) is int and
         isinstance(state.get("StartedAt"),str) and
         isinstance(state.get("FinishedAt"),str),
         "SHADOW_CONTAINER_STATE_INVALID")
    return {
        "id":item["Id"],"image":item["Image"],
        "status":state["Status"],"running":state.get("Running"),
        "exit_code":state["ExitCode"],"oom_killed":state["OOMKilled"],
        "started_at":state["StartedAt"],"finished_at":state["FinishedAt"],
    }


def packet(planfile: Path):
    need(os.geteuid()==0 and sys.flags.isolated==1,
         "ISOLATED_ROOT_ONLY")
    need(os.environ.get("SUDO_USER")=="al" and pwd.getpwnam("al").pw_uid==1000,
         "INTERACTIVE_LOCAL_OWNER_REQUIRED")
    plan=jsonfile(planfile,uid=1000,mode=0o400)
    need(set(plan)=={
        "schema_version","action","candidate_sha","source_sha","rollback_sha",
        "scope_sha256","root_sha256","freeze_sha256","old_timer_unit_sha256",
        "scoped_timer_unit_sha256","owner_consents","production_mutations",
        "standing_authority","no_runtime_or_mcp_restart","later_stages_authorized",
        "shadow_identity",
    },"EXACT_PACKET_SCHEMA")
    need(plan["schema_version"]=="1.0" and plan["action"]==ACTION
         and plan["candidate_sha"]==plan["source_sha"] and
         SHA40.fullmatch(plan["source_sha"]) and SHA40.fullmatch(plan["rollback_sha"])
         and all(SHA64.fullmatch(plan[x]) for x in (
             "scope_sha256","root_sha256","freeze_sha256",
             "old_timer_unit_sha256","scoped_timer_unit_sha256"))
         and plan["owner_consents"]==1 and plan["standing_authority"] is False
         and plan["later_stages_authorized"] is False
         and plan["no_runtime_or_mcp_restart"] is True
         and isinstance(plan["shadow_identity"],dict)
         and set(plan["shadow_identity"])=={
             "id","image","status","running","exit_code","oom_killed",
             "started_at","finished_at",
         }
         and plan["production_mutations"]==[
             "disable_completed_bootstrap_recovery_timer",
             "reset_failed_completed_bootstrap_service",
             "restart_watchdog_oneshot",
             "reinstall_exact_timer_if_postflight_fails",
         ],"EXACT_ACTION_SCOPE_INVALID")
    rest=dict(plan);expected_scope=rest.pop("scope_sha256")
    need(digest(canonical(rest))==expected_scope,"SCOPE_HASH_INVALID")
    art=ARTIFACTS/("pmv4-bootstrap-timer-"+plan["source_sha"])
    need(planfile==art/"root-release-plan.json","ARTIFACT_LOCATION_INVALID")
    pinned=STAGE/("jason-pmv4-bootstrap-timer-"+plan["source_sha"][:12])/"root.py"
    need(Path(__file__).resolve()==pinned and not pinned.is_symlink()
         and pinned.lstat().st_uid==0 and pinned.lstat().st_gid==0
         and stat.S_IMODE(pinned.lstat().st_mode)==0o400
         and pinned.parent.lstat().st_uid==0
         and stat.S_IMODE(pinned.parent.lstat().st_mode)==0o700
         and digest(secure_file(pinned,uid=0,mode=0o400))==plan["root_sha256"],
         "UNPINNED_ROOT_SOURCE")
    return plan

def protected_ci(source: str) -> None:
    current=checked("/usr/bin/git","-C","/home/al/.local/lib/jason/engineering-source-repo",
                    "ls-remote","origin","refs/heads/main",timeout=25,owner=True).split()
    need(bool(current) and current[0]==source,"PROTECTED_MAIN_MOVED")
    branch=json.loads(checked("/usr/bin/gh","api",
                              "repos/al-teamaot-com/jason/branches/main",owner=True))
    need(branch.get("protected") is True and branch.get("commit",{}).get("sha")==source,
         "PROTECTED_BRANCH_MISMATCH")
    required=json.loads(checked("/usr/bin/gh","api",
                 "repos/al-teamaot-com/jason/branches/main/protection/required_status_checks",owner=True))
    check_names=[c.get("context") for c in required.get("checks",[])]
    need(required.get("strict") is True and len(check_names)>=5
         and all(isinstance(x,str) for x in check_names),"PROTECTED_CHECK_POLICY_CHANGED")
    seen=json.loads(checked("/usr/bin/gh","api",
         "repos/al-teamaot-com/jason/commits/"+source+"/check-runs?per_page=100",owner=True)).get("check_runs",[])
    for name in check_names:
        rows=[x for x in seen if x.get("name")==name and x.get("head_sha")==source]
        rows.sort(key=lambda z:(z.get("completed_at") or "",z.get("id") or 0),reverse=True)
        need(bool(rows) and rows[0].get("status")=="completed"
             and rows[0].get("conclusion")=="success","REQUIRED_CHECK_NOT_GREEN:"+name)

def observed_drift() -> dict:
    probe=subprocess.run([
        "/usr/bin/python3",str(HOST_LKG/"tools/production_drift_guard.py"),
        "--config",str(ROOT_POLICY)],capture_output=True,text=True,timeout=55)
    need(probe.returncode in (0,2) and len(probe.stdout)<131072,
         "NATIVE_DRIFT_READBACK_FAILED")
    result=json.loads(probe.stdout)
    need(result.get("schema_version")=="1.0" and
         isinstance(result.get("problems"),list),"NATIVE_DRIFT_SCHEMA_INVALID")
    return result

def completed_install() -> None:
    original=jsonfile(INSTALL_PLAN,uid=1000,mode=0o400)
    need(original.get("source_sha")==SOURCE_SHA and
         original.get("rollback_source_sha")==HOST_LKG.resolve(strict=True).name,
         "ORIGINAL_INSTALL_SOURCE_CHANGED")
    trust=jsonfile(BOOTSTRAP_TRUST,uid=0,mode=0o600)
    need(trust.get("protected_source_sha")==SOURCE_SHA and
         trust.get("install_scope_sha256")==original.get("installation_scope_sha256") and
         trust.get("plan_sha256")==original.get("install_plan_sha256"),
         "ORIGINAL_ROOT_TRUST_SOURCE_CHANGED")
    installed_code=Path("/usr/local/lib/jason/catalog-root-bootstrap/tools/catalog_scoped_root_install_native.py")
    need(digest(secure_file(installed_code,uid=0,mode=0o555,limit=400000)) ==
         trust.get("bootstrap_sha256"), "ROOT_BOOTSTRAP_NATIVE_SOURCE_CHANGED")
    policy=jsonfile(INSTALLED_POLICY,uid=0,mode=0o600)
    need(policy==original.get("root_policy_after_separate_approval"),
         "INSTALLED_ROOT_POLICY_NOT_ORIGINAL")
    audit=ROOT_JOURNALS/("release-"+SOURCE_SHA[:16]+".json")
    receipt=jsonfile(audit,uid=0,mode=0o600)
    need(receipt.get("schema_version")=="1.0" and
         receipt.get("action")=="catalog_root_install_only_v1" and
         receipt.get("source_sha")==SOURCE_SHA and
         receipt.get("plan_sha256")==original["install_plan_sha256"] and
         receipt.get("scope_sha256")==original["installation_scope_sha256"] and
         receipt.get("rollback_source_sha")==original.get("rollback_source_sha") and
         isinstance(receipt.get("approval_id"),str) and
         re.fullmatch("catalog-root-owner-[0-9a-f]{32}",receipt["approval_id"]) and
         isinstance(receipt.get("verified_owner_oid"),str) and receipt["verified_owner_oid"] and
         isinstance(receipt.get("verified_token_sha256"),str) and
         SHA64.fullmatch(receipt["verified_token_sha256"]) and
         receipt.get("status") in ("exact_catalog_root_install_verified",
                                   "root_install_verified_freeze_unchanged"),
         "ORIGINAL_ROOT_INSTALL_NOT_ACCEPTED")
    need(digest(secure_file(FREEZE,uid=1000,mode=0o600))==
         original.get("freeze_sha256"),"PROTECTED_FREEZE_CHANGED")

def verify(plan: dict, *, strict_drift: bool = True):
    protected_ci(plan["source_sha"])
    need(HOST_LKG.resolve(strict=True).name==plan["rollback_sha"],
         "PROTECTED_LKG_CHANGED")
    need(digest(secure_file(FREEZE,uid=1000,mode=0o600))==
         plan["freeze_sha256"],"PROTECTED_FREEZE_CHANGED")
    completed_install()
    for n,key in ((OLD_TIMER,"old_timer_unit_sha256"),(SCOPED_TIMER,"scoped_timer_unit_sha256")):
        source=Path("/etc/systemd/system")/n
        need(digest(secure_file(source,uid=0,mode=0o644))==plan[key],
             "TIMER_FILE_CHANGED:"+n)
    need(systemd_status(OLD_TIMER,"is-active")=="active" and
         systemd_status(OLD_TIMER,"is-enabled")=="enabled",
         "BOOTSTRAP_TIMER_NOT_ACTIVE")
    need(systemd_status(SCOPED_TIMER,"is-active")=="active" and
         systemd_status(SCOPED_TIMER,"is-enabled")=="enabled",
         "SCOPED_CATALOG_RECOVERY_NOT_ACTIVE")
    need(systemd_status(OLD_SERVICE,"is-active")=="failed",
         "STALE_BOOTSTRAP_SERVICE_NOT_FAILED")
    control=jsonfile(CONTROL,uid=1000,mode=0o600)
    breaker=control.get("circuit_breaker",{})
    need(breaker.get("state")=="open" and
         breaker.get("reason")=="continuous_production_drift_detected" and
         breaker.get("problem_kinds")==["failed_system_unit"],
         "UNRELATED_PRODUCTION_BREAKER")
    drift=observed_drift()
    kinds={(p.get("kind"),p.get("unit")) for p in drift["problems"]}
    allowed={("failed_system_unit",OLD_SERVICE),
             ("failed_system_unit",WATCHDOG)}
    need(drift.get("status")=="drift_detected" and
         ("failed_system_unit",OLD_SERVICE) in kinds and
         kinds.issubset(allowed),"UNRELATED_PRODUCTION_DRIFT")
    need(shadow_identity()==plan["shadow_identity"],
         "REVIEWED_SHADOW_STATE_CHANGED")
    return protected_containers()

@contextmanager
def native_locks():
    handles=[]
    try:
        for path,expected_uid,expected_mode in (
            (RELEASE_LOCK,1000,None),(PMV4_LOCK,0,0o600)):
            need(not path.is_symlink(),"HOST_LOCK_SYMLINK")
            fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW)
            st=os.fstat(fd)
            need(stat.S_ISREG(st.st_mode) and st.st_uid==expected_uid
                 and not st.st_mode & 0o002
                 and (expected_mode is None or
                      stat.S_IMODE(st.st_mode)==expected_mode),
                 "HOST_LOCK_METADATA_CHANGED")
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            handles.append(fd)
        yield
    finally:
        for fd in reversed(handles):
            fcntl.flock(fd,fcntl.LOCK_UN)
            os.close(fd)

def authenticated_owner(plan) -> str:
    need(digest(secure_file(OWNER_HELPER,uid=0,mode=0o555,limit=50000))==
         OWNER_HELPER_SHA,"TRUSTED_ENTRA_OWNER_VERIFIER_CHANGED")
    spec=importlib.util.spec_from_file_location("pmv4_bootstrap_owner_native",OWNER_HELPER)
    need(spec is not None and spec.loader is not None,"ENTRA_OWNER_VERIFIER_UNAVAILABLE")
    signer=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(signer)
    endpoint="https://login.microsoftonline.com/"+signer.TENANT+"/oauth2/v2.0/"
    token=signer._form(endpoint+"devicecode",
                       {"client_id":signer.CLIENT_ID,"scope":signer.SCOPE})
    need(all(isinstance(token.get(k),str) for k in (
         "device_code","user_code","verification_uri")),"ENTRA_DEVICE_CODE_UNAVAILABLE")
    print("EXACT_ACTION="+ACTION,flush=True)
    print("EXACT_SOURCE_SHA="+plan["source_sha"],flush=True)
    print("EXACT_SCOPE_SHA256="+plan["scope_sha256"],flush=True)
    print("MUTATIONS=disable-one-completed-timer,reset-two-failed-states,watchdog-oneshot",flush=True)
    print("NO_CONTAINERS_OR_FREEZE_CHANGE=true; NO_BREAKER_OVERRIDE=true",flush=True)
    print("BROWSER_VERIFICATION_URL="+token["verification_uri"],flush=True)
    print("SIGN_IN_CODE="+token["user_code"],flush=True)
    deadline=time.monotonic()+min(600,int(token.get("expires_in",600)))
    interval=max(5,int(token.get("interval",5)))
    while time.monotonic()<deadline:
        response=signer._form(endpoint+"token",{
            "grant_type":"urn:ietf:params:oauth:grant-type:device_code",
            "client_id":signer.CLIENT_ID,"device_code":token["device_code"]})
        if isinstance(response.get("access_token"),str):
            oid=signer.jwt_owner(response["access_token"])
            response=None
            need(input("Type "+CONFIRM+" to approve ONLY this timer repair: ").strip()==CONFIRM,
                 "EXACT_OWNER_CONFIRMATION_MISSING")
            return str(oid)
        reason=response.get("error")
        if reason=="slow_down":interval=min(interval+5,20)
        elif reason!="authorization_pending":need(False,"ENTRA_OWNER_AUTHENTICATION_DENIED")
        time.sleep(interval)
    need(False,"ENTRA_OWNER_AUTH_EXPIRED")

def audit_file(path: Path, obj: dict):
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"wb") as out:
        out.write(canonical(obj));out.flush();os.fsync(out.fileno())

def native_action(*argv: str, timeout: int = 60):
    r=subprocess.run(["/usr/bin/systemctl",*argv],capture_output=True,text=True,timeout=timeout)
    need(r.returncode==0,"NATIVE_SYSTEMD_ACTION_FAILED:"+argv[0])

def execute(planpath: Path):
    plan=packet(planpath)
    before=verify(plan)
    need(os.isatty(0) and os.isatty(1),"LOCAL_OWNER_TTY_REQUIRED")
    oid=authenticated_owner(plan)
    with native_locks():
        again=packet(planpath)
        need(again==plan,"APPROVAL_PLAN_CHANGED")
        need(verify(plan)==before,"PROTECTED_CONTAINERS_CHANGED_PREMUTATION")
        AUDIT.mkdir(mode=0o700,parents=True,exist_ok=True)
        need(AUDIT.lstat().st_uid==0 and stat.S_IMODE(AUDIT.lstat().st_mode)==0o700,
             "AUDIT_ROOT_DIRECTORY_UNTRUSTED")
        attempt=AUDIT/(plan["source_sha"]+"-attempt.json")
        accepted=AUDIT/(plan["source_sha"]+"-accepted.json")
        need(not attempt.exists() and not attempt.is_symlink()
             and not accepted.exists() and not accepted.is_symlink(),
             "OWNER_ACTION_ALREADY_CONSUMED")
        approval="pmv4-bootstrap-"+uuid4().hex
        audit_file(attempt,{
          "schema_version":"1.0","status":"owner_consumed_before_mutation",
          "action":ACTION,"owner_oid":oid,"approval_id":approval,
          "source_sha":plan["source_sha"],"scope_sha256":plan["scope_sha256"],
          "freeze_sha256":plan["freeze_sha256"],
          "timestamp":datetime.now(timezone.utc).isoformat()})
        disabled=False
        try:
            native_action("disable","--now",OLD_TIMER)
            disabled=True
            need(systemd_status(OLD_TIMER,"is-active")!="active" and
                 systemd_status(OLD_TIMER,"is-enabled")=="disabled",
                 "OLD_BOOTSTRAP_TIMER_NOT_DISABLED")
            native_action("reset-failed",OLD_SERVICE,WATCHDOG)
            native_action("start",WATCHDOG,timeout=100)
            live=observed_drift()
            need(live.get("status")=="pass" and live["problems"]==[],
                 "NATIVE_WATCHDOG_POSTFLIGHT_NOT_CLEAN")
            need(systemd_status(SCOPED_TIMER,"is-active")=="active" and
                 systemd_status(SCOPED_TIMER,"is-enabled")=="enabled",
                 "INDEPENDENT_CATALOG_RECOVERY_CHANGED")
            need(protected_containers()==before and
                 shadow_identity()==plan["shadow_identity"] and
                 digest(secure_file(FREEZE,uid=1000,mode=0o600))==
                 plan["freeze_sha256"] and
                 HOST_LKG.resolve(strict=True).name==plan["rollback_sha"],
                 "PROTECTED_RUNTIME_OR_FREEZE_CHANGED")
            audit_file(accepted,{
                "schema_version":"1.0","status":"completed_bootstrap_timer_superseded",
                "action":ACTION,"source_sha":plan["source_sha"],
                "scope_sha256":plan["scope_sha256"],"approval_id":approval,
                "drift":"pass","breaker_force_closed":False,
                "protected_containers_restarted":0,"production_freeze_changed":False,
                "scoped_recovery_timer_active":True,
                "completed_at":datetime.now(timezone.utc).isoformat()})
        except BaseException:
            restored=False
            if disabled:
                try:
                    native_action("enable","--now",OLD_TIMER)
                    restored=(systemd_status(OLD_TIMER,"is-active")=="active" and
                              systemd_status(OLD_TIMER,"is-enabled")=="enabled"
                              and protected_containers()==before)
                except Exception:
                    restored=False
            audit_file(AUDIT/(plan["source_sha"]+"-rollback.json"),{
                "schema_version":"1.0","status":"rolled_back" if restored else "unverified",
                "scope_sha256":plan["scope_sha256"],"timer_rollback_verified":restored})
            raise
    print("PMV4_COMPLETED_BOOTSTRAP_RECOVERY_TIMER_SUPERSEDED=PASS",flush=True)
    print("NATIVE_DRIFT=PASS; BREAKER_NOT_FORCED_CLOSED=true",flush=True)
    print("TICKET_CORE_MCP_FREEZE_UNCHANGED=true",flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--plan",type=Path,required=True)
    m=p.add_mutually_exclusive_group(required=True)
    m.add_argument("--check-only",action="store_true")
    m.add_argument("--execute",action="store_true")
    opts=p.parse_args()
    try:
        if opts.check_only:
            plan=packet(opts.plan)
            verify(plan)
            print("PMV4_BOOTSTRAP_TIMER_EXACT_ROOT_PREFLIGHT=PASS")
            print("EXACT_SCOPE_SHA256="+plan["scope_sha256"])
            print("OWNER_APPROVAL_USED=false; PRODUCTION_MUTATIONS=false")
        else:execute(opts.plan)
    except BaseException as exc:
        print("BOOTSTRAP_TIMER_DENIED="+type(exc).__name__+":"+str(exc)[:180],
              file=sys.stderr,flush=True)
        raise SystemExit(2)
if __name__=="__main__":
    main()
