#!/usr/bin/env python3
"""Exact one-use PMv4 Stage D installation. Not a general systemd installer.

Stage a protected-main runbook READ-ONLY service and add ONE native drift
allowance. Owner consent, production locks, native guards and rollback remain
mandatory; no runtime/MCP/worker or database mutation is authorized.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime,timezone
import argparse
import fcntl
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import time
from uuid import uuid4

ACTION="pmv4-d-one-owner-independent-runbook-read-install-v1"
CONFIRM="APPROVE-EXACT-PMV4-D-INDEPENDENT-RUNBOOK-READ-INSTALL"
UNIT="jason-runbook-management-read.service"
SERVICE_ROOT=Path("/usr/local/lib/jason/runbook-management")
SERVICE_DIR=SERVICE_ROOT/"current"
UNIT_PATH=Path("/etc/systemd/system")/UNIT
REGISTRY=Path("/var/lib/jason/openclaw/json-playbooks.sqlite3")
POLICY=Path("/etc/jason/release-readback-recovery/production-desired-state.json")
FREEZE=Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
CONTROL=Path("/var/lib/jason/openclaw/release-manager/protected-readback/production-control-state.json")
LKG=Path("/opt/jason/current")
LOCKS=(
 Path("/var/lib/jason/openclaw/release-manager/production-transaction.lock"),
 Path("/var/lib/jason/pmv4-shadow/control/host-mutation.lock"),
)
AUDIT=Path("/etc/jason-owner-release/pmv4-d-runbook-read")
OWNER=Path("/usr/local/lib/jason/owner_signer_recovery.py")
OWNER_SHA="24d3632a4b0aa60851a1c82ccb15539eb823dd26afa5a1a2cc8c7afc54d72153"
STAGE_C_SHA="7aaa2c3fc3ac51279c3488a16ab39b6e7a03007e"
STAGE_C_APPROVAL="owner-mcp-8fb03f9faea44336b216456b5afcf663"
STAGE_C_RECEIPT=Path("/var/lib/jason/pmv4-stage-c/receipts")/(
    "owner-"+STAGE_C_APPROVAL+".json")
ARTIFACTS=Path("/srv/jason/archive/engineering-artifacts")
SOURCE_REPO=Path("/home/al/.local/lib/jason/engineering-source-repo")
FILES=(
 "implementation/autonomous_remediation/__init__.py",
 "implementation/autonomous_remediation/playbook_document.py",
 "implementation/autonomous_remediation/playbook_store.py",
 "implementation/autonomous_remediation/runbook_management_read_service.py",
 "infrastructure/pmv4-runbook-management/jason-runbook-management-read.service",
)
PROTECTED=("jason-runtime","jason-mcp-pilot","jason-pmv4-ticket-core",
           "jason-teams-gateway","openbao")
SHADOW="jason-pmv4-shadow-gateway"
ROOT_POLICY_GUARD=Path("/opt/jason/current/tools/production_drift_guard.py")
ROOT_WATCHDOG=Path("/opt/jason/current/tools/production_drift_watchdog.py")
SHA40=re.compile("[a-f0-9]{40}")
SHA64=re.compile("[a-f0-9]{64}")
ENV_NATIVE={**os.environ,"PATH":"/usr/sbin:/usr/bin:/bin"}

class RunbookInstallDenied(PermissionError):pass

def need(ok,code):
    if not ok:raise RunbookInstallDenied("PMV4_D_"+code)

def sha(raw:bytes)->str:return sha256(raw).hexdigest()

def canon(record)->bytes:
    return json.dumps(record,sort_keys=True,separators=(",",":"),
                      allow_nan=False,ensure_ascii=False).encode()

def trusted_read(path:Path, *,uid:int,mode:int|None=None,limit:int=250_000)->bytes:
    need(path.is_absolute() and not path.is_symlink(),"FILE_PATH_UNTRUSTED")
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        st=os.fstat(fd)
        need(stat.S_ISREG(st.st_mode) and st.st_uid==uid and
             st.st_nlink==1 and st.st_size<=limit and
             not st.st_mode&0o022 and
             (mode is None or stat.S_IMODE(st.st_mode)==mode),
             "FILE_METADATA_CHANGED:"+path.name)
        out=os.read(fd,limit+1)
        need(len(out)==st.st_size,"FILE_LENGTH_CHANGED")
        return out
    finally:os.close(fd)

def run(args:list[str], *,user:bool=False,timeout:int=40,check:bool=True):
    argv=(["/usr/sbin/runuser","-u","al","--"] if user else [])+args
    r=subprocess.run(argv,capture_output=True,text=True,timeout=timeout,env=ENV_NATIVE)
    if check:need(r.returncode==0,"HOST_COMMAND_DENIED:"+Path(args[0]).name)
    return r

def git_blob(ref:str, path:str)->bytes:
    raw=run(["/usr/bin/git","-C",str(SOURCE_REPO),
             "show",ref+":"+path],user=True,timeout=25).stdout.encode()
    return raw

def ci(source:str)->None:
    branch=json.loads(run(["/usr/bin/gh","api",
        "repos/al-teamaot-com/jason/branches/main"],user=True,timeout=35).stdout)
    need(branch.get("protected") is True and
         branch.get("commit",{}).get("sha")==source,"PROTECTED_MAIN_CHANGED")
    checks=json.loads(run(["/usr/bin/gh","api",
        "repos/al-teamaot-com/jason/branches/main/protection/required_status_checks"],
        user=True,timeout=35).stdout)
    required=[x.get("context") for x in checks.get("checks",[])]
    need(checks.get("strict") is True and len(required)>=5 and
         all(isinstance(x,str) for x in required),"REQUIRED_CI_POLICY_CHANGED")
    observed=json.loads(run(["/usr/bin/gh","api",
        "repos/al-teamaot-com/jason/commits/"+source+"/check-runs?per_page=100"],
        user=True,timeout=45).stdout).get("check_runs",[])
    for name in required:
        candidates=[r for r in observed if
                    r.get("name")==name and r.get("head_sha")==source]
        candidates.sort(key=lambda r:(r.get("completed_at") or "",r.get("id") or 0),
                        reverse=True)
        need(bool(candidates) and
             candidates[0].get("conclusion")=="success" and
             candidates[0].get("status")=="completed",
             "PROTECTED_CI_NOT_GREEN:"+name)

def packet(path:Path):
    need(os.geteuid()==0 and sys.flags.isolated==1,"ROOT_ISOLATED_ONLY")
    need(os.environ.get("SUDO_USER")=="al" and pwd.getpwnam("al").pw_uid==1000,
         "LOCAL_OWNER_SUDO_ONLY")
    p=json.loads(trusted_read(path,uid=1000,mode=0o400,limit=16000))
    need(set(p)=={"schema_version","action","source_sha","candidate_sha",
           "scope_sha256","root_sha256","files_sha256",
           "policy_base_sha256","policy_target_sha256",
           "freeze_sha256","rollback_sha","stage_c_source_sha",
           "stage_c_approval_id","one_owner_total","production_mutations",
           "runtime_restarts","mcp_restarts","ticket_core_restarts",
           "registry_writes","later_stage_retirements_authorized"},
         "PLAN_SCHEMA_UNEXPECTED")
    need(p["schema_version"]=="1.0" and p["action"]==ACTION and
         SHA40.fullmatch(p["source_sha"]) and
         p["candidate_sha"]==p["source_sha"] and
         SHA40.fullmatch(p["rollback_sha"]) and
         all(isinstance(p[k],str) and SHA64.fullmatch(p[k]) for k in (
           "scope_sha256","root_sha256","policy_base_sha256",
           "policy_target_sha256","freeze_sha256")) and
         p["stage_c_source_sha"]==STAGE_C_SHA and
         p["stage_c_approval_id"]==STAGE_C_APPROVAL and
         p["one_owner_total"]==1 and
         p["production_mutations"]==[
           "install_pinned_readonly_runbook_service",
           "allow_exact_runbook_service_in_native_drift_policy",
           "start_only_runbook_service_and_verify",
           "on_failure_restore_prior_service_and_policy"] and
         all(p[k]==0 for k in
             ("runtime_restarts","mcp_restarts","ticket_core_restarts",
              "registry_writes")) and
         p["later_stage_retirements_authorized"] is False and
         isinstance(p["files_sha256"],dict) and
         set(p["files_sha256"])==set(FILES) and
         all(isinstance(h,str) and SHA64.fullmatch(h)
             for h in p["files_sha256"].values()),
         "EXACT_SCOPE_INVALID")
    unsigned=dict(p);digest=unsigned.pop("scope_sha256")
    need(sha(canon(unsigned))==digest,"SCOPE_HASH_INVALID")
    artifact=ARTIFACTS/("pmv4-d-runbook-read-"+p["source_sha"])
    need(path==artifact/"root-release-plan.json","PACKET_PATH_MISMATCH")
    stage=Path("/run")/("jason-pmv4-d-runbook-"+p["source_sha"][:12])
    root_source=stage/"root.py"
    need(Path(__file__).resolve()==root_source and
         stat.S_IMODE(root_source.lstat().st_mode)==0o400 and
         root_source.lstat().st_uid==0 and not root_source.is_symlink() and
         stage.lstat().st_uid==0 and
         stat.S_IMODE(stage.lstat().st_mode)==0o700 and
         sha(trusted_read(root_source,uid=0,mode=0o400))==p["root_sha256"],
         "PINNED_ROOT_SOURCE_MISMATCH")
    return p,artifact

def proposed_policy(base:bytes)->bytes:
    config=json.loads(base)
    need(config.get("schema_version")=="1.0" and
         isinstance(config.get("allowed_system_units"),list) and
         UNIT not in config["allowed_system_units"],"BASELINE_UNIT_ALREADY_PRESENT")
    target=dict(config)
    target["allowed_system_units"]=sorted(config["allowed_system_units"]+[UNIT])
    return (json.dumps(target,sort_keys=True,indent=2)+"\n").encode()

def verified_stage_c():
    receipt=json.loads(trusted_read(STAGE_C_RECEIPT,uid=0,mode=0o600))
    need(receipt.get("status")=="postmigration_stage_c_accepted" and
         receipt.get("approval_id")==STAGE_C_APPROVAL and
         receipt.get("candidate_sha")==STAGE_C_SHA and
         receipt.get("no_database_relocation") is True and
         receipt.get("mcp_restarts")==0 and
         isinstance(receipt.get("scan_cycle_ids"),list) and
         len(receipt["scan_cycle_ids"])==2 and
         receipt["scan_cycle_ids"][0]!=receipt["scan_cycle_ids"][1],
         "STAGE_C_ROOT_ACCEPTANCE_NOT_VERIFIED")

def status_core():
    result={}
    for n in PROTECTED+(SHADOW,):
        row=json.loads(run(["/usr/bin/docker","inspect",n],timeout=25).stdout)[0]
        state=row.get("State",{})
        need(row.get("Id") and row.get("Image") and
             isinstance(state.get("StartedAt"),str),"PROTECTED_INSPECT_UNAVAILABLE")
        if n in PROTECTED:
            need(state.get("Running") is True,"PROTECTED_CONTAINER_DOWN:"+n)
        if n in ("jason-runtime","jason-pmv4-ticket-core"):
            need(state.get("Health",{}).get("Status")=="healthy",
                 "TICKET_CORE_NOT_HEALTHY:"+n)
        if n=="jason-runtime":
            need("JASON_TICKET_WORKER_HOSTING=external" in
                 row.get("Config",{}).get("Env",[]),
                 "STAGE_C_RUNTIME_NOT_EXTERNAL")
        result[n]=(row["Id"],row["Image"],state.get("Status"),
                   state.get("StartedAt"),state.get("OOMKilled"),
                   state.get("ExitCode"))
    return result

def native_drift(config:Path):
    r=run(["/usr/bin/python3",str(ROOT_POLICY_GUARD),
           "--config",str(config)],timeout=60,check=False)
    need(r.returncode==0 and len(r.stdout)<200_000,
         "NATIVE_DRIFT_GUARD_FAILED")
    parsed=json.loads(r.stdout)
    need(parsed.get("status")=="pass" and parsed.get("problems")==[],
         "NATIVE_DRIFT_NOT_PASS")

def verify(p,artifact):
    ci(p["source_sha"])
    need(sha(git_blob(p["source_sha"],
             "tools/pmv4_d_runbook_read_install_root.py"))==
         p["root_sha256"],"ROOT_SOURCE_NOT_PROTECTED_MAIN")
    for name in FILES:
        raw=trusted_read(artifact/"files"/name,uid=1000,mode=0o400)
        need(sha(raw)==p["files_sha256"][name] and
             raw==git_blob(p["source_sha"],name),"FILE_NOT_PROTECTED_MAIN:"+name)
    need(LKG.resolve(strict=True).name==p["rollback_sha"],
         "PROTECTED_LKG_CHANGED")
    need(sha(trusted_read(FREEZE,uid=1000,mode=0o600))==
         p["freeze_sha256"],"PRODUCTION_FREEZE_CHANGED")
    need(sha(trusted_read(POLICY,uid=0,mode=0o600))==
         p["policy_base_sha256"],"NATIVE_POLICY_BASE_CHANGED")
    original=trusted_read(artifact/"policy-base.json",uid=1000,mode=0o400)
    target=trusted_read(artifact/"policy-target.json",uid=1000,mode=0o400)
    need(sha(original)==p["policy_base_sha256"] and
         sha(target)==p["policy_target_sha256"] and
         target==proposed_policy(original) and
         original==trusted_read(POLICY,uid=0,mode=0o600),
         "UNREVIEWED_POLICY_CHANGE")
    need(not UNIT_PATH.exists() and not SERVICE_ROOT.exists(),
         "RUNBOOK_SERVICE_ALREADY_INSTALLED")
    verified_stage_c()
    state=json.loads(trusted_read(CONTROL,uid=1000,mode=0o600))
    need(state.get("circuit_breaker",{}).get("state")=="closed",
         "PRODUCTION_BREAKER_OPEN")
    native_drift(POLICY)
    need(REGISTRY.is_file() and REGISTRY.lstat().st_uid==1000 and
         stat.S_IMODE(REGISTRY.lstat().st_mode)==0o600,
         "EXISTING_REGISTRY_UNTRUSTED")
    with sqlite3.connect("file:"+REGISTRY.as_posix()+"?mode=ro",uri=True,
                         timeout=4) as db:
        count=db.execute("SELECT COUNT(*) FROM json_playbooks").fetchone()[0]
        gen=db.execute("SELECT generation FROM json_playbook_registry_meta WHERE singleton=1").fetchone()[0]
    return status_core(),{"registry_generation":gen,"rows":count}

@contextmanager
def locks():
    descriptors=[]
    try:
        for i,path in enumerate(LOCKS):
            need(not path.is_symlink(),"PRODUCTION_LOCK_SYMLINK")
            fd=os.open(path,os.O_RDWR|os.O_NOFOLLOW)
            st=os.fstat(fd)
            # Existing PMv3 lock is al-owned 0664 and must remain on the
            # same inode. PMv4 root host lock is root-owned 0600.
            expected_uid=1000 if i==0 else 0
            expected_mode=0o664 if i==0 else 0o600
            need(stat.S_ISREG(st.st_mode) and st.st_uid==expected_uid
                 and stat.S_IMODE(st.st_mode)==expected_mode and
                 st.st_nlink==1 and not st.st_mode&0o002,
                 "PRODUCTION_LOCK_METADATA_CHANGED")
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            descriptors.append(fd)
        yield
    finally:
        for fd in reversed(descriptors):
            fcntl.flock(fd,fcntl.LOCK_UN)
            os.close(fd)

def authenticated_owner(p)->str:
    need(sha(trusted_read(OWNER,uid=0,mode=0o555,limit=50000))==OWNER_SHA,
         "OWNER_VERIFIER_CHANGED")
    spec=importlib.util.spec_from_file_location("stage_d_pinned_owner",OWNER)
    need(spec is not None and spec.loader is not None,"ENTRA_OWNER_MODULE_UNAVAILABLE")
    lib=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lib)
    endpoint="https://login.microsoftonline.com/"+lib.TENANT+"/oauth2/v2.0/"
    auth=lib._form(endpoint+"devicecode",
                   {"client_id":lib.CLIENT_ID,"scope":lib.SCOPE})
    need(all(isinstance(auth.get(k),str) for k in
             ("device_code","user_code","verification_uri")),
         "OWNER_DEVICE_CODE_FAILED")
    print("EXACT_ACTION="+ACTION,flush=True)
    print("SOURCE_SHA="+p["source_sha"],flush=True)
    print("EXACT_SCOPE_SHA256="+p["scope_sha256"],flush=True)
    print("ONE_SYSTEMD_UNIT="+UNIT,flush=True)
    print("ONE_ROOT_POLICY_ALLOWANCE=true; NO_RUNTIME_MCP_WORKER_RESTART=true",flush=True)
    print("BROWSER_VERIFICATION_URL="+auth["verification_uri"],flush=True)
    print("SIGN_IN_CODE="+auth["user_code"],flush=True)
    interval=max(5,int(auth.get("interval",5)))
    deadline=time.monotonic()+min(600,int(auth.get("expires_in",600)))
    while time.monotonic()<deadline:
        value=lib._form(endpoint+"token",{
            "grant_type":"urn:ietf:params:oauth:grant-type:device_code",
            "client_id":lib.CLIENT_ID,"device_code":auth["device_code"]})
        if isinstance(value.get("access_token"),str):
            owner=str(lib.jwt_owner(value["access_token"]))
            value=None
            need(input("Type "+CONFIRM+" to approve ONLY this service: ").strip()==CONFIRM,
                 "EXACT_OWNER_CONFIRMATION_MISSING")
            return owner
        err=value.get("error")
        if err=="slow_down":interval=min(interval+5,25)
        elif err!="authorization_pending":need(False,"ENTRA_OWNER_AUTH_DENIED")
        time.sleep(interval)
    need(False,"ENTRA_OWNER_AUTH_EXPIRED")

def root_write(path:Path,raw:bytes,mode:int)->None:
    need(not path.exists() and not path.is_symlink(),"ROOT_FILE_ALREADY_EXISTS")
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    try:
        with os.fdopen(fd,"wb",closefd=False) as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
    finally:os.close(fd)
    os.chmod(path,mode)
    need(path.lstat().st_uid==0 and sha(path.read_bytes())==sha(raw),
         "ROOT_FILE_READBACK_FAILED")

def atomic_policy(data:bytes,expected:bytes)->None:
    need(trusted_read(POLICY,uid=0,mode=0o600)==expected,
         "ROOT_POLICY_ATOMIC_BASE_CHANGED")
    marker=POLICY.parent/(".pmv4-d-"+uuid4().hex+".tmp")
    try:
        root_write(marker,data,0o600)
        os.replace(marker,POLICY)
        dfd=os.open(POLICY.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(dfd)
        finally:os.close(dfd)
    finally:
        if marker.exists():marker.unlink()
    need(trusted_read(POLICY,uid=0,mode=0o600)==data,
         "ROOT_POLICY_ATOMIC_READBACK_FAILED")

def systemctl(*args:str,timeout:int=35,check:bool=True):
    return run(["/usr/bin/systemctl",*args],timeout=timeout,check=check)

def service_readback():
    need(systemctl("is-active",UNIT).stdout.strip()=="active",
         "RUNBOOK_UNIT_NOT_ACTIVE")
    need(systemctl("is-enabled",UNIT).stdout.strip()=="enabled",
         "RUNBOOK_UNIT_NOT_ENABLED")
    socket_path=Path("/run/jason-runbook-management/read.sock")
    need(socket_path.is_socket() and
         stat.S_IMODE(socket_path.lstat().st_mode)==0o600 and
         socket_path.lstat().st_uid==1000,"RUNBOOK_SOCKET_NOT_TRUSTED")
    probe=(
        "import json,socket,sys;"
        "s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);"
        "s.settimeout(5);"
        "s.connect(sys.argv[1]);"
        "s.sendall(b'{\"operation\":\"status\"}\\n');"
        "data=s.makefile('rb').readline();"
        "print(data.decode().strip());"
        "s.close()"
    )
    out=run(["/usr/bin/python3","-c",probe,str(socket_path)],user=True,
            timeout=15).stdout
    state=json.loads(out)
    need(state.get("status")=="healthy" and
         state.get("provider_calls") is False and
         state.get("execution_authority") is False and
         state.get("configuration_mutations") is False and
         type(state.get("registry_generation")) is int and
         type(state.get("active_count")) is int,
         "RUNBOOK_SOCKET_READONLY_ACCEPTANCE_FAILED")
    return state

def verify_recent_ticket_scan():
    path=Path("/var/lib/jason/ticket-core/autonomy-operational-work.sqlite3")
    with sqlite3.connect("file:"+path.as_posix()+"?mode=ro",
                         uri=True,timeout=5) as db:
        row=db.execute(
            "SELECT scanned_at,provider_items,duplicate_items FROM "
            "autonomy_ticket_scan_cycle ORDER BY scanned_at DESC LIMIT 1").fetchone()
    need(row is not None and type(row[1]) is int and row[1]>=0 and
         row[2]==0,"PROVIDER_TICKET_SCAN_NOT_ACCEPTED")
    when=datetime.fromisoformat(row[0].replace("Z","+00:00"))
    seconds=(datetime.now(timezone.utc)-when).total_seconds()
    need(0<=seconds<=180,"PROVIDER_TICKET_SCAN_NOT_FRESH")
    return row[0]

def install_files(p,artifact):
    SERVICE_ROOT.mkdir(mode=0o755)
    SERVICE_DIR.mkdir(mode=0o755)
    module=SERVICE_DIR/"autonomous_remediation"
    module.mkdir(mode=0o755)
    for rel in FILES:
        raw=trusted_read(artifact/"files"/rel,uid=1000,mode=0o400)
        if rel.startswith("implementation/"):
            dest=module/Path(rel).name
            root_write(dest,raw,0o444)
        else:
            root_write(UNIT_PATH,raw,0o644)
    need(sha(UNIT_PATH.read_bytes())==p["files_sha256"][FILES[-1]],
         "UNIT_INSTALL_HASH_MISMATCH")

def remove_own_files():
    if UNIT_PATH.exists():
        need(UNIT_PATH.lstat().st_uid==0 and not UNIT_PATH.is_symlink(),
             "ROLLBACK_UNIT_UNTRUSTED")
        UNIT_PATH.unlink()
    if SERVICE_ROOT.exists():
        need(SERVICE_ROOT.is_dir() and not SERVICE_ROOT.is_symlink() and
             SERVICE_ROOT.lstat().st_uid==0,
             "ROLLBACK_DIRECTORY_UNTRUSTED")
        for child in SERVICE_ROOT.rglob("*"):
            need(not child.is_symlink() and child.lstat().st_uid==0,
                 "ROLLBACK_TREE_UNTRUSTED")
        shutil.rmtree(SERVICE_ROOT)

def audit(path:Path,obj):
    root_write(path,canon(obj),0o600)

def execute(path:Path):
    p,artifact=packet(path)
    initial,registry=verify(p,artifact)
    need(os.isatty(0) and os.isatty(1),"LOCAL_OWNER_TTY_REQUIRED")
    owner=authenticated_owner(p)
    with locks():
        replan,restaged=packet(path)
        need(replan==p and restaged==artifact,"OWNER_SCOPE_CHANGED")
        same,now_registry=verify(p,artifact)
        need(same==initial and now_registry==registry,
             "PROTECTED_STATE_CHANGED")
        AUDIT.mkdir(mode=0o700,parents=True,exist_ok=True)
        need(AUDIT.lstat().st_uid==0 and
             stat.S_IMODE(AUDIT.lstat().st_mode)==0o700,
             "ROOT_AUDIT_DIRECTORY_INVALID")
        attempt=AUDIT/(p["source_sha"]+"-attempt.json")
        accepted=AUDIT/(p["source_sha"]+"-accepted.json")
        need(not attempt.exists() and not accepted.exists(),
             "OWNER_ACTION_ALREADY_CONSUMED")
        approval="pmv4-d-owner-"+uuid4().hex
        audit(attempt,{
            "schema_version":"1.0","action":ACTION,
            "status":"owner_consumed_before_mutation",
            "approval_id":approval,"verified_owner_oid":owner,
            "source_sha":p["source_sha"],"scope_sha256":p["scope_sha256"],
            "at":datetime.now(timezone.utc).isoformat(),
        })
        old=trusted_read(artifact/"policy-base.json",uid=1000,mode=0o400)
        target=trusted_read(artifact/"policy-target.json",uid=1000,mode=0o400)
        mutated=False
        try:
            install_files(p,artifact)
            atomic_policy(target,old)
            mutated=True
            systemctl("daemon-reload")
            systemctl("enable","--now",UNIT,timeout=70)
            socket=service_readback()
            need(socket["registry_generation"]==registry["registry_generation"] and
                 socket["active_count"]==registry["rows"],
                 "RUNBOOK_REGISTRY_CONTENT_CHANGED")
            scan=verify_recent_ticket_scan()
            native_drift(POLICY)
            systemctl("start","jason-production-drift-watchdog.service",timeout=70)
            native_drift(POLICY)
            need(status_core()==initial,"PROTECTED_CONTAINERS_CHANGED")
            state=json.loads(trusted_read(CONTROL,uid=1000,mode=0o600))
            need(state.get("circuit_breaker",{}).get("state")=="closed" and
                 sha(trusted_read(FREEZE,uid=1000,mode=0o600))==
                 p["freeze_sha256"],
                 "BREAKER_OR_FREEZE_CHANGED")
            need(trusted_read(POLICY,uid=0,mode=0o600)==target,
                 "INSTALLED_POLICY_NOT_EXACT")
            audit(accepted,{
                "schema_version":"1.0","action":ACTION,
                "status":"independent_runbook_read_service_accepted",
                "source_sha":p["source_sha"],"scope_sha256":p["scope_sha256"],
                "owner_approval_id":approval,"registry_generation":socket["registry_generation"],
                "active_count":socket["active_count"],
                "last_ticket_scan_at":scan,"provider_writes":0,
                "mcp_restarts":0,"runtime_restarts":0,"ticket_core_restarts":0,
                "native_drift":"pass","production_freeze_unchanged":True,
                "accepted_at":datetime.now(timezone.utc).isoformat(),
            })
        except BaseException:
            restored=False
            try:
                systemctl("disable","--now",UNIT,timeout=50,check=False)
                remove_own_files()
                systemctl("daemon-reload")
                current=trusted_read(POLICY,uid=0,mode=0o600)
                if current==target:
                    atomic_policy(old,target)
                else:
                    need(current==old,"ROLLBACK_POLICY_UNEXPECTED")
                native_drift(POLICY)
                restored=(status_core()==initial and
                          sha(trusted_read(FREEZE,uid=1000,mode=0o600))==
                          p["freeze_sha256"])
            except BaseException:
                restored=False
            audit(AUDIT/(p["source_sha"]+"-rollback.json"),{
                "schema_version":"1.0","action":ACTION,
                "scope_sha256":p["scope_sha256"],
                "status":"rolled_back" if restored else "rollback_unverified",
                "rollback_verified":restored,
                "at":datetime.now(timezone.utc).isoformat(),
            })
            raise
    print("PMV4_D_INDEPENDENT_RUNBOOK_READ_SERVICE=ACCEPTED",flush=True)
    print("NATIVE_DRIFT=PASS; TICKET_CORE_MCP_FREEZE=UNCHANGED",flush=True)
    print("REGISTRY_READ_ONLY=true; NO_PROVIDER_AUTHORITY=true",flush=True)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--plan",type=Path,required=True)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-only",action="store_true")
    mode.add_argument("--execute",action="store_true")
    args=parser.parse_args()
    try:
        if args.check_only:
            p,a=packet(args.plan)
            before,registry=verify(p,a)
            print("PMV4_D_ROOT_PROTECTED_PREFLIGHT=PASS",flush=True)
            print("SOURCE="+p["source_sha"],flush=True)
            print("SCOPE_SHA256="+p["scope_sha256"],flush=True)
            print("EXISTING_REGISTRY_GENERATION="+str(registry["registry_generation"]),flush=True)
            print("OWNER_APPROVAL_USED=false; PRODUCTION_MUTATIONS=false",flush=True)
        else:execute(args.plan)
    except BaseException as exc:
        print("PMV4_D_ROOT_DENIED:"+type(exc).__name__+":"+str(exc)[:160],
              file=sys.stderr,flush=True)
        raise SystemExit(2)
if __name__=="__main__":main()
