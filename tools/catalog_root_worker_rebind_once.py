#!/usr/bin/env python3
"""One-use exact catalog root worker/projection rebind. No image or provider write."""
from __future__ import annotations
import argparse
from contextlib import ExitStack, contextmanager
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
import tempfile
import time
from uuid import uuid4

ACTION = "catalog-root-worker-projection-rebind-once-v1"
CONFIRM = "APPROVE-EXACT-CATALOG-ROOT-WORKER-REBIND-ONLY"
ROOT_SCRIPT = Path("/root/catalog-root-worker-rebind-once.py")
REPO = Path("/srv/jason/archive/engineering-worktrees/catalog-root-rebind-final-20261117")
MANAGED = Path("/home/al/.local/lib/jason/engineering-source-repo")
PLAN = Path("/srv/jason/archive/engineering-evidence/catalog-scoped-rebind-final-20261117.json")
ORIGINAL = Path("/srv/jason/archive/engineering-evidence/catalog-scoped-root-install-20261117/unsigned-root-install-plan.json")
WORKER = Path("/usr/local/lib/jason/release_host_reconcile_worker.py")
PROJECTION = Path("/usr/local/lib/jason/catalog-scoped-promotion/tools/pmv4_mcp_projection.py")
ROOT_POLICY = Path("/etc/jason-owner-release/catalog-scoped-promotion-installed.json")
OWNER_HELPER = Path("/usr/local/lib/jason/owner_signer_recovery.py")
OWNER_HELPER_SHA = "24d3632a4b0aa60851a1c82ccb15539eb823dd26afa5a1a2cc8c7afc54d72153"
FREEZE = Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
DRIFT = Path("/var/lib/jason/openclaw/release-manager/protected-readback/production-drift.json")
CONTROL = Path("/var/lib/jason/openclaw/release-manager/protected-readback/production-control-state.json")
BOOTSTRAP_TIMER = "jason-catalog-root-bootstrap-recovery.timer"
SCOPED_TIMER = "jason-catalog-scoped-recovery.timer"
RELEASE_LOCK = Path("/var/lib/jason/openclaw/release-manager/production-transaction.lock")
PMV4_LOCK = Path("/var/lib/jason/pmv4-shadow/control/host-mutation.lock")
LEDGER = Path("/var/lib/jason-catalog-scoped-promotion/rebind-ledger")
SHA = re.compile(r"^[0-9a-f]{40}$")
HEX = re.compile(r"^[0-9a-f]{64}$")
PROTECTED_NAMES = ("jason-runtime", "jason-mcp-pilot", "jason-teams-gateway",
                   "jason-pmv4-shadow-gateway", "openbao")
AL = pwd.getpwnam("al").pw_uid

def denied(why):
    raise PermissionError("CATALOG_ROOT_REBIND_DENIED_" + why)

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()

def digest(value):
    return sha256(value).hexdigest()

def file(path, *, uid=0, mode=None, limit=350000):
    if path.is_symlink():
        denied("SYMLINK_" + path.name)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid
                or info.st_nlink != 1 or info.st_size < 1 or info.st_size > limit
                or (mode is not None and stat.S_IMODE(info.st_mode) != mode)
                or info.st_mode & 0o002):
            denied("FILE_TRUST_" + path.name)
        data = os.read(fd, limit + 1)
        if len(data) != info.st_size:
            denied("FILE_CHANGED_" + path.name)
        return data
    finally:
        os.close(fd)

def run_bytes(*argv, timeout=50, uid=None):
    cmd = list(argv)
    if uid == AL:
        cmd = ["runuser", "-u", "al", "--"] + cmd
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          check=False, timeout=timeout)
    if proc.returncode:
        denied("COMMAND_FAILED_" + Path(argv[0]).name)
    return proc.stdout

def run(*argv, timeout=50, uid=None):
    return run_bytes(*argv, timeout=timeout, uid=uid).decode().strip()

def git(*args):
    return run("git", "-C", str(REPO), *args, uid=AL, timeout=45)

def systemctl(action, timer):
    return run("systemctl", action, timer, timeout=65)

def root_directory(path, mode):
    st = path.lstat()
    if (path.is_symlink() or not stat.S_ISDIR(st.st_mode)
            or st.st_uid != 0 or stat.S_IMODE(st.st_mode) != mode):
        denied("ROOT_DIRECTORY_" + path.name)

def protected_main_ci(main):
    # Read immutable branch requirements and exact check runs from GitHub, never mutable repo code.
    branch = json.loads(run("gh", "api", "repos/al-teamaot-com/jason/branches/main",
                            uid=AL, timeout=30))
    if branch.get("name") != "main" or branch.get("protected") is not True or (branch.get("commit") or {}).get("sha") != main:
        denied("PROTECTED_MAIN_CHANGED")
    rules = json.loads(run("gh", "api", "repos/al-teamaot-com/jason/branches/main/protection/required_status_checks",
                           uid=AL, timeout=30))
    checks = rules.get("checks")
    if rules.get("strict") is not True or not isinstance(checks, list) or len(checks) < 5:
        denied("PROTECTED_CHECK_POLICY_INVALID")
    observed = json.loads(run("gh", "api", "repos/al-teamaot-com/jason/commits/" + main + "/check-runs?per_page=100",
                              uid=AL, timeout=40)).get("check_runs")
    if not isinstance(observed, list):
        denied("PROTECTED_CHECK_READBACK_INVALID")
    for policy in checks:
        name = policy.get("context")
        rows = [x for x in observed if x.get("name") == name and x.get("head_sha") == main]
        rows.sort(key=lambda x: (x.get("completed_at") or "", x.get("id") or 0), reverse=True)
        if not rows or rows[0].get("status") != "completed" or rows[0].get("conclusion") != "success":
            denied("PROTECTED_CHECK_NOT_GREEN_" + str(name))
    return True

def read_plan():
    raw = file(PLAN, uid=AL, mode=0o400, limit=120000)
    p = json.loads(raw)
    claimed = p.get("plan_sha256")
    rest = {k:v for k,v in p.items() if k != "plan_sha256"}
    if not isinstance(claimed, str) or digest(canonical(rest)) != claimed:
        denied("PLAN_HASH_MISMATCH")
    if (p.get("action") != "catalog-root-worker-and-projection-rebind-v1"
            or p.get("status") != "SOURCE_ONLY_REBIND_PREP_NOT_AUTHORIZED"
            or p.get("requires_fresh_signed_exact_owner") is not True
            or p.get("provider_write_authorized") is not False
            or p.get("runtime_mcp_promotion_authorized") is not False
            or p.get("production_mutations") is not False):
        denied("PLAN_SCOPE_INVALID")
    return p

def inspect_containers():
    out = {}
    for name in PROTECTED_NAMES:
        d = json.loads(run("docker", "inspect", name, timeout=20))[0]
        if d.get("State",{}).get("Running") is not True:
            denied("PROTECTED_CONTAINER_NOT_RUNNING_" + name)
        out[name] = (d.get("Id"), d.get("Image"), d.get("State",{}).get("StartedAt"))
    return out

def preflight():
    if os.geteuid() != 0 or os.environ.get("SUDO_USER") != "al":
        denied("INTERACTIVE_SUDO_FROM_AL_REQUIRED")
    if not os.isatty(0):
        denied("INTERACTIVE_OWNER_TTY_REQUIRED")
    if (ROOT_SCRIPT.is_symlink() or ROOT_SCRIPT.lstat().st_uid != 0
            or stat.S_IMODE(ROOT_SCRIPT.stat().st_mode) != 0o500):
        denied("PINNED_ROOT_ENTRYPOINT_REQUIRED")
    root_directory(PROJECTION.parent, 0o755)
    if PROJECTION.exists() or PROJECTION.is_symlink():
        denied("PROJECTION_ALREADY_INSTALLED")
    old = json.loads(file(ORIGINAL, uid=AL, mode=0o400, limit=150000))
    plan = read_plan()
    old_root = old.get("root_policy_after_separate_approval")
    new_root = plan.get("updated_root_policy_exactly")
    if (not isinstance(old_root, dict) or not isinstance(new_root, dict)
            or old.get("install_plan_sha256") != plan.get("original_install_plan_sha256")
            or len(old.get("root_file_plan", [])) != 17
            or old.get("source_sha") != plan.get("original_install_source_sha")
            or plan.get("original_freeze_sha256") != old.get("freeze_sha256")
            or set(old_root) != set(new_root)
            or any(new_root[k] != old_root[k] for k in old_root if k not in ("source_sha","root_worker_sha256"))
            or new_root["source_sha"] != plan.get("current_protected_main_sha")):
        denied("ORIGINAL_INSTALL_BOUNDARY_CHANGED")
    old_policy = file(ROOT_POLICY, uid=0, mode=0o600, limit=12000)
    old_worker = file(WORKER, uid=0, mode=0o755, limit=300000)
    if (digest(old_policy) != plan.get("existing_root_policy_expected_sha256")
            or digest(old_worker) != plan.get("existing_root_worker_sha256")
            or digest(old_policy) != digest(canonical(old_root)+b"\n")):
        denied("CURRENT_ROOT_INSTALL_DRIFT")
    if digest(file(FREEZE, uid=AL, mode=0o600, limit=4096)) != old["freeze_sha256"]:
        denied("PRODUCTION_FREEZE_CHANGED")
    if git("ls-remote","origin","refs/heads/main").split()[0] != plan["current_protected_main_sha"]:
        denied("PROTECTED_SOURCE_CHANGED")
    if git("rev-parse","HEAD") != plan["current_protected_main_sha"]:
        denied("SOURCE_CHECKOUT_NOT_EXACT_MAIN")
    protected_main_ci(plan["current_protected_main_sha"])
    readback = json.loads(file(CONTROL, uid=AL, mode=0o600, limit=150000))
    drift = json.loads(file(DRIFT, uid=AL, mode=0o600, limit=150000))
    if readback.get("circuit_breaker",{}).get("state") != "closed" or drift.get("status") != "pass" or drift.get("problems") != []:
        denied("NATIVE_BREAKER_OR_DRIFT_NOT_HEALTHY")
    for timer in (BOOTSTRAP_TIMER,SCOPED_TIMER):
        if systemctl("is-active",timer) != "active" or systemctl("is-enabled",timer) != "enabled":
            denied("RECOVERY_TIMER_NOT_ACTIVE_" + timer)
    if LEDGER.exists():
        denied("ROOT_REBIND_ALREADY_ATTEMPTED")
    targets = plan.get("root_install_targets")
    expected = {
        str(WORKER): "tools/release_host_reconcile_worker.py",
        str(PROJECTION): "tools/pmv4_mcp_projection.py",
    }
    if (not isinstance(targets,list) or len(targets) != 2
            or {x.get("destination"):x.get("source") for x in targets if isinstance(x,dict)} != expected):
        denied("REVIEWED_TARGETS_CHANGED")
    source = {}
    for t in targets:
        blob = run_bytes("git","-C",str(REPO),"show",plan["current_protected_main_sha"]+":"+t["source"],
                   uid=AL,timeout=25)
        if digest(blob) != t.get("sha256") or len(blob) > 260000:
            denied("PROTECTED_SOURCE_BLOB_MISMATCH")
        source[t["destination"]] = blob
    if digest(canonical(new_root)+b"\n") != plan.get("updated_root_policy_sha256"):
        denied("NEW_POLICY_HASH_MISMATCH")
    if digest(source[str(WORKER)]) != new_root.get("root_worker_sha256"):
        denied("NEW_WORKER_POLICY_MISMATCH")
    return plan, old_worker, old_policy, source, inspect_containers()

@contextmanager
def hold_locks():
    fds = []
    try:
        for path, uid, mode in ((RELEASE_LOCK,AL,None),(PMV4_LOCK,0,0o600)):
            if path.is_symlink():denied("RELEASE_LOCK_SYMLINK")
            fd = os.open(path,os.O_RDWR|getattr(os,"O_NOFOLLOW",0))
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_uid != uid or st.st_mode&0o002
                    or (mode is not None and stat.S_IMODE(st.st_mode)!=mode)):
                denied("RELEASE_LOCK_UNTRUSTED")
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:denied("PROTECTED_RELEASE_BUSY")
            fds.append(fd)
        yield
    finally:
        for fd in reversed(fds):
            fcntl.flock(fd,fcntl.LOCK_UN)
            os.close(fd)

def auth_owner(plan):
    if digest(file(OWNER_HELPER,uid=0,mode=0o555,limit=50000)) != OWNER_HELPER_SHA:
        denied("PINNED_OWNER_VERIFIER_MISMATCH")
    spec = importlib.util.spec_from_file_location("pinned_owner_rebind_verifier",OWNER_HELPER)
    if spec is None or spec.loader is None:denied("ENTRA_VERIFIER_UNAVAILABLE")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    endpoint = "https://login.microsoftonline.com/"+helper.TENANT+"/oauth2/v2.0/"
    code = helper._form(endpoint+"devicecode",{"client_id":helper.CLIENT_ID,"scope":helper.SCOPE})
    if not all(isinstance(code.get(k),str) for k in ("device_code","user_code","verification_uri")):
        denied("ENTRA_DEVICE_CODE_UNAVAILABLE")
    print("EXACT_ACTION="+ACTION,flush=True)
    print("SOURCE_SHA="+plan["current_protected_main_sha"],flush=True)
    print("PLAN_SHA256="+plan["plan_sha256"],flush=True)
    print("ROOT_WORKER_REPLACE=true; ONE_PROJECTION_ADD=true; BOOTSTRAP_TIMER_SUPERSEDE=true",flush=True)
    print("IMAGE_PROMOTION_APPROVED=false; PROVIDER_WRITES_APPROVED=false",flush=True)
    print("BROWSER_VERIFICATION_URL="+code["verification_uri"],flush=True)
    print("SIGN_IN_CODE="+code["user_code"],flush=True)
    deadline=time.monotonic()+min(int(code.get("expires_in",600)),600)
    interval=max(5,int(code.get("interval",5)))
    while time.monotonic()<deadline:
        response=helper._form(endpoint+"token",{"grant_type":"urn:ietf:params:oauth:grant_type:device_code",
                              "client_id":helper.CLIENT_ID,"device_code":code["device_code"]})
        if isinstance(response.get("access_token"),str):
            oid=helper.jwt_owner(response["access_token"])
            response=None
            if input("Type "+CONFIRM+" to authorize ONLY this rebind: ").strip()!=CONFIRM:
                denied("EXACT_OWNER_CONFIRMATION_MISSING")
            return oid
        err=response.get("error")
        if err=="slow_down":interval=min(interval+5,20)
        elif err!="authorization_pending":denied("ENTRA_OWNER_AUTH_FAILED")
        time.sleep(interval)
    denied("ENTRA_OWNER_AUTH_EXPIRED")

def atomic_root(path,data,mode):
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix=".catalog-rebind-")
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,"wb") as f:
            f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def ledger_write(name,bytes_):
    path=LEDGER/name
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
    with os.fdopen(fd,"wb") as f:
        f.write(bytes_);f.flush();os.fsync(f.fileno())

def execute():
    plan,_,_,_,_=preflight()
    oid=auth_owner(plan)
    with hold_locks():
        again,worker_before,policy_before,blobs,containers=preflight()
        if again!=plan:denied("APPROVAL_PLAN_CHANGED")
        LEDGER.mkdir(mode=0o700)
        root_directory(LEDGER,0o700)
        approval_id="catalog-rebind-"+uuid4().hex
        ledger_write("prior-worker.bin",worker_before)
        ledger_write("prior-policy.bin",policy_before)
        ledger_write("owner-intent.json",canonical({
            "approval_id":approval_id,"authenticated_owner_oid":oid,
            "action":ACTION,"confirmation":CONFIRM,"plan_sha256":plan["plan_sha256"],
            "source_sha":plan["current_protected_main_sha"],
            "freeze_sha256":plan["original_freeze_sha256"],
            "status":"consumed_before_mutation","created_at":datetime.now(timezone.utc).isoformat()})+b"\n")
        changed_worker=False
        changed_policy=False
        created_projection=False
        stopped_timer=False
        try:
            run("systemctl","disable","--now",BOOTSTRAP_TIMER,timeout=65)
            stopped_timer=True
            enabled_check=subprocess.run(("systemctl","is-enabled",BOOTSTRAP_TIMER),capture_output=True,text=True,timeout=15)
            if enabled_check.stdout.strip()!="disabled":
                denied("BOOTSTRAP_TIMER_NOT_DISABLED")
            atomic_root(WORKER,blobs[str(WORKER)],0o755)
            changed_worker=True
            fd=os.open(PROJECTION,os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,"O_NOFOLLOW",0),0o644)
            created_projection=True
            with os.fdopen(fd,"wb") as f:
                f.write(blobs[str(PROJECTION)]);f.flush();os.fsync(f.fileno())
            updated=canonical(plan["updated_root_policy_exactly"])+b"\n"
            atomic_root(ROOT_POLICY,updated,0o600)
            changed_policy=True
            if (digest(file(WORKER,uid=0,mode=0o755,limit=300000))!=digest(blobs[str(WORKER)])
                    or digest(file(PROJECTION,uid=0,mode=0o644,limit=30000))!=digest(blobs[str(PROJECTION)])
                    or digest(file(ROOT_POLICY,uid=0,mode=0o600,limit=12000))!=plan["updated_root_policy_sha256"]):
                denied("ROOT_REBIND_HASH_READBACK_FAILED")
            if systemctl("is-active",SCOPED_TIMER)!="active" or systemctl("is-enabled",SCOPED_TIMER)!="enabled":
                denied("SCOPED_RECOVERY_TIMER_NOT_ACTIVE")
            bootstrap_state=subprocess.run(("systemctl","is-active",BOOTSTRAP_TIMER),capture_output=True,text=True,timeout=15)
            if bootstrap_state.stdout.strip()=="active":
                denied("SUPERSEDED_BOOTSTRAP_TIMER_STILL_ACTIVE")
            # Exact immutable native helper must import its pinned sibling and pass both read-only preflights.
            native=PROJECTION.parent/"deploy_live_container.py"
            specs=(("jason-runtime","runtime_image_id","JASON_AUTOTASK_CATALOG_AUTH_MODE=jason_managed","8080"),
                   ("jason-mcp-pilot","mcp_image_id","JASON_AUTOTASK_CATALOG_GRANT_ADMIN_PROFILE=aot-catalog-self-owner-v1","8000"))
            manifest=json.loads(file(PROJECTION.parent.parent/"config/catalog-scoped-release-admission.json",uid=0,mode=0o644,limit=15000))
            for live,key,env,port in specs:
                result=run("python3",str(native),"--live",live,"--image",manifest[key],
                           "--rollback","admission-readonly-"+live,
                           "--source-revision",manifest["snapshot_sha"],
                           "--health-url","http://127.0.0.1:"+port+"/healthz",
                           "--harden","--set-env",env,"--preflight",timeout=40)
                fields=dict(line.split("=",1) for line in result.splitlines() if "=" in line)
                if (fields.get("PREFLIGHT")!="PASS" or fields.get("LIVE_CONTAINER")!=live
                        or fields.get("CANDIDATE_IMAGE_ID")!=manifest[key]
                        or fields.get("SOURCE_IMAGE_ID")!=containers[live][1]
                        or fields.get("SET_ENV_COUNT")!="1"
                        or fields.get("ADDITIONAL_READONLY_BIND_COUNT")!="0"):
                    denied("PINNED_NATIVE_PREFLIGHT_FAILED")
            if inspect_containers()!=containers:
                denied("PROTECTED_CONTAINER_CHANGED")
            if digest(file(FREEZE,uid=AL,mode=0o600,limit=4096))!=plan["original_freeze_sha256"]:
                denied("PROTECTED_FREEZE_CHANGED")
            ledger_write("verified.json",canonical({"status":"exact_catalog_root_rebind_verified",
                          "approval_id":approval_id,"source_sha":plan["current_protected_main_sha"],
                          "plan_sha256":plan["plan_sha256"],"images_changed":False,
                          "provider_writes":False,"bootstrap_timer_superseded":True,
                          "scoped_recovery_timer_active":True})+b"\n")
            print("CATALOG_ROOT_REBIND_VERIFIED="+approval_id,flush=True)
        except BaseException:
            # Preserve original root control precisely; do not guess other owner changes.
            good=True
            try:
                if changed_policy:
                    if digest(file(ROOT_POLICY,uid=0,mode=0o600,limit=12000))!=plan["updated_root_policy_sha256"]:
                        denied("UNKNOWN_POLICY_DRIFT")
                    atomic_root(ROOT_POLICY,policy_before,0o600)
                if created_projection:
                    if digest(file(PROJECTION,uid=0,mode=0o644,limit=30000))!=digest(blobs[str(PROJECTION)]):
                        denied("UNKNOWN_PROJECTION_DRIFT")
                    PROJECTION.unlink()
                if changed_worker:
                    if digest(file(WORKER,uid=0,mode=0o755,limit=300000))!=digest(blobs[str(WORKER)]):
                        denied("UNKNOWN_WORKER_DRIFT")
                    atomic_root(WORKER,worker_before,0o755)
                if stopped_timer:
                    run("systemctl","enable","--now",BOOTSTRAP_TIMER,timeout=65)
                if (file(WORKER,uid=0,mode=0o755,limit=300000)!=worker_before
                        or file(ROOT_POLICY,uid=0,mode=0o600,limit=12000)!=policy_before
                        or inspect_containers()!=containers):
                    denied("ROLLBACK_READBACK_FAILED")
            except BaseException:
                good=False
            ledger_write("failed.json",canonical({"rollback_verified":good,"status":"rolled_back" if good else "rollback_unverified"})+b"\n")
            if not good:denied("UNVERIFIED_ROLLBACK_HUMAN_RECOVERY")
            raise

def main():
    p=argparse.ArgumentParser()
    m=p.add_mutually_exclusive_group(required=True)
    m.add_argument("--check-only",action="store_true")
    m.add_argument("--execute",action="store_true")
    a=p.parse_args()
    if a.check_only:
        plan,*_=preflight()
        print(json.dumps({"status":"READONLY_REBIND_PREFLIGHT_PASS_NOT_APPROVED",
                          "source_sha":plan["current_protected_main_sha"],
                          "plan_sha256":plan["plan_sha256"],
                          "mutations":False},sort_keys=True))
    else:execute()

if __name__=="__main__":
    main()
