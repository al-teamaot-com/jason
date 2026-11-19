#!/usr/bin/env python3
"""One-use, owner-authenticated catalog root trusted-runner guard correction.

Only changes: exact root-owned host worker, and its two-field trust policy.
Never changes images, PMv4, runbook, freeze, provider records or systemd units.
"""
from __future__ import annotations
from datetime import datetime, timezone
from contextlib import contextmanager
from hashlib import sha256
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
import tempfile
import time
from uuid import uuid4
import argparse

ACTION = "catalog-root-trusted-original-runner-guard-repair-once-v1"
CONFIRM = "APPROVE-EXACT-CATALOG-ROOT-RUNNER-TRUST-REPAIR-ONLY"
SELF = Path("/root/catalog-root-trusted-runner-guard-repair-once.py")
WORKER = Path("/usr/local/lib/jason/release_host_reconcile_worker.py")
POLICY = Path("/etc/jason-owner-release/catalog-scoped-promotion-installed.json")
BUNDLE = Path("/usr/local/lib/jason/catalog-scoped-promotion")
ROOT_SIGNER = Path("/usr/local/lib/jason/owner_signer_recovery.py")
FREEZE = Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
DRIFT = Path("/var/lib/jason/openclaw/release-manager/protected-readback/production-drift.json")
CONTROL = Path("/var/lib/jason/openclaw/release-manager/protected-readback/production-control-state.json")
GIT = Path("/home/al/.local/lib/jason/engineering-source-repo")
NATIVE_LOCK = Path("/var/lib/jason/openclaw/release-manager/production-transaction.lock")
PMV4_LOCK = Path("/var/lib/jason/pmv4-shadow/control/host-mutation.lock")
LEDGER = Path("/var/lib/jason-catalog-scoped-promotion/trusted-runner-guard-repair-oneuse")
OWNER_SIGNER_SHA256 = "24d3632a4b0aa60851a1c82ccb15539eb823dd26afa5a1a2cc8c7afc54d72153"
OLD_WORKER_SHA256 = "b1d5d569287af795cc67ba2dd6506cb7e2046a9b7bf4e3bf65854bfcec98914d"
OLD_POLICY_SHA256 = "de613cdf641bd8c11dc42224ca4cf8ce5c70236045218d142c3c2f2d9b7672d9"
OLD_SOURCE_SHA = "05ed0e0be7e0c945a69995cd596d3eb730a094f9"
FREEZE_SHA256 = "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
ORIGINAL_ROOT_RUNNER_SHA256 = "b194084a9a54fe024ae89784e2e75d54a26e1369ed65d824abed4ce958f58edf"
ORIGINAL_ROOT_SHA = "01ba71c54d9dd0391734b16a92d0b292fc457ae9"
OWNER = 1000  # pinned host operator UID, verified at privileged execution
SHA40 = re.compile(r"^[0-9a-f]{40}$")
PROTECTED = ("jason-pmv4-ticket-core","jason-pmv4-shadow-gateway",
             "jason-teams-gateway","openbao","jason-runtime","jason-mcp-pilot")

def fail(reason):
    raise PermissionError("CATALOG_ROOT_TRUSTED_RUNNER_REPAIR_DENIED_" + reason)

def canonical(data):
    return (json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)+"\n").encode()

def digest(raw):
    return sha256(raw).hexdigest()

def read(path, *, uid=0, mode=0o600, limit=650000):
    fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
    try:
        st=os.fstat(fd)
        if (path.is_symlink() or not stat.S_ISREG(st.st_mode)
                or st.st_uid!=uid or stat.S_IMODE(st.st_mode)!=mode
                or st.st_nlink!=1 or not 0<st.st_size<=limit):
            fail("FILE_TRUST_"+path.name)
        data=os.read(fd,limit+1)
        if len(data)!=st.st_size:fail("FILE_RACE_"+path.name)
        return data
    finally:
        os.close(fd)

def run(*argv, owner=False, timeout=40):
    command=(("runuser","-u","al","--")+argv) if owner else argv
    p=subprocess.run(command,capture_output=True,timeout=timeout)
    if p.returncode:fail("EXACT_COMMAND_"+str(argv[0]).replace("/","_"))
    return p.stdout

def github_ci(sha):
    head=json.loads(run("gh","api","repos/al-teamaot-com/jason/branches/main",owner=True))
    if (head.get("name")!="main" or head.get("protected") is not True
            or (head.get("commit") or {}).get("sha")!=sha):
        fail("PROTECTED_MAIN_CHANGED")
    rules=json.loads(run("gh","api","repos/al-teamaot-com/jason/branches/main/protection/required_status_checks",owner=True))
    checks=rules.get("checks")
    if rules.get("strict") is not True or not isinstance(checks,list) or len(checks)<5:
        fail("PROTECTED_CI_POLICY_MISSING")
    rows=json.loads(run("gh","api","repos/al-teamaot-com/jason/commits/"+sha+"/check-runs?per_page=100",owner=True)).get("check_runs")
    if not isinstance(rows,list):fail("PROTECTED_CI_READBACK_UNAVAILABLE")
    for item in checks:
        name=item.get("context")
        hits=sorted((r for r in rows if r.get("name")==name and r.get("head_sha")==sha),
                    key=lambda r:(r.get("completed_at") or "",int(r.get("id") or 0)),reverse=True)
        if not hits or hits[0].get("conclusion")!="success" or hits[0].get("status")!="completed":
            fail("PROTECTED_CI_NOT_GREEN_"+str(name))

def protected_snapshot():
    data=json.loads(run("docker","inspect",*PROTECTED,timeout=35))
    if len(data)!=len(PROTECTED):fail("PROTECTED_CONTAINERS_INCOMPLETE")
    result={}
    for c in data:
        n=c["Name"].lstrip("/")
        if n not in PROTECTED or c["State"]["Running"] is not True:fail("PROTECTED_CONTAINER_UNHEALTHY")
        health=c["State"].get("Health")
        if n in ("jason-pmv4-ticket-core","jason-pmv4-shadow-gateway"):
            if not health or health.get("Status")!="healthy":fail("PMV4_INDEPENDENT_HEALTH")
        result[n]=(c["Id"],c["Image"],c["State"]["StartedAt"])
    return result

def preflight():
    if os.geteuid()!=0 or os.environ.get("SUDO_USER")!="al" or not os.isatty(0):
        fail("INTERACTIVE_HOST_OWNER_REQUIRED")
    if pwd.getpwnam("al").pw_uid!=OWNER:
        fail("PINNED_AL_USER_ID_CHANGED")
    if (SELF.is_symlink() or SELF.lstat().st_uid!=0 or
            stat.S_IMODE(SELF.stat().st_mode)!=0o500 or SELF.stat().st_nlink!=1):
        fail("ROOT_PINNED_ENTRYPOINT_REQUIRED")
    if (LEDGER.exists() or LEDGER.is_symlink()):fail("ONEUSE_LEDGER_ALREADY_PRESENT")
    if digest(read(ROOT_SIGNER,uid=0,mode=0o555,limit=50000))!=OWNER_SIGNER_SHA256:
        fail("OWNER_VERIFIER_CHANGED")
    previous=read(WORKER,uid=0,mode=0o755)
    oldpolicy=read(POLICY,uid=0,mode=0o600,limit=16000)
    if digest(previous)!=OLD_WORKER_SHA256 or digest(oldpolicy)!=OLD_POLICY_SHA256:
        fail("PREVIOUS_AUTHENTICATED_ROOT_REBIND_CHANGED")
    old=json.loads(oldpolicy)
    if old.get("source_sha")!=OLD_SOURCE_SHA or old.get("root_worker_sha256")!=OLD_WORKER_SHA256:
        fail("EXACT_ROOT_POLICY_MISMATCH")
    previously=Path("/var/lib/jason-catalog-scoped-promotion/rebind-ledger")
    original_receipt=json.loads(read(previously/"verified.json",uid=0,mode=0o600,limit=8192))
    consumed=json.loads(read(previously/"owner-intent.json",uid=0,mode=0o600,limit=8192))
    if (original_receipt.get("status")!="exact_catalog_root_rebind_verified"
            or original_receipt.get("source_sha")!=OLD_SOURCE_SHA
            or consumed.get("status")!="consumed_before_mutation"
            or consumed.get("source_sha")!=OLD_SOURCE_SHA
            or not consumed.get("authenticated_owner_oid")
            or consumed.get("approval_id")!=original_receipt.get("approval_id")):
        fail("PREVIOUS_ROOT_REBIND_OWNER_EVIDENCE_INVALID")
    if digest(read(FREEZE,uid=OWNER,mode=0o600,limit=4096))!=FREEZE_SHA256:
        fail("FREEZE_CHANGED")
    for timer,desired in (("jason-catalog-scoped-recovery.timer","active"),
                          ("jason-catalog-root-bootstrap-recovery.timer","inactive")):
        r=subprocess.run(("systemctl","is-active",timer),capture_output=True,text=True,timeout=15)
        if r.stdout.strip()!=desired:fail("RECOVERY_TIMER_STATE_"+timer)
    d=json.loads(read(DRIFT,uid=OWNER,mode=0o600,limit=131072))
    c=json.loads(read(CONTROL,uid=OWNER,mode=0o600,limit=131072))
    if d.get("status")!="pass" or d.get("problems")!=[] or (c.get("circuit_breaker") or {}).get("state")!="closed":
        fail("NATIVE_PRODUCTION_CONTROL_NOT_CLOSED")
    source=run("git","-C",str(GIT),"ls-remote","origin","refs/heads/main",owner=True).decode().split()[0]
    if not SHA40.fullmatch(source):fail("PROTECTED_MAIN_SHA_INVALID")
    github_ci(source)
    if digest(run("git","-C",str(GIT),"show",ORIGINAL_ROOT_SHA+":tools/release_manager_host_runner.py",owner=True))!=ORIGINAL_ROOT_RUNNER_SHA256:
        fail("HISTORICAL_ROOT_RUNNER_SOURCE_CHANGED")
    if digest(read(BUNDLE/"tools/release_manager_host_runner.py",uid=0,mode=0o644))!=ORIGINAL_ROOT_RUNNER_SHA256:
        fail("PINNED_INSTALLED_NATIVE_RUNNER_CHANGED")
    blob=run("git","-C",str(GIT),"show",source+":tools/release_host_reconcile_worker.py",owner=True)
    expected_runner=run("git","-C",str(GIT),"show",source+":tools/catalog_root_trusted_runner_repair_once.py",owner=True)
    if digest(expected_runner)!=digest(read(SELF,uid=0,mode=0o500)):
        fail("PROTECTED_SOURCE_INSTALLER_CHANGED")
    if len(blob)>=650000 or b"CATALOG_SCOPED_PINNED_RUNNER_SHA256" not in blob:
        fail("NEW_ROOT_WORKER_NOT_EXACT_FIX")
    new=dict(old,source_sha=source,root_worker_sha256=digest(blob))
    if set(new)!=set(old) or any(new[k]!=old[k] for k in old if k not in ("source_sha","root_worker_sha256")):
        fail("ROOT_POLICY_SCOPE_EXPANDED")
    return source,previous,oldpolicy,blob,canonical(new),protected_snapshot()

@contextmanager
def exclusive_locks():
    fds=[]
    try:
        for path,uid,mode in ((NATIVE_LOCK,OWNER,None),(PMV4_LOCK,0,0o600)):
            fd=os.open(path,os.O_RDWR|getattr(os,"O_NOFOLLOW",0))
            st=os.fstat(fd)
            if path.is_symlink() or st.st_uid!=uid or not stat.S_ISREG(st.st_mode) or st.st_mode&0o002 or (mode is not None and stat.S_IMODE(st.st_mode)!=mode):
                fail("RELEASE_LOCK_UNTRUSTED")
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:fail("PROTECTED_RELEASE_IN_PROGRESS")
            fds.append(fd)
        yield
    finally:
        for fd in reversed(fds):
            fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)

def owner_auth(source,new_sha):
    spec=importlib.util.spec_from_file_location("catalog_existing_exact_owner_signer",ROOT_SIGNER)
    if spec is None or spec.loader is None:fail("OWNER_SIGNER_LOAD")
    helper=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    endpoint="https://login.microsoftonline.com/"+helper.TENANT+"/oauth2/v2.0/"
    challenge=helper._form(endpoint+"devicecode",{"client_id":helper.CLIENT_ID,"scope":helper.SCOPE})
    if not all(isinstance(challenge.get(k),str) for k in ("device_code","user_code","verification_uri")):
        fail("DEVICE_CHALLENGE_INVALID")
    print("EXACT_ACTION="+ACTION,flush=True)
    print("SOURCE_SHA="+source,flush=True)
    print("OLD_ROOT_WORKER_SHA256="+OLD_WORKER_SHA256,flush=True)
    print("NEW_ROOT_WORKER_SHA256="+new_sha,flush=True)
    print("IMAGE_PROMOTION_APPROVED=false; PROVIDER_WRITES_APPROVED=false",flush=True)
    print("BROWSER_VERIFICATION_URL="+challenge["verification_uri"],flush=True)
    print("SIGN_IN_CODE="+challenge["user_code"],flush=True)
    ttl=min(int(challenge.get("expires_in",0)),600)
    if ttl<60:fail("DEVICE_CODE_TTL")
    delay=max(5,min(int(challenge.get("interval",5)),20))
    end=time.monotonic()+ttl
    while time.monotonic()<end:
        time.sleep(delay)
        result=helper._form(endpoint+"token",{
            "grant_type":"urn:ietf:params:oauth:grant-type:device_code",
            "client_id":helper.CLIENT_ID,"device_code":challenge["device_code"]})
        if isinstance(result.get("access_token"),str):
            oid=helper.jwt_owner(result["access_token"])
            result=None
            if input("Type "+CONFIRM+" to approve ONLY this root worker trust fix: ").strip()!=CONFIRM:
                fail("EXACT_OWNER_CONSENT_MISSING")
            return oid
        if result.get("error")=="slow_down":delay=min(delay+5,20)
        elif result.get("error")!="authorization_pending":fail("ENTRA_OWNER_AUTH_DENIED")
    fail("ENTRA_OWNER_AUTH_EXPIRED")

def new_record(name,data):
    p=LEDGER/name
    fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,"O_NOFOLLOW",0),0o600)
    with os.fdopen(fd,"wb") as f:
        f.write(data);f.flush();os.fsync(f.fileno())

def atomic_replace(path,data,mode):
    fd,tmp=tempfile.mkstemp(prefix=".catalog-runner-guard-",dir=path.parent)
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,"wb") as f:
            f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def exact_trusted_loader(source):
    spec=importlib.util.spec_from_file_location("verify_catalog_trusted_worker_after_repair",WORKER)
    if spec is None or spec.loader is None:fail("NEW_WORKER_MODULE_UNAVAILABLE")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    sys.dont_write_bytecode=True
    trusted=module._trusted_catalog_scoped_promotion_module(source)
    if not callable(getattr(trusted,"execute_native_catalog_scoped_request",None)):
        fail("TRUSTED_CATALOG_ROOT_HANDLER_MISSING")

def execute():
    src,oldworker,oldpolicy,newworker,newpolicy,before=preflight()
    approval=owner_auth(src,digest(newworker))
    with exclusive_locks():
        src2,before_worker,before_policy,worker2,policy2,containers2=preflight()
        if ((src2,before_worker,before_policy,worker2,policy2,containers2)
                !=(src,oldworker,oldpolicy,newworker,newpolicy,before)):
            fail("EXACT_SCOPE_CHANGED_DURING_AUTHENTICATION")
        LEDGER.mkdir(mode=0o700)
        rid="catalog-trusted-runner-"+uuid4().hex
        new_record("previous-worker.bin",oldworker)
        new_record("previous-policy.bin",oldpolicy)
        new_record("owner-intent.json",canonical({
            "schema":"1.0","action":ACTION,"approval_id":rid,"owner_oid":approval,
            "approved_scope":{"old_worker_sha256":digest(oldworker),
                "new_worker_sha256":digest(newworker),
                "old_policy_sha256":digest(oldpolicy),
                "new_policy_sha256":digest(newpolicy),"freeze_sha256":FREEZE_SHA256,
                "source_sha":src},
            "created_at":datetime.now(timezone.utc).isoformat(),
            "status":"consumed_before_mutation"}))
        worker_written=False
        policy_written=False
        try:
            atomic_replace(WORKER,newworker,0o755)
            worker_written=True
            atomic_replace(POLICY,newpolicy,0o600)
            policy_written=True
            if read(WORKER,uid=0,mode=0o755)!=newworker or read(POLICY,uid=0,mode=0o600,limit=16000)!=newpolicy:
                fail("AFTER_WRITE_READBACK_DRIFT")
            exact_trusted_loader(src)
            if protected_snapshot()!=before:fail("PMV4_OR_CATALOG_CONTAINER_CHANGED")
            if digest(read(FREEZE,uid=OWNER,mode=0o600,limit=4096))!=FREEZE_SHA256:
                fail("FREEZE_CHANGED")
            if run("git","-C",str(GIT),"ls-remote","origin","refs/heads/main",owner=True).decode().split()[0]!=src:
                fail("PROTECTED_MAIN_CHANGED_DURING_ROOT_REPAIR")
            new_record("verified.json",canonical({
                "status":"exact_trusted_root_runner_guard_verified","action":ACTION,
                "approval_id":rid,"source_sha":src,"worker_sha256":digest(newworker),
                "root_policy_sha256":digest(newpolicy),"freeze_unchanged":True,
                "container_images_changed":False,"provider_writes":False,
                "owner_approval_consumed":True}))
            print("CATALOG_TRUSTED_ROOT_RUNNER_GUARD_VERIFIED="+rid,flush=True)
        except BaseException:
            good=True
            try:
                if policy_written:
                    if read(POLICY,uid=0,mode=0o600,limit=16000)!=newpolicy:
                        fail("UNRECOGNIZED_POLICY_DRIFT_DO_NOT_ROLL_BACK")
                    atomic_replace(POLICY,oldpolicy,0o600)
                if worker_written:
                    if read(WORKER,uid=0,mode=0o755)!=newworker:
                        fail("UNRECOGNIZED_WORKER_DRIFT_DO_NOT_ROLL_BACK")
                    atomic_replace(WORKER,oldworker,0o755)
                if read(WORKER,uid=0,mode=0o755)!=oldworker or read(POLICY,uid=0,mode=0o600,limit=16000)!=oldpolicy:
                    fail("FAILED_ROLLBACK_READBACK")
            except BaseException:
                good=False
            new_record("failed.json",canonical({
                "status":"rolled_back" if good else "rollback_unverified",
                "approval_id":rid,"rollback_verified":good}))
            if not good:fail("ROLLBACK_UNVERIFIED_HUMAN_RECOVERY_REQUIRED")
            raise

def main():
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check-only",action="store_true")
    group.add_argument("--execute",action="store_true")
    args=parser.parse_args()
    if args.check_only:
        source,oldworker,oldpolicy,newworker,newpolicy,baseline=preflight()
        print(json.dumps({"status":"READONLY_TRUSTED_ROOT_REPAIR_PREFLIGHT_PASS_NOT_APPROVED",
            "action":ACTION,"source_sha":source,
            "old_worker_sha256":digest(oldworker),"new_worker_sha256":digest(newworker),
            "old_policy_sha256":digest(oldpolicy),"new_policy_sha256":digest(newpolicy),
            "protected_container_count":len(baseline),
            "production_mutations":False},sort_keys=True))
    else:
        execute()

if __name__=="__main__":
    raise SystemExit(main())
