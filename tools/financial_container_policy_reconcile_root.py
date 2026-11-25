#!/usr/bin/env python3
"""Exact one-use signed root policy allowance for the independent financial service.

Requires separately completed PMv4 four-unit reconciliation and native clean
breaker before adding only jason-financial-statements to the root-owned
effective desired state. No runtime, MCP, PMv4, systemd, provider or freeze edit.
"""
from __future__ import annotations
from datetime import datetime,timezone
from hashlib import sha256
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time

ACTION="owner-financial-container-root-policy-allowance-20261117"
ROOT_POLICY=Path("/etc/jason/release-readback-recovery/production-desired-state.json")
BASE_SHA="e17ffed6b6c4589721d69a46a25b80f80d571e8b67e1726c881647d07e29a2b8"
TARGET_SHA="cf8aa933c78513b1b3b4391c68d71a04a17f5d3fa47e6c7d14d96347ce0b2647"
NAME="jason-financial-statements"
PMV4_SOURCE="7792e9018cc4535d0517dff4bf29e35644f5e9e4"
FINANCIAL_SOURCE="c205bb4ac163e7d433796f2f4839a90c7cc1f56b"
FINANCIAL_IMAGE="sha256:913322f47c96ae56f5ae9bb4c6e742ebe36691dc28ca56c202b124bf969ea195"
LKG="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
FREEZE_SHA="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
HOLD=Path("/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold")
FREEZE=Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
DRIFT=Path("/var/lib/jason/openclaw/release-manager/protected-readback/production-drift.json")
CONTROL=Path("/var/lib/jason/openclaw/release-manager/protected-readback/production-control-state.json")
CAT_AUDIT=Path("/etc/jason-owner-release/pmv4-catalog-unit-drift-reconciliation")
LEDGER=Path("/etc/jason-owner-release/financial-container-policy-reconcile-ledger")
SRC_FILE="financial_container_policy_reconcile_root.py"
STAGE_PARENT=Path("/home/al/.local/share/jason")
UID=1000
SIGNER=Path("/usr/local/lib/jason/owner_signed_release.py")
SIGNER_SHA="f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3"
PUBLIC=Path("/etc/jason-owner-release/verified-owner-public-key.json")
NATIVE_LOCK=Path("/var/lib/jason/openclaw/release-manager/production-transaction.lock")
PMV4_LOCK=Path("/var/lib/jason/pmv4-shadow/control/host-mutation.lock")
PROTECTED=("jason-runtime","jason-mcp-pilot","jason-pmv4-shadow-gateway","jason-teams-gateway","openbao")
ALLOWED_STAGE={"manifest.json",SRC_FILE,"baseline.json","candidate.json"}
OWNER_FILE="owner-proof.json"

class Denied(PermissionError):pass

def need(ok,msg):
    if not ok:raise Denied(msg)

def digest(blob):return sha256(blob).hexdigest()

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False).encode()

def candidate(raw):
    p=json.loads(raw)
    need(isinstance(p,dict) and p.get("schema_version")=="1.0"
         and isinstance(p.get("allowed_running_containers"),list),
         "FINANCIAL_POLICY_BASELINE_SCHEMA_CHANGED")
    running=p["allowed_running_containers"]
    need(NAME not in running and len(running)==len(set(running)),
         "FINANCIAL_POLICY_ALREADY_DECLARED_OR_INVALID")
    p["allowed_running_containers"]=sorted(running+[NAME])
    return (json.dumps(p,indent=2,sort_keys=True)+"\n").encode()

def stage(directory,with_proof=False):
    need(directory.parent==STAGE_PARENT
         and re.fullmatch("financial-container-policy-[0-9a-f]{12}",directory.name)
         and directory.is_dir() and not directory.is_symlink()
         and directory.lstat().st_uid==UID
         and stat.S_IMODE(directory.lstat().st_mode)==0o700,
         "FINANCIAL_POLICY_STAGE_UNTRUSTED")
    names=set(ALLOWED_STAGE)
    if with_proof:names.add(OWNER_FILE)
    elif (directory/OWNER_FILE).exists():names.add(OWNER_FILE)
    need({p.name for p in directory.iterdir()}==names,
         "FINANCIAL_POLICY_STAGE_UNEXPECTED_FILES")
    files={}
    for name in names:
        p=directory/name;info=p.lstat()
        need(not p.is_symlink() and stat.S_ISREG(info.st_mode)
             and info.st_uid==UID and info.st_nlink==1
             and stat.S_IMODE(info.st_mode)==0o400 and 0<info.st_size<150000,
             "FINANCIAL_POLICY_STAGE_FILE_UNTRUSTED")
        files[name]=p.read_bytes()
    plan=json.loads(files["manifest.json"])
    keys={"schema_version","action","source_sha","rollback_sha",
          "pmv4_catalog_policy_sha","financial_candidate_sha","financial_image_id",
          "freeze_sha256","baseline_sha256","target_sha256",
          "root_script_sha256","scope_sha256","one_use",
          "provider_mutations","protected_service_restarts","new_containers_started"}
    need(isinstance(plan,dict) and set(plan)==keys
         and plan["schema_version"]=="1.0" and plan["action"]==ACTION
         and re.fullmatch("[a-f0-9]{40}",plan["source_sha"])
         and plan["rollback_sha"]==LKG
         and plan["pmv4_catalog_policy_sha"]==PMV4_SOURCE
         and plan["financial_candidate_sha"]==FINANCIAL_SOURCE
         and plan["financial_image_id"]==FINANCIAL_IMAGE
         and plan["freeze_sha256"]==FREEZE_SHA
         and plan["baseline_sha256"]==BASE_SHA
         and plan["target_sha256"]==TARGET_SHA
         and plan["root_script_sha256"]==digest(files[SRC_FILE])
         and plan["one_use"] is True and plan["provider_mutations"]==0
         and plan["protected_service_restarts"] is False
         and plan["new_containers_started"] is False,
         "FINANCIAL_POLICY_SCOPE_NOT_EXACT")
    scope=dict(plan);scope.pop("scope_sha256")
    need(plan["scope_sha256"]==digest(canonical(scope)),
         "FINANCIAL_POLICY_SCOPE_HASH_MISMATCH")
    need(digest(files["baseline.json"])==BASE_SHA
         and digest(files["candidate.json"])==TARGET_SHA
         and candidate(files["baseline.json"])==files["candidate.json"],
         "FINANCIAL_POLICY_DIFF_NOT_SINGLE_CONTAINER")
    return plan,files

def root_owner(directory,plan):
    info=SIGNER.lstat()
    need(info.st_uid==0 and stat.S_ISREG(info.st_mode)
         and not SIGNER.is_symlink() and not (info.st_mode&0o022)
         and digest(SIGNER.read_bytes())==SIGNER_SHA,
         "FINANCIAL_POLICY_SIGNER_DRIFT")
    spec=importlib.util.spec_from_file_location("finance_policy_owner",SIGNER)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    receipt=json.loads((directory/OWNER_FILE).read_bytes())
    need(set(receipt)=={"schema_version","action","manifest_sha256","signed_owner_proof"}
         and receipt["schema_version"]=="1.0" and receipt["action"]==ACTION
         and receipt["manifest_sha256"]==digest(canonical(plan)),
         "FINANCIAL_POLICY_OWNER_SCOPE_NOT_EXACT")
    pub=module.read_pinned_root_owner_public_key(PUBLIC,require_root_owned=True)
    payload=module.verify_exact_owner_release(
        receipt["signed_owner_proof"],public_key=pub,
        expected_candidate_sha=plan["source_sha"],
        expected_rollback_sha=LKG,
        expected_release_id="release-"+plan["source_sha"][:16],
        expected_scope_sha256=plan["scope_sha256"],
        expected_manifest_sha256=digest(canonical(plan)),
        expected_freeze_sha256=FREEZE_SHA,
        at=datetime.now(timezone.utc))
    return payload["approval_id"]

def strict_root_bytes(path,mode=0o600):
    info=path.lstat()
    need(not path.is_symlink() and stat.S_ISREG(info.st_mode)
         and info.st_uid==0 and info.st_nlink==1
         and stat.S_IMODE(info.st_mode)==mode and 0<info.st_size<=262144,
         "FINANCIAL_POLICY_ROOT_FILE_UNTRUSTED")
    return path.read_bytes()

def inspect(name):
    x=json.loads(subprocess.check_output(
        ["/usr/bin/docker","inspect",name],text=True,timeout=20))[0]
    need(x["State"]["Running"],"FINANCIAL_POLICY_PROTECTED_CONTAINER_DOWN")
    return x["Id"],x["Image"],x["State"]["StartedAt"]

def gate():
    need(os.geteuid()==0 and sys.flags.isolated==1,
         "FINANCIAL_POLICY_PINNED_ROOT_REQUIRED")
    need(Path("/opt/jason/current").resolve(strict=True).name==LKG
         and digest(FREEZE.read_bytes())==FREEZE_SHA,
         "FINANCIAL_POLICY_PRODUCTION_LKG_OR_FREEZE_CHANGED")
    need(digest(strict_root_bytes(ROOT_POLICY))==BASE_SHA,
         "FINANCIAL_POLICY_CURRENT_BASELINE_NOT_APPROVED")
    record=json.loads(strict_root_bytes(
        CAT_AUDIT/(PMV4_SOURCE+"-accepted.json")))
    need(record.get("status")=="four_unit_catalog_policy_reconciled"
         and record.get("candidate_policy_sha256")==BASE_SHA
         and record.get("watchdog")=="pass",
         "FINANCIAL_POLICY_CATALOG_RECONCILE_NOT_COMPLETE")
    state=json.loads(CONTROL.read_bytes())
    drift=json.loads(DRIFT.read_bytes())
    need(state.get("circuit_breaker",{}).get("state")=="closed"
         and drift.get("status")=="pass" and drift.get("problems")==[],
         "FINANCIAL_POLICY_BREAKER_OR_DRIFT_NOT_PASS")
    need(not LEDGER.exists() and not LEDGER.is_symlink(),
         "FINANCIAL_POLICY_ONE_USE_ALREADY_ATTEMPTED")
    image=json.loads(subprocess.check_output(
        ["/usr/bin/docker","image","inspect",FINANCIAL_IMAGE],
        text=True,timeout=20))[0]
    need(image.get("Id")==FINANCIAL_IMAGE
         and image.get("Config",{}).get("Labels",{}).get(
             "com.aot.jason.source_revision")==FINANCIAL_SOURCE,
         "FINANCIAL_POLICY_REVIEWED_IMAGE_NOT_PRESENT")
    need(not subprocess.check_output(
        ["/usr/bin/docker","ps","-a","--filter",
         "label=com.docker.compose.project=jason-financial-statements",
         "--format","{{.Names}}"],text=True,timeout=15).strip(),
         "FINANCIAL_COMPONENT_ALREADY_DEPLOYED")
    return {name:inspect(name) for name in PROTECTED}

def lock():
    files=[]
    for path,owner in ((NATIVE_LOCK,1000),(PMV4_LOCK,0)):
        fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
        st=os.fstat(fd)
        need(st.st_uid==owner and stat.S_ISREG(st.st_mode)
             and not (st.st_mode&0o002),
             "FINANCIAL_POLICY_NATIVE_LOCK_UNTRUSTED")
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            for earlier in files:os.close(earlier)
            raise Denied("FINANCIAL_POLICY_NATIVE_RELEASE_BUSY")
        files.append(fd)
    return files

def unlock(held):
    for fd in reversed(held):os.close(fd)

def record(path,value):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|
               getattr(os,"O_NOFOLLOW",0),0o600)
    with os.fdopen(fd,"wb") as out:
        out.write(json.dumps(value,sort_keys=True,indent=2).encode()+b"\n")
        out.flush();os.fsync(out.fileno())

def atomic_replace(content):
    need(ROOT_POLICY.parent.is_dir()
         and ROOT_POLICY.parent.lstat().st_uid==0
         and not ROOT_POLICY.parent.is_symlink()
         and not (ROOT_POLICY.parent.lstat().st_mode&0o022),
         "FINANCIAL_POLICY_PARENT_UNTRUSTED")
    fd,temp=tempfile.mkstemp(dir=ROOT_POLICY.parent,prefix=".finance-policy-")
    try:
        with os.fdopen(fd,"wb") as out:
            out.write(content);out.flush();os.fsync(out.fileno())
        os.chown(temp,0,0,follow_symlinks=False)
        os.chmod(temp,0o600)
        os.replace(temp,ROOT_POLICY)
        n=os.open(ROOT_POLICY.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(n)
        finally:os.close(n)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    need(digest(strict_root_bytes(ROOT_POLICY))==digest(content),
         "FINANCIAL_POLICY_ROOT_ATOMIC_READBACK_FAIL")

def watchdog_pass():
    since=time.time()
    child=subprocess.run(
        ["/usr/bin/systemctl","start","jason-production-drift-watchdog.service"],
        capture_output=True,text=True,timeout=135)
    need(child.returncode==0,
         "FINANCIAL_POLICY_NATIVE_WATCHDOG_FAILED")
    readback=json.loads(DRIFT.read_bytes())
    need(readback.get("status")=="pass"
         and readback.get("problems")==[]
         and DRIFT.stat().st_mtime>=since-2,
         "FINANCIAL_POLICY_NATIVE_DRIFT_NOT_FRESH_PASS")

def unchanged(before):
    need(before=={name:inspect(name) for name in PROTECTED},
         "FINANCIAL_POLICY_PROTECTED_CONTAINERS_CHANGED")
    need(Path("/opt/jason/current").resolve(strict=True).name==LKG
         and digest(FREEZE.read_bytes())==FREEZE_SHA,
         "FINANCIAL_POLICY_FREEZE_OR_LKG_CHANGED")
    need(json.loads(CONTROL.read_bytes())
         .get("circuit_breaker",{}).get("state")=="closed",
         "FINANCIAL_POLICY_BREAKER_OPENED_DURING_ACTION")

def execute(directory):
    need(os.geteuid()==0 and sys.flags.isolated==1,
         "FINANCIAL_POLICY_ISOLATED_ROOT_REQUIRED")
    manifest,files=stage(directory,with_proof=True)
    need(digest(Path(__file__).read_bytes())==manifest["root_script_sha256"],
         "FINANCIAL_POLICY_EXECUTED_ROOT_SOURCE_UNREVIEWED")
    approval=root_owner(directory,manifest)
    previous=gate()
    held=lock()
    before=files["baseline.json"]
    target=files["candidate.json"]
    outcome={
        "schema_version":"1.0","action":ACTION,
        "source_sha":manifest["source_sha"],
        "scope_sha256":manifest["scope_sha256"],
        "approval_id":approval,
        "status":"failed_closed",
        "baseline_sha256":BASE_SHA,"target_sha256":TARGET_SHA,
        "financial_container_started":False,
        "protected_services_unchanged":False,
        "production_freeze_unchanged":False,
        "catalog_recovery_units_preserved":True,
        "started_at":datetime.now(timezone.utc).isoformat(),
    }
    changed=False
    try:
        gate()
        LEDGER.mkdir(mode=0o700,exist_ok=False)
        record(LEDGER/"attempt.json",outcome)
        fd=os.open(LEDGER/"baseline.json",os.O_WRONLY|os.O_CREAT|os.O_EXCL,
                   0o600)
        with os.fdopen(fd,"wb") as f:
            f.write(before);f.flush();os.fsync(f.fileno())
        need(digest((LEDGER/"baseline.json").read_bytes())==BASE_SHA,
             "FINANCIAL_POLICY_BACKUP_READBACK_FAILED")
        need(digest(strict_root_bytes(ROOT_POLICY))==BASE_SHA,
             "FINANCIAL_POLICY_BASELINE_CHANGED_UNDER_LOCK")
        atomic_replace(target)
        changed=True
        unlock(held)
        held=[]
        watchdog_pass()
        time.sleep(13)
        watchdog_pass()
        unchanged(previous)
        need(digest(strict_root_bytes(ROOT_POLICY))==TARGET_SHA,
             "FINANCIAL_POLICY_TARGET_DRIFT")
        outcome["status"]="verified"
        outcome["protected_services_unchanged"]=True
        outcome["production_freeze_unchanged"]=True
    except BaseException:
        try:
            if LEDGER.exists() and (LEDGER/"baseline.json").exists():
                live=digest(strict_root_bytes(ROOT_POLICY))
                need(live in (BASE_SHA,TARGET_SHA),
                     "FINANCIAL_POLICY_UNRELATED_CONCURRENT_WRITE")
                if live==TARGET_SHA:
                    if held:
                        atomic_replace(before)
                    else:
                        again=lock()
                        try:
                            need(digest(strict_root_bytes(ROOT_POLICY))==TARGET_SHA,
                                 "FINANCIAL_POLICY_ROLLBACK_RACE")
                            atomic_replace(before)
                        finally:unlock(again)
                outcome["rollback"]="exact_baseline_restored"
            else:outcome["rollback"]="no_production_mutation"
        except BaseException:
            outcome["rollback"]="failed_closed_unverified"
        raise
    finally:
        if held:unlock(held)
        outcome["finished_at"]=datetime.now(timezone.utc).isoformat()
        if LEDGER.exists():
            record(LEDGER/"result.json",outcome)
    print("FINANCIAL_ROOT_CONTAINER_POLICY=DECLARED_VERIFIED")
    print("FINANCIAL_COMPONENT_RUNNING=FALSE")
    print("NATIVE_WATCHDOG=PASS")
    print("PROTECTED_RUNTIME_MCP_PMV4=UNCHANGED")
    print("PRODUCTION_FREEZE=UNCHANGED")
    print("OWNER_ONE_USE_APPROVAL=CONSUMED")

def main():
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--packet",type=Path,required=True)
    group=ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--check-only",action="store_true")
    group.add_argument("--host-preflight",action="store_true")
    group.add_argument("--execute",action="store_true")
    args=ap.parse_args()
    if args.check_only:
        stage(args.packet)
        print("FINANCIAL_ROOT_POLICY_SOURCE_SCOPE=PASS")
        print("PRODUCTION_MUTATIONS=False")
    elif args.host_preflight:
        plan,_=stage(args.packet)
        need(os.geteuid()==0 and sys.flags.isolated==1,
             "FINANCIAL_POLICY_HOST_PREFLIGHT_ROOT_REQUIRED")
        need(digest(Path(__file__).read_bytes())==plan["root_script_sha256"],
             "FINANCIAL_POLICY_ROOT_PREFLIGHT_HASH_DRIFT")
        observed=gate()
        print("FINANCIAL_ROOT_POLICY_HOST_PREFLIGHT=PASS")
        print("PROTECTED_RUNNING="+str(len(observed)))
        print("PRODUCTION_MUTATIONS=False")
    else:
        execute(args.packet)

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("FINANCIAL_CONTAINER_POLICY_DENIED:"+type(exc).__name__+
              (":"+str(exc)[:120] if isinstance(exc,Denied) else ":DETAILS_REDACTED"),
              file=sys.stderr)
        raise SystemExit(2)
