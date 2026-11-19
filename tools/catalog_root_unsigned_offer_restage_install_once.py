#!/usr/bin/env python3
"""One-use, authenticated install of the catalog-only safe unsigned offer restager.

No runtime/MCP image promotion, Autotask write grant, PMv4 release, freeze
removal, Docker action or service restart. Only one reviewed root Python blob.
"""
from __future__ import annotations

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
import stat
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

ACTION="catalog-source-only-offer-safe-restage-root-module-v1"
WORD="APPROVE-EXACT-CATALOG-UNSIGNED-OFFER-RESTAGE-MODULE-ONLY"
RELEASE_ID="release-755fa5fe3f75958f"
CANDIDATE="755fa5fe3f75958fee2427a0af0777dd242d8f00"
ROLLBACK="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
IMAGE_RUNTIME="sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132"
IMAGE_MCP="sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477"
FREEZE_SHA="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
OLD_MODULE_SHA="fa9f232522b7bd210846ab2783e71e67443f32e20bf795908c0582992bd00c99"
NEW_MODULE_SHA="382cadc5a199788cb36a14317611dc808fee8105df81022c2bb67f2453b4c5a9"
ROOT_WORKER_SHA="dca0c480265426c3c73f9cf8f7b8a9a4c5ab555640bd6953eb127cf3963a1896"
ROOT_POLICY_SHA="7a4f43b7c58d31ba69a6fe08891e3193a218fe39991457dd4c278f0c44cdbdba"
OWNER_HELPER_SHA="24d3632a4b0aa60851a1c82ccb15539eb823dd26afa5a1a2cc8c7afc54d72153"
ROOT_MODULE=Path("/usr/local/lib/jason/catalog-scoped-promotion/tools/catalog_scoped_promotion_root.py")
ROOT_WORKER=Path("/usr/local/lib/jason/release_host_reconcile_worker.py")
ROOT_POLICY=Path("/etc/jason-owner-release/catalog-scoped-promotion-installed.json")
ROOT_ENTRY=Path("/root/catalog-root-unsigned-offer-safe-restage-install-once.py")
ROOT_BUNDLE=Path("/usr/local/lib/jason/catalog-scoped-promotion")
ROOT_OWNER_HELPER=Path("/usr/local/lib/jason/owner_signer_recovery.py")
REPO=Path("/home/al/.local/lib/jason/engineering-source-repo")
STATE=Path("/var/lib/jason/openclaw/release-manager")
ROOT_CATALOG=Path("/var/lib/jason-catalog-scoped-promotion")
AUTH=Path("/var/lib/jason/authority/catalog-scoped-release")
LEDGER=ROOT_CATALOG/"unsigned-offer-restage-module-oneuse"
NATIVE_LOCK=STATE/"production-transaction.lock"
SHADOW_LOCK=Path("/var/lib/jason/pmv4-shadow/control/host-mutation.lock")
SNAPSHOT=("jason-runtime","jason-mcp-pilot","jason-pmv4-ticket-core",
          "jason-pmv4-shadow-gateway","jason-teams-gateway","openbao")

def fail(reason:str):
    raise PermissionError("CATALOG_RESTAGE_INSTALL_DENIED_"+reason)

def digest(raw:bytes)->str:return sha256(raw).hexdigest()

def trusted(path:Path,*,owner:int=0,mode:int=0o644,max_bytes:int=550000)->bytes:
    if path.is_symlink():fail("SYMLINK_"+path.name)
    fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
    try:
        st=os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid!=owner or
            stat.S_IMODE(st.st_mode)!=mode or st.st_nlink!=1 or
            not 0<st.st_size<=max_bytes):
            fail("TRUSTED_FILE_"+path.name)
        content=os.read(fd,max_bytes+1)
        if len(content)!=st.st_size:fail("FILE_RACE_"+path.name)
        return content
    finally:os.close(fd)

def run(*args:str,as_al:bool=False,timeout:int=35)->bytes:
    cmd=(("runuser","-u","al","--")+args) if as_al else args
    proc=subprocess.run(cmd,capture_output=True,timeout=timeout,check=False)
    if proc.returncode:fail("READONLY_COMMAND_FAILED_"+args[0].replace("/","_"))
    return proc.stdout

def verified_main()->str:
    line=run("git","-C",str(REPO),"ls-remote","origin","refs/heads/main",as_al=True).decode().strip().split()
    if len(line)!=2 or line[1]!="refs/heads/main" or not re.fullmatch("[0-9a-f]{40}",line[0]):
        fail("PROTECTED_MAIN_UNAVAILABLE")
    return line[0]

def ci_green(sha:str):
    base="repos/al-teamaot-com/jason/"
    branch=json.loads(run("gh","api",base+"branches/main",as_al=True))
    if not branch.get("protected") or branch.get("commit",{}).get("sha")!=sha:
        fail("GITHUB_PROTECTED_MAIN_CHANGED")
    rules=json.loads(run("gh","api",base+"branches/main/protection/required_status_checks",as_al=True))
    checks=rules.get("checks") or []
    if rules.get("strict") is not True or len(checks)<5:fail("PROTECTED_CHECKS_NOT_ENFORCED")
    runs=json.loads(run("gh","api",base+"commits/"+sha+"/check-runs?per_page=100",as_al=True))["check_runs"]
    latest={}
    for row in runs:
        name=row.get("name")
        if name and (name not in latest or int(row["id"])>int(latest[name]["id"])):
            latest[name]=row
    for item in checks:
        result=latest.get(item["context"])
        if not result or result.get("conclusion")!="success" or result.get("status")!="completed":
            fail("PROTECTED_CI_NOT_GREEN_"+item["context"])

def container_snapshot():
    rows=json.loads(run("docker","inspect",*SNAPSHOT))
    if len(rows)!=len(SNAPSHOT):fail("PROTECTED_CONTAINER_COUNT")
    result={}
    for row in rows:
        name=row["Name"].lstrip("/")
        if name not in SNAPSHOT or not row["State"]["Running"]:
            fail("PROTECTED_SERVICE_UNHEALTHY")
        if name in ("jason-pmv4-ticket-core","jason-pmv4-shadow-gateway"):
            if row["State"].get("Health",{}).get("Status")!="healthy":
                fail("PMV4_PROTECTED_TICKET_UNHEALTHY")
        result[name]=(row["Id"],row["Image"],row["State"]["StartedAt"])
    if result["jason-runtime"][1]!=IMAGE_RUNTIME or result["jason-mcp-pilot"][1]!=IMAGE_MCP:
        fail("ORIGINAL_CATALOG_CONTAINERS_CHANGED")
    system=run("systemctl","show","jason-runbook-management-read.service",
               "-p","ActiveState","-p","SubState","-p","MainPID","-p","ActiveEnterTimestamp")
    fields=dict(x.split("=",1) for x in system.decode().splitlines() if "=" in x)
    if fields.get("ActiveState")!="active" or fields.get("SubState")!="running" or fields.get("MainPID") in (None,"0"):
        fail("PMV4_RUNBOOK_MANAGEMENT_UNHEALTHY")
    return {"containers":result,"runbook":fields}

def no_prior_release():
    if (AUTH/"owner-approvals"/(RELEASE_ID+".json")).exists():
        fail("SIGNED_OWNER_CATALOG_APPROVAL_ALREADY_ISSUED")
    if (ROOT_CATALOG/"transactions"/(RELEASE_ID+".json")).exists():
        fail("PRODUCTION_CATALOG_TRANSACTION_ALREADY_ATTEMPTED")
    if (ROOT_CATALOG/"active.json").exists():fail("CATALOG_ALREADY_PROMOTED")
    public=json.loads(trusted(AUTH/"offers"/(RELEASE_ID+".json"),
                              owner=1000,mode=0o600,max_bytes=16384))
    root=json.loads(trusted(ROOT_CATALOG/"offers"/(RELEASE_ID+".json"),
                            owner=0,mode=0o600,max_bytes=16384))
    if public!=root or root.get("release_id")!=RELEASE_ID or root.get("candidate_sha")!=CANDIDATE or root.get("rollback_sha")!=ROLLBACK:
        fail("UNSIGNED_OFFER_ROOT_PUBLIC_DRIFT")
    return root

def preflight():
    if (os.geteuid()!=0 or os.environ.get("SUDO_USER")!="al"
            or not os.isatty(0) or not os.isatty(1)):
        fail("INTERACTIVE_AUTHENTICATED_HOST_REQUIRED")
    if pwd.getpwnam("al").pw_uid!=1000:fail("PINNED_HOST_OPERATOR_CHANGED")
    if digest(trusted(ROOT_ENTRY,owner=0,mode=0o500,max_bytes=550000)) != digest(
           run("git","-C",str(REPO),"show",verified_main()+":tools/catalog_root_unsigned_offer_restage_install_once.py",as_al=True)):
        fail("PINNED_ROOT_INSTALLER_SOURCE_CHANGED")
    if digest(trusted(ROOT_MODULE))!=OLD_MODULE_SHA:fail("ROOT_MODULE_BEFORE_IMAGE_CHANGED")
    if digest(trusted(ROOT_WORKER,mode=0o755))!=ROOT_WORKER_SHA:fail("ROOT_WORKER_CHANGED")
    if digest(trusted(ROOT_POLICY,mode=0o600))!=ROOT_POLICY_SHA:fail("ROOT_POLICY_CHANGED")
    if digest(trusted(ROOT_OWNER_HELPER,mode=0o555,max_bytes=60000))!=OWNER_HELPER_SHA:
        fail("ENTRA_VERIFIER_CHANGED")
    if LEDGER.exists() or LEDGER.is_symlink():fail("ONEUSE_ALREADY_CONSUMED")
    original_freeze=trusted(STATE/"production-deployment-freeze",owner=1000,mode=0o600,max_bytes=4096)
    if digest(original_freeze)!=FREEZE_SHA:fail("PRODUCTION_FREEZE_CHANGED")
    control=json.loads(trusted(STATE/"protected-readback/production-control-state.json",
                               owner=1000,mode=0o600,max_bytes=131072))
    drift=json.loads(trusted(STATE/"protected-readback/production-drift.json",
                             owner=1000,mode=0o600,max_bytes=131072))
    if control["circuit_breaker"]["state"]!="closed" or drift.get("status")!="pass" or drift.get("problems"):
        fail("PRODUCTION_CONTROL_NOT_HEALTHY")
    if run("systemctl","is-active","jason-catalog-scoped-recovery.timer").decode().strip()!="active":
        fail("ROOT_ROLLBACK_TIMER_UNAVAILABLE")
    current=verified_main()
    ci_green(current)
    new=run("git","-C",str(REPO),"show",current+":tools/catalog_scoped_promotion_root.py",as_al=True)
    if digest(new)!=NEW_MODULE_SHA:fail("REVIEWED_RESTAGE_MODULE_NOT_CURRENT_SOURCE")
    no_prior_release()
    return current,new,container_snapshot(),original_freeze

def auth_owner(source,module_sha):
    spec=importlib.util.spec_from_file_location("pinned_existing_jason_entra_owner",ROOT_OWNER_HELPER)
    if spec is None or spec.loader is None:fail("OWNER_AUTH_HELPER_NOT_LOADABLE")
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    endpoint="https://login.microsoftonline.com/"+helper.TENANT+"/oauth2/v2.0/"
    claim=helper._form(endpoint+"devicecode",{"client_id":helper.CLIENT_ID,"scope":helper.SCOPE})
    if not all(isinstance(claim.get(k),str) for k in ("device_code","user_code","verification_uri")):
        fail("ENTRA_DEVICE_AUTH_UNAVAILABLE")
    print("EXACT_ACTION="+ACTION,flush=True)
    print("SOURCE_SHA="+source,flush=True)
    print("ROOT_MODULE_OLD_SHA256="+OLD_MODULE_SHA,flush=True)
    print("ROOT_MODULE_NEW_SHA256="+module_sha,flush=True)
    print("IMAGE_PROMOTION=false; PROVIDER_WRITES=false",flush=True)
    print("BROWSER_VERIFICATION_URL="+claim["verification_uri"],flush=True)
    print("SIGN_IN_CODE="+claim["user_code"],flush=True)
    ttl=min(int(claim.get("expires_in",0)),600)
    if ttl<60:fail("ENTRA_DEVICE_CODE_TTL")
    delay=max(5,min(int(claim.get("interval",5)),20))
    until=time.monotonic()+ttl
    while time.monotonic()<until:
        time.sleep(delay)
        res=helper._form(endpoint+"token",{
            "grant_type":"urn:ietf:params:oauth:grant-type:device_code",
            "client_id":helper.CLIENT_ID,"device_code":claim["device_code"]})
        if isinstance(res.get("access_token"),str):
            oid=helper.jwt_owner(res["access_token"])
            res=None
            if input("Type "+WORD+" to authorize ONLY root module installation: ").strip()!=WORD:
                fail("EXACT_OWNER_DECISION_MISSING")
            return oid
        status=str(res.get("error") or "")
        if status=="slow_down":delay=min(delay+5,20)
        elif status!="authorization_pending":fail("ENTRA_OWNER_LOGIN_FAILED")
    fail("ENTRA_OWNER_LOGIN_EXPIRED")

def replace(path:Path,data:bytes):
    fd,temp=tempfile.mkstemp(prefix=".catalog-safe-restage-",dir=path.parent)
    try:
        os.fchown(fd,0,0);os.fchmod(fd,0o644)
        with os.fdopen(fd,"wb") as out:
            out.write(data);out.flush();os.fsync(out.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def record(name:str,obj):
    p=LEDGER/name
    b=(json.dumps(obj,sort_keys=True,separators=(",",":"))+"\n").encode() if isinstance(obj,dict) else obj
    handle=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
    with os.fdopen(handle,"wb") as out:
        out.write(b);out.flush();os.fsync(out.fileno())

def execute():
    source,new,before,marker=preflight()
    owner=auth_owner(source,digest(new))
    latest,refreshed,protected,freeze=preflight()
    if (latest!=source or refreshed!=new or protected!=before or freeze!=marker):
        fail("EXACT_SOURCE_OR_HOST_CHANGED_DURING_OWNER_AUTH")
    fd=os.open(NATIVE_LOCK,os.O_RDWR|getattr(os,"O_NOFOLLOW",0))
    shadow=os.open(SHADOW_LOCK,os.O_RDWR|getattr(os,"O_NOFOLLOW",0))
    try:
        for handle,path,expected_uid in ((fd,NATIVE_LOCK,1000),(shadow,SHADOW_LOCK,0)):
            meta=os.fstat(handle)
            if (path.is_symlink() or not stat.S_ISREG(meta.st_mode)
                    or meta.st_uid!=expected_uid or (meta.st_mode&0o002)):
                fail("NATIVE_RELEASE_LOCK_UNTRUSTED")
            try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:fail("OTHER_GOVERNED_RELEASE_IN_PROGRESS")
        current,actual,still,frozen=preflight()
        if (current,actual,still,frozen)!=(source,new,before,marker):
            fail("EXACT_SOURCE_CHANGED_WHILE_LOCKED")
        LEDGER.mkdir(mode=0o700)
        intent="owner-"+uuid4().hex
        record_original=trusted(ROOT_MODULE)
        record("original-root-module.bin",record_original)
        record("owner-intent.json",{
            "status":"consumed_before_mutation","action":ACTION,"approval_id":intent,
            "owner_oid":owner,"source_sha":source,"original_sha256":OLD_MODULE_SHA,
            "candidate_sha256":NEW_MODULE_SHA,"freeze_sha256":FREEZE_SHA,
            "approved_at":datetime.now(timezone.utc).isoformat(),
            "image_promotion_approved":False,"autotask_provider_writes_approved":False,
        })
        changed=False
        try:
            replace(ROOT_MODULE,new)
            changed=True
            if digest(trusted(ROOT_MODULE))!=NEW_MODULE_SHA:
                fail("ROOT_MODULE_NEW_HASH_MISMATCH")
            spec=importlib.util.spec_from_file_location("reviewed_existing_trusted_root_worker",ROOT_WORKER)
            root=importlib.util.module_from_spec(spec);spec.loader.exec_module(root)
            verified=root._trusted_catalog_scoped_promotion_module(source)
            if not callable(verified.execute_native_catalog_scoped_request):
                fail("NATIVE_ROOT_CATALOG_HANDLER_MISSING")
            if container_snapshot()!=before:fail("PMV4_OR_CATALOG_CONTAINER_CHANGED")
            if trusted(STATE/"production-deployment-freeze",owner=1000,mode=0o600,max_bytes=4096)!=marker:
                fail("PRODUCTION_FREEZE_CHANGED")
            if verified_main()!=source:fail("PROTECTED_MAIN_CHANGED_DURING_INSTALL")
            record("verified.json",{
                "status":"exact_catalog_unsigned_offer_restage_root_module_verified",
                "approval_id":intent,"source_sha":source,"module_sha256":NEW_MODULE_SHA,
                "original_sha256":OLD_MODULE_SHA,"freeze_unchanged":True,
                "pmv4_containers_unchanged":True,"image_promotion":False,"provider_writes":False,
            })
            print("CATALOG_UNSIGNED_OFFER_RESTAGE_MODULE_VERIFIED="+intent,flush=True)
        except BaseException:
            restored=False
            try:
                if changed:
                    if digest(trusted(ROOT_MODULE))!=NEW_MODULE_SHA:
                        fail("UNKNOWN_ROOT_MODULE_STATE_DO_NOT_OVERWRITE")
                    replace(ROOT_MODULE,record_original)
                restored=(digest(trusted(ROOT_MODULE))==OLD_MODULE_SHA)
            except BaseException:restored=False
            record("failed.json",{"status":"rolled_back" if restored else "rollback_unverified",
                                  "rollback_verified":restored})
            if not restored:fail("ROOT_MODULE_ROLLBACK_UNVERIFIED")
            raise
    finally:
        for handle in (shadow,fd):
            try:fcntl.flock(handle,fcntl.LOCK_UN)
            except OSError:pass
            os.close(handle)

def main():
    cli=argparse.ArgumentParser()
    mode=cli.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-only",action="store_true")
    mode.add_argument("--execute",action="store_true")
    parsed=cli.parse_args()
    if parsed.check_only:
        source,new,baseline,_=preflight()
        print(json.dumps({"status":"READONLY_ROOT_RESTAGE_INSTALL_PREFLIGHT_PASS",
            "source_sha":source,"old_module_sha256":OLD_MODULE_SHA,
            "new_module_sha256":digest(new),"protected_container_count":len(baseline["containers"]),
            "owner_approval_recorded":False,"production_mutations":False},sort_keys=True))
    else:
        execute()

if __name__=="__main__":
    raise SystemExit(main())
