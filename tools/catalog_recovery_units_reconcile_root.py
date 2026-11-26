#!/usr/bin/env python3
"""One-use signed removal of four *idle* unlisted catalog recovery systemd units.

Not a general repair or waiver. Requires independent exact Entra Owner proof,
root-owned trusted source, exclusive native release locks, the precise
undeclared-unit incident, no pending catalog promotion/transactions, and fresh
native watchdog PASS before using the native breaker revalidation operation.
Catalog root/source stays installed, but catalog promotions fail closed until
their recovery units are properly declared in a future protected release.
"""
from __future__ import annotations
from datetime import datetime, timezone
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
import time

ACTION="owner-catalog-recovery-unit-conflict-reconcile-20261117"
LKG="d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
SOURCE_CATALOG="01ba71c54d9dd0391734b16a92d0b292fc457ae9"
FREEZE_SHA="bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
DESIRED_SHA="835fcb669cbc433e569797a5882d84ddf1dd206aadba56fbed180bce4ceda3e5"
SIGNER_SHA="f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3"
SOURCE_FILE="catalog_recovery_units_reconcile_root.py"
ROOT_SYSTEMD=Path("/etc/systemd/system")
ROOT_AUDIT=Path("/etc/jason-owner-release/catalog-recovery-units-reconcile-ledger")
SOURCE_ROOT=Path("/home/al/.local/share/jason")
ROOT_OWNER=Path("/etc/jason-owner-release/verified-owner-public-key.json")
SIGNER=Path("/usr/local/lib/jason/owner_signed_release.py")
FREEZE=Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
DESIRED=Path("/opt/jason/current/config/production-desired-state.json")
CONTROL=Path("/var/lib/jason/openclaw/release-manager/protected-readback/production-control-state.json")
DRIFT=Path("/var/lib/jason/openclaw/release-manager/protected-readback/production-drift.json")
CATALOG_STATE=Path("/var/lib/jason-catalog-scoped-promotion")
CATALOG_ROOT_POLICY=Path("/etc/jason-owner-release/catalog-scoped-promotion-installed.json")
CATALOG_BOOTSTRAP_POLICY=Path("/etc/jason-owner-release/catalog-scoped-root-bootstrap-trust.json")
NATIVE_LOCK=Path("/var/lib/jason/openclaw/release-manager/production-transaction.lock")
PMV4_LOCK=Path("/var/lib/jason/pmv4-shadow/control/host-mutation.lock")
UNITS={
    "jason-catalog-root-bootstrap-recovery.service":"a0547e546279a976443c7df75cbdfb44b3b28c22db422bfb6dac7c56fc71126c",
    "jason-catalog-root-bootstrap-recovery.timer":"b0136ee08188f16aad42c504585a43354ec68266cc238042f563aa168bbe3c44",
    "jason-catalog-scoped-recovery.service":"23c01396da6c62b22ba3d89fd9196d88a0a21d408d2381cd518332de929e1a06",
    "jason-catalog-scoped-recovery.timer":"41ab29fe56a3d5b454fd323e25f36ab49cacc2fcc6c074e052a6d2a35bc0f2fe",
}
TIMERS=tuple(sorted(x for x in UNITS if x.endswith(".timer")))
SERVICES=tuple(sorted(x for x in UNITS if x.endswith(".service")))
PROTECTED=("jason-runtime","jason-mcp-pilot","jason-pmv4-shadow-gateway",
           "jason-teams-gateway","openbao")
ROOT_STAGE_UID=1000
GATE_REASON="undeclared_installed_system_unit"
CHECK_FRESH_SECONDS=30

class Denied(PermissionError):
    pass

def need(ok, reason):
    if not ok:raise Denied(reason)

def digest(raw):
    return sha256(raw).hexdigest()

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      allow_nan=False,ensure_ascii=False).encode()

def stage(directory, require_proof=False):
    need(directory.parent==SOURCE_ROOT
         and re.fullmatch("catalog-units-reconcile-[0-9a-f]{12}",directory.name)
         and directory.is_dir() and not directory.is_symlink()
         and directory.lstat().st_uid==ROOT_STAGE_UID
         and stat.S_IMODE(directory.lstat().st_mode)==0o700,
         "CATALOG_RECONCILE_STAGING_UNTRUSTED")
    expected={"manifest.json",SOURCE_FILE}
    if require_proof:expected.add("owner-proof.json")
    elif (directory/"owner-proof.json").exists():expected.add("owner-proof.json")
    need({p.name for p in directory.iterdir()}==expected,
         "CATALOG_RECONCILE_STAGE_SET_CHANGED")
    data={}
    for name in expected:
        p=directory/name
        st=p.lstat()
        need(not p.is_symlink() and stat.S_ISREG(st.st_mode)
             and st.st_uid==ROOT_STAGE_UID and st.st_nlink==1
             and stat.S_IMODE(st.st_mode)==0o400
             and 0<st.st_size<150000,
             "CATALOG_RECONCILE_STAGE_FILE_UNTRUSTED")
        data[name]=p.read_bytes()
    manifest=json.loads(data["manifest.json"])
    allowed={
        "schema_version","action","source_sha","rollback_sha",
        "catalog_source_sha","freeze_sha256","desired_sha256",
        "unit_sha256","root_source_sha256","scope_sha256","one_use",
        "catalog_root_controls_removed","systemd_units_removed",
        "protected_service_restarts","financial_scheduler_activation",
    }
    need(isinstance(manifest,dict) and set(manifest)==allowed
         and manifest["schema_version"]=="1.0"
         and manifest["action"]==ACTION
         and re.fullmatch("[a-f0-9]{40}",manifest["source_sha"])
         and manifest["rollback_sha"]==LKG
         and manifest["catalog_source_sha"]==SOURCE_CATALOG
         and manifest["freeze_sha256"]==FREEZE_SHA
         and manifest["desired_sha256"]==DESIRED_SHA
         and manifest["unit_sha256"]==UNITS
         and manifest["one_use"] is True
         and manifest["catalog_root_controls_removed"] is False
         and manifest["systemd_units_removed"]==sorted(UNITS)
         and manifest["protected_service_restarts"] is False
         and manifest["financial_scheduler_activation"] is False
         and manifest["root_source_sha256"]==digest(data[SOURCE_FILE]),
         "CATALOG_RECONCILE_ACTION_NOT_EXACT")
    without=dict(manifest);without.pop("scope_sha256")
    need(manifest["scope_sha256"]==digest(canonical(without)),
         "CATALOG_RECONCILE_SCOPE_HASH_MISMATCH")
    return manifest,data

def signature(directory,manifest):
    m=SIGNER.lstat()
    need(m.st_uid==0 and stat.S_ISREG(m.st_mode)
         and not SIGNER.is_symlink() and not (m.st_mode&0o022)
         and digest(SIGNER.read_bytes())==SIGNER_SHA,
         "CATALOG_RECONCILE_ROOT_OWNER_VERIFIER_CHANGED")
    spec=importlib.util.spec_from_file_location("catalog_reconcile_owner",SIGNER)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    signed=json.loads((directory/"owner-proof.json").read_bytes())
    need(set(signed)=={"schema_version","action","manifest_sha256",
                       "signed_owner_proof"}
         and signed["schema_version"]=="1.0" and signed["action"]==ACTION
         and signed["manifest_sha256"]==digest(canonical(manifest)),
         "CATALOG_RECONCILE_OWNER_PROOF_NOT_EXACT")
    pub=mod.read_pinned_root_owner_public_key(
        ROOT_OWNER,require_root_owned=True)
    proof=mod.verify_exact_owner_release(
        signed["signed_owner_proof"],public_key=pub,
        expected_candidate_sha=manifest["source_sha"],
        expected_rollback_sha=LKG,
        expected_release_id="release-"+manifest["source_sha"][:16],
        expected_scope_sha256=manifest["scope_sha256"],
        expected_manifest_sha256=digest(canonical(manifest)),
        expected_freeze_sha256=FREEZE_SHA,
        at=datetime.now(timezone.utc))
    return proof["approval_id"]

def json_file(path):
    return json.loads(path.read_bytes())

def system(*args,timeout=80):
    p=subprocess.run(["/usr/bin/systemctl",*args],
                     capture_output=True,text=True,timeout=timeout)
    need(p.returncode==0,"CATALOG_RECONCILE_SYSTEMD_DENIED:"+args[0])
    return p.stdout.strip()

def inspect(name):
    x=json.loads(subprocess.check_output(
        ["/usr/bin/docker","inspect",name],text=True,timeout=25))[0]
    need(x["State"]["Running"],"CATALOG_RECONCILE_PROTECTED_DOWN:"+name)
    return x["Id"],x["Image"],x["State"]["StartedAt"]

def protected_baseline():
    return {x:inspect(x) for x in PROTECTED}

def verified_host():
    need(os.geteuid()==0 and sys.flags.isolated==1,
         "CATALOG_RECONCILE_ISOLATED_ROOT_REQUIRED")
    need(Path("/opt/jason/current").resolve(strict=True).name==LKG,
         "CATALOG_RECONCILE_PRODUCTION_REVISION_CHANGED")
    need(digest(FREEZE.read_bytes())==FREEZE_SHA
         and digest(DESIRED.read_bytes())==DESIRED_SHA,
         "CATALOG_RECONCILE_PRODUCTION_POLICY_CHANGED")
    desired=json_file(DESIRED)
    allowable=set(desired["required_system_units"]+desired["allowed_system_units"])
    need(not set(UNITS)&allowable,
         "CATALOG_RECONCILE_UNITS_NOW_DECLARED")
    control=json_file(CONTROL)
    drift=json_file(DRIFT)
    need(control.get("circuit_breaker",{}).get("state")=="open"
         and drift.get("status")=="drift_detected"
         and sorted(drift.get("problems") or [],key=lambda x:x.get("unit",""))
          ==sorted([{"kind":GATE_REASON,"state":"active" if n in TIMERS else "inactive","unit":n}
                    for n in UNITS],key=lambda x:x["unit"]),
         "CATALOG_RECONCILE_INCIDENT_CHANGED")
    for p in (CATALOG_ROOT_POLICY,CATALOG_BOOTSTRAP_POLICY):
        info=p.lstat()
        need(not p.is_symlink() and stat.S_ISREG(info.st_mode)
             and info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o600,
             "CATALOG_RECONCILE_CURRENT_OWNER_TRUST_MISSING")
    for p in (CATALOG_STATE,CATALOG_STATE/"transactions",CATALOG_STATE/"offers"):
        info=p.lstat()
        need(p.is_dir() and not p.is_symlink() and info.st_uid==0
             and stat.S_IMODE(info.st_mode)==0o700,
             "CATALOG_RECONCILE_TRANSACTION_ROOT_UNTRUSTED")
    need(not any((CATALOG_STATE/"transactions").iterdir())
         and not any((CATALOG_STATE/"offers").iterdir()),
         "CATALOG_RECONCILE_ACTIVE_OR_PENDING_CATALOG_RELEASE")
    for name,expected in UNITS.items():
        p=ROOT_SYSTEMD/name;info=p.lstat()
        need(not p.is_symlink() and stat.S_ISREG(info.st_mode)
             and info.st_uid==0 and stat.S_IMODE(info.st_mode)==0o644
             and digest(p.read_bytes())==expected,
             "CATALOG_RECONCILE_INSTALLED_UNIT_DRIFT:"+name)
        state=system("show",name,"--property=ActiveState","--value")
        need(state==("active" if name in TIMERS else "inactive"),
             "CATALOG_RECONCILE_UNIT_ACTIVE_STATE_CHANGED:"+name)
        if name in TIMERS:
            need(system("is-enabled",name)=="enabled",
                 "CATALOG_RECONCILE_TIMER_NOT_ENABLED")
    return protected_baseline()

def lock():
    held=[]
    for path,uid in ((NATIVE_LOCK,1000),(PMV4_LOCK,0)):
        fd=os.open(path,os.O_RDONLY|getattr(os,"O_NOFOLLOW",0))
        st=os.fstat(fd)
        need(stat.S_ISREG(st.st_mode) and st.st_uid==uid
             and not (st.st_mode&0o002),
             "CATALOG_RECONCILE_NATIVE_LOCK_UNTRUSTED")
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BaseException:
            os.close(fd)
            for other in held:os.close(other)
            raise Denied("CATALOG_RECONCILE_NATIVE_RELEASE_BUSY")
        held.append(fd)
    return held

def unlock(held):
    for fd in reversed(held):os.close(fd)

def receipt(path,value):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|
               getattr(os,"O_NOFOLLOW",0),0o600)
    with os.fdopen(fd,"wb") as out:
        out.write(json.dumps(value,sort_keys=True,indent=2).encode()+b"\n")
        out.flush();os.fsync(out.fileno())

def backup():
    dest=ROOT_AUDIT/"unit-backups"
    dest.mkdir(mode=0o700)
    for n in UNITS:
        original=(ROOT_SYSTEMD/n).read_bytes()
        fd=os.open(dest/n,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"wb") as out:
            out.write(original)
            out.flush();os.fsync(out.fileno())
        need(digest((dest/n).read_bytes())==UNITS[n],
             "CATALOG_RECONCILE_BACKUP_READBACK_FAIL")

def revert():
    # Reinstall only exact saved files when a later step fails. Never touch
    # unrelated production units. Keep root incident auditable, fail closed.
    for n in UNITS:
        p=ROOT_SYSTEMD/n
        if p.exists():
            need(digest(p.read_bytes())==UNITS[n],
                 "CATALOG_RECONCILE_ROLLBACK_UNIT_DRIFT")
        else:
            blob=(ROOT_AUDIT/"unit-backups"/n).read_bytes()
            need(digest(blob)==UNITS[n],"CATALOG_RECONCILE_BACKUP_DRIFT")
            fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644)
            with os.fdopen(fd,"wb") as out:
                out.write(blob);out.flush();os.fsync(out.fileno())
    system("daemon-reload")
    for n in TIMERS:
        system("enable","--now",n)
    need(all(digest((ROOT_SYSTEMD/n).read_bytes())==UNITS[n] for n in UNITS),
         "CATALOG_RECONCILE_ROLLBACK_NOT_VERIFIED")

def remove_only_units():
    for n in TIMERS:system("disable","--now",n)
    for n in UNITS:
        p=ROOT_SYSTEMD/n
        need(digest(p.read_bytes())==UNITS[n],"CATALOG_RECONCILE_RACE")
        p.unlink()
    system("daemon-reload")
    need(all(not (ROOT_SYSTEMD/n).exists() for n in UNITS),
         "CATALOG_RECONCILE_UNITS_PERSIST_AFTER_REMOVE")
    for n in TIMERS:
        state=system("show",n,"--property=ActiveState","--value")
        need(state!="active","CATALOG_RECONCILE_TIMER_STILL_ACTIVE")

def check_clean_watchdog():
    since=time.time()
    system("reset-failed","jason-production-drift-watchdog.service")
    system("start","jason-production-drift-watchdog.service",timeout=135)
    x=json_file(DRIFT)
    need(x.get("status")=="pass" and x.get("problems")==[]
         and DRIFT.stat().st_mtime>=since-2,
         "CATALOG_RECONCILE_NATIVE_DRIFT_NOT_FRESH_PASS")

def verify_protected(before):
    need(protected_baseline()==before,
         "CATALOG_RECONCILE_PROTECTED_CONTAINER_CHANGED")
    need(digest(FREEZE.read_bytes())==FREEZE_SHA
         and digest(DESIRED.read_bytes())==DESIRED_SHA,
         "CATALOG_RECONCILE_PRODUCTION_FREEZE_OR_POLICY_CHANGED")

def native_revalidate():
    # Native release manager handles protected transition: never write breaker.
    snippet=(
        "from pathlib import Path;"
        "import sys;"
        "sys.path.insert(0,'/home/al/.local/lib/jason');"
        "import release_manager_host_runner as r;"
        "r.revalidate_circuit_breaker("
        "Path('/var/lib/jason/openclaw/release-manager'))"
    )
    process=subprocess.run([
        "/usr/sbin/runuser","-u","al","--","/usr/bin/python3",
        "-c",snippet],capture_output=True,text=True,timeout=145)
    need(process.returncode==0,
         "CATALOG_RECONCILE_NATIVE_BREAKER_REVALIDATION_DENIED")
    actual=json_file(CONTROL).get("circuit_breaker",{})
    need(actual.get("state")=="closed"
         and actual.get("reason")=="root_verified_revalidate",
         "CATALOG_RECONCILE_NATIVE_BREAKER_STILL_OPEN")

def execute(directory):
    need(os.geteuid()==0 and sys.flags.isolated==1,
         "CATALOG_RECONCILE_ISOLATED_ROOT_REQUIRED")
    manifest,blobs=stage(directory,require_proof=True)
    need(digest(Path(__file__).read_bytes())==manifest["root_source_sha256"]
         and digest(blobs[SOURCE_FILE])==manifest["root_source_sha256"],
         "CATALOG_RECONCILE_EXECUTED_ROOT_CODE_NOT_PINNED")
    approval=signature(directory,manifest)
    need(not ROOT_AUDIT.exists() and not ROOT_AUDIT.is_symlink(),
         "CATALOG_RECONCILE_ONE_USE_ALREADY_ATTEMPTED")
    previous=verified_host()
    held=lock()
    outcome={
        "action":ACTION,"status":"failed_closed",
        "source_sha":manifest["source_sha"],
        "scope_sha256":manifest["scope_sha256"],
        "catalog_installer_source_sha":SOURCE_CATALOG,
        "owner_approval_id":approval,
        "catalog_root_controls_preserved":True,
        "catalog_promotions_suspended_until_native_declaration":True,
        "financial_component_activated":False,
        "native_breaker_closed":False,
        "protected_services_unchanged":False,
        "freeze_unchanged":False,
        "started_at":datetime.now(timezone.utc).isoformat(),
    }
    mutated=False
    try:
        verified_host()
        ROOT_AUDIT.mkdir(mode=0o700,exist_ok=False)
        receipt(ROOT_AUDIT/"attempt.json",outcome)
        backup()
        remove_only_units()
        mutated=True
        verify_protected(previous)
        unlock(held)
        held=[]
        # Watchdog skips host checks during the lock: require post-lock PASS.
        check_clean_watchdog()
        time.sleep(14)
        check_clean_watchdog()
        native_revalidate()
        verify_protected(previous)
        outcome["status"]="verified"
        outcome["native_breaker_closed"]=True
        outcome["protected_services_unchanged"]=True
        outcome["freeze_unchanged"]=True
    except BaseException:
        try:
            if ROOT_AUDIT.exists() and (ROOT_AUDIT/"unit-backups").is_dir():
                revert()
                outcome["unit_rollback"]="restored_exact_original_bytes"
            else:
                outcome["unit_rollback"]="no_units_backed_up"
        except BaseException:
            outcome["unit_rollback"]="incomplete_fail_closed"
        raise
    finally:
        if held:unlock(held)
        outcome["finished_at"]=datetime.now(timezone.utc).isoformat()
        if ROOT_AUDIT.exists():
            receipt(ROOT_AUDIT/"result.json",outcome)
    print("CATALOG_UNDECLARED_UNITS=REMOVED_WITH_EXACT_OWNER_PROOF")
    print("CATALOG_ROOT_CONTROLS=RETAINED_NO_PROMOTIONS")
    print("NATIVE_DRIFT=PASS")
    print("NATIVE_BREAKER=CLOSED")
    print("PROTECTED_RUNTIME_MCP_PMV4=UNCHANGED")
    print("PRODUCTION_FREEZE=UNCHANGED")
    print("FINANCIAL_COMPONENT=NOT_ACTIVATED")

def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--packet",type=Path,required=True)
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check-only",action="store_true")
    modes.add_argument("--host-preflight",action="store_true")
    modes.add_argument("--execute",action="store_true")
    args=parser.parse_args()
    if args.check_only:
        stage(args.packet,require_proof=False)
        print("CATALOG_RECONCILE_EXACT_SOURCE_AND_SCOPE=PASS")
        print("ROOT_MUTATION=NOT_PERFORMED")
    elif args.host_preflight:
        manifest,files=stage(args.packet,require_proof=False)
        need(digest(Path(__file__).read_bytes())==manifest["root_source_sha256"],
             "CATALOG_RECONCILE_ROOT_PREFLIGHT_HASH_DRIFT")
        before=verified_host()
        need(len(before)==len(PROTECTED),
             "CATALOG_RECONCILE_PROTECTED_BASELINE_INCOMPLETE")
        print("ROOT_HOST_INCIDENT_AND_IDLE_CATALOG_PREFLIGHT=PASS")
        print("PROTECTED_CONTAINERS="+str(len(before)))
        print("ROOT_MUTATION=NOT_PERFORMED")
    else:execute(args.packet)

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("CATALOG_RECONCILE_ROOT_DENIED:"+type(exc).__name__+
              (":"+str(exc)[:160] if isinstance(exc,Denied) else ":DETAILS_REDACTED"),
              file=sys.stderr)
        raise SystemExit(2)
