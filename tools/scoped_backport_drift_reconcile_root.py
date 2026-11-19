#!/usr/bin/env python3
"""One-use, signed Owner recovery for four independently approved scoped-backport units.

Do not turn off the drift guard, enable a provider write, reboot, restart Ticket
Core/MCP or touch the production freeze. Root policy reconciliation only.
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
import stat
import subprocess
import sys
import tempfile

ACTION="scoped-backport-four-unit-drift-policy-reconcile-v1"
CANDIDATE_NAMES=(
 "jason-scoped-backport-recovery.service",
 "jason-scoped-backport-recovery.timer",
 "jason-scoped-backport-requests.path",
 "jason-scoped-backport-requests.service",
)
# SHA256s independently matched installed root-owned units to protected Git
# at source 6adc19744fc7464ef3ba34d1ce0b3b20e9e69684.
PINNED_UNIT_SHA256={
    'jason-scoped-backport-recovery.service': 'd91a129e3783554ecb87b72e076353c7c90cd64856a4b0187ee8c5a5ad9b1cde',
    'jason-scoped-backport-recovery.timer': 'e15b3973791625a5d817a1892eaf11a6b1ac60cffe86f419cea33a930d56c4fd',
    'jason-scoped-backport-requests.path': '5ed31ef5b204a436a07ed9dfd268f82484242ae4656c813bc287bce0b9a8aa34',
    'jason-scoped-backport-requests.service': 'f9cbc38b2612466dee9a603197ee9484d11f2468f744c31140f1ba5683c2a40d',
}
ROOT_POLICY=Path("/etc/jason/release-readback-recovery/production-desired-state.json")
FREEZE=Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
HOLD=Path("/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold")
CURRENT=Path("/opt/jason/current")
AUDIT=Path("/etc/jason-owner-release/scoped-backport-unit-drift-reconciliation")
LOCK=Path("/var/lib/jason/openclaw/release-manager/production-transaction.lock")
TRUSTED_SIGNER=Path("/usr/local/lib/jason/owner_signed_release.py")
TRUSTED_SIGNER_SHA="f50eea90102d9a1de82b3753ec8d0cd225280d385ac7a658ae2c2a303934a0e3"
PUBLIC=Path("/etc/jason-owner-release/verified-owner-public-key.json")
STAGE_PARENT=Path("/run")

class CatalogDriftDenied(PermissionError):
    pass

def need(ok, reason):
    if not ok: raise CatalogDriftDenied("SCOPED_BACKPORT_DRIFT_"+reason)

def digest(raw):
    return sha256(raw).hexdigest()

def canon(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()

def file_bytes(path, *, uid=0, mode=None, limit=262144):
    need(not path.is_symlink(), "SYMLINK:"+path.name)
    meta=path.lstat()
    need(stat.S_ISREG(meta.st_mode) and meta.st_uid==uid and meta.st_nlink==1
         and (mode is None or stat.S_IMODE(meta.st_mode)==mode)
         and meta.st_size <= limit,"FILE_UNTRUSTED:"+path.name)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        return os.read(fd,limit+1)
    finally: os.close(fd)

def expected_policy(raw):
    p=json.loads(raw)
    need(isinstance(p,dict) and p.get("schema_version")=="1.0", "BASE_SCHEMA")
    allowed=p.get("allowed_system_units")
    need(isinstance(allowed,list) and len(allowed)==len(set(allowed))
         and not any(item in allowed for item in CANDIDATE_NAMES),
         "BASE_SCOPED_BACKPORT_UNITS_NOT_MISSING")
    need(p.get("max_stopped_rollback_containers")==21,
         "UNEXPECTED_ROLLBACK_CAPACITY")
    p["allowed_system_units"]=sorted(allowed+list(CANDIDATE_NAMES))
    return p

def plan_from(packet):
    need(os.geteuid()==0 and sys.flags.isolated==1,"ROOT_ISOLATED_REQUIRED")
    p=Path(packet)
    data=json.loads(p.read_text())
    need(isinstance(data,dict) and data.get("schema_version")=="1.0"
         and data.get("action")==ACTION
         and data.get("owner_consents")==1
         and data.get("standing_authority") is False
         and data.get("later_stages_authorized") is False
         and data.get("production_mutations")==["root_scoped_backport_four_unit_allowlist","watchdog_oneshot","native_root_breaker_revalidation","restore_exact_baseline_on_failure","one_use_audit_receipts"]
         and data.get("scoped_backport_unit_names")==list(CANDIDATE_NAMES)
         and data.get("restart_containers")==[]
         and data.get("source_sha") and len(data["source_sha"])==40
         and data.get("candidate_sha")==data.get("source_sha")
         and all(x in "0123456789abcdef" for x in data["source_sha"]),
         "SCOPE_INVALID")
    scope=data.get("scope_sha256")
    unsigned=dict(data);unsigned.pop("scope_sha256",None)
    need(digest(canon(unsigned))==scope,"SCOPE_HASH_INVALID")
    need(p.name=="root-release-plan.json" and
         p.parent==Path("/srv/jason/archive/engineering-artifacts")/
            ("scoped-backport-drift-"+data["source_sha"]),
         "ARTIFACT_PATH_UNTRUSTED")
    return p,data

def inspect(plan_path):
    packet,plan=plan_from(plan_path)
    stage=STAGE_PARENT/("jason-scoped-backport-drift-"+plan["source_sha"][:12])
    exe=stage/"root.py"
    need(Path(__file__).resolve()==exe and stage.lstat().st_uid==0
         and stat.S_IMODE(stage.lstat().st_mode)==0o700
         and digest(file_bytes(exe,mode=0o400))==plan["root_sha256"],
         "ROOT_EXECUTOR_UNTRUSTED")
    need(digest(file_bytes(ROOT_POLICY,mode=0o600))==
         plan["baseline_policy_sha256"], "PROTECTED_POLICY_BASELINE_CHANGED")
    base=file_bytes(packet.parent/"baseline.json",uid=1000,mode=0o400)
    target=file_bytes(packet.parent/"candidate.json",uid=1000,mode=0o400)
    need(digest(base)==plan["baseline_policy_sha256"] and
         digest(target)==plan["candidate_policy_sha256"] and
         canon(expected_policy(base))==canon(json.loads(target)),
         "CANDIDATE_POLICY_NOT_FOUR_UNIT_ONLY")
    need(CURRENT.resolve(strict=True).name==plan["rollback_sha"] and
         digest(file_bytes(FREEZE,uid=1000))==plan["freeze_sha256"] and
         digest(file_bytes(HOLD,uid=1000))==plan["hold_sha256"],
         "PRODUCTION_BASELINE_CHANGED")
    for name in CANDIDATE_NAMES:
        unit=Path("/etc/systemd/system")/name
        observed=digest(file_bytes(unit,mode=0o444))
        need(observed==PINNED_UNIT_SHA256[name]
             and plan["unit_file_sha256"][name]==PINNED_UNIT_SHA256[name],
             "REVIEWED_SCOPED_BACKPORT_UNIT_CHANGED:"+name)
    need(not AUDIT.joinpath(plan["source_sha"]+"-accepted.json").exists()
         and not AUDIT.joinpath(plan["source_sha"]+"-attempt.json").exists(),
         "SIGNED_POLICY_ACTION_ALREADY_CONSUMED")
    # The protected production breaker may legitimately be OPEN because of
    # these exact undeclared names. Do NOT close or bypass it.
    current=run_guard(ROOT_POLICY)
    allowed={("undeclared_installed_system_unit",n) for n in CANDIDATE_NAMES}
    allowed.add(("failed_system_unit","jason-production-drift-watchdog.service"))
    problems=current["problems"]
    need(current["status"]=="drift_detected" and
         len(problems)>=4 and
         { (z.get("kind"),z.get("unit")) for z in problems }.issubset(allowed) and
         {("undeclared_installed_system_unit",n) for n in CANDIDATE_NAMES}.issubset(
             { (z.get("kind"),z.get("unit")) for z in problems }),
         "UNRELATED_LIVE_DRIFT_PRESENT")
    return packet,plan

def run_guard(config):
    run=subprocess.run(["/usr/bin/python3",str(CURRENT/"tools/production_drift_guard.py"),
                        "--config",str(config)],capture_output=True,text=True,timeout=60)
    need(run.returncode in (0,2) and len(run.stdout)<131072,"GUARD_EXECUTION_INVALID")
    obj=json.loads(run.stdout)
    need(obj.get("schema_version")=="1.0" and
         isinstance(obj.get("problems"),list),"GUARD_FORMAT_INVALID")
    return obj

def verified_owner(packet,plan):
    proof_path=packet.parent/"root-oneowner-proof.json"
    proof=json.loads(file_bytes(proof_path,uid=1000,mode=0o400))
    need(proof.get("action")==ACTION and proof.get("source_sha")==plan["source_sha"]
         and proof.get("scope_sha256")==plan["scope_sha256"]
         and proof.get("plan_sha256")==digest(canon(plan)),
         "SIGNED_OWNER_PLAN_MISMATCH")
    digest_bytes=file_bytes(TRUSTED_SIGNER,mode=0o644)
    need(digest(digest_bytes)==TRUSTED_SIGNER_SHA,
         "INSTALLED_SIGNER_CHANGED")
    spec=importlib.util.spec_from_file_location("catalog_drift_trusted_signer",TRUSTED_SIGNER)
    need(spec is not None and spec.loader is not None,"SIGNER_UNAVAILABLE")
    signer=importlib.util.module_from_spec(spec);spec.loader.exec_module(signer)
    public=signer.read_pinned_root_owner_public_key(PUBLIC)
    bound=signer.verify_exact_owner_release(
        proof["signed_release"],public_key=public,at=datetime.now(timezone.utc),
        expected_candidate_sha=plan["source_sha"],
        expected_rollback_sha=plan["rollback_sha"],
        expected_release_id="release-"+plan["source_sha"][:16],
        expected_scope_sha256=plan["scope_sha256"],
        expected_manifest_sha256=digest(canon(plan)),
        expected_freeze_sha256=plan["freeze_sha256"])
    need(bound["approval_id"]==proof["approval_id"],
         "OWNER_SIGNATURE_INVALID")
    return proof["approval_id"]

@contextmanager
def lock_transaction():
    fd=os.open(LOCK,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        meta=os.fstat(fd)
        need(stat.S_ISREG(meta.st_mode) and meta.st_uid==1000,
             "TRANSACTION_LOCK_UNTRUSTED")
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)

def atomic_policy(payload):
    meta=ROOT_POLICY.lstat()
    need(meta.st_uid==0 and meta.st_gid==0 and stat.S_IMODE(meta.st_mode)==0o600,
         "ROOT_POLICY_OWNER_CHANGED")
    fd,tmp=tempfile.mkstemp(dir=ROOT_POLICY.parent,prefix=".scoped-backport-drift-")
    try:
        with os.fdopen(fd,"wb") as out:
            out.write(payload);out.flush();os.fsync(out.fileno())
        os.chown(tmp,0,0);os.chmod(tmp,0o600)
        os.replace(tmp,ROOT_POLICY)
        directory_fd=os.open(ROOT_POLICY.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory_fd)
        finally:os.close(directory_fd)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def durable(root, data):
    fd=os.open(root,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"wb") as out:
        out.write(canon(data));out.flush();os.fsync(out.fileno())


def apply(path):
    packet,plan=inspect(path)
    approval=verified_owner(packet,plan)
    accepted=AUDIT/(plan["source_sha"]+"-accepted.json")
    attempted=AUDIT/(plan["source_sha"]+"-attempt.json")
    AUDIT.mkdir(mode=0o700,parents=True,exist_ok=True)
    need(AUDIT.lstat().st_uid==0 and stat.S_IMODE(AUDIT.lstat().st_mode)==0o700,
         "AUDIT_DIRECTORY_UNTRUSTED")
    with lock_transaction():
        inspect(path)
        # Construct the bytes directly from the protected root baseline under
        # the production transaction lock. Never use mutable packet bytes
        # after the last hash check (TOCTOU prevention).
        baseline=file_bytes(ROOT_POLICY,mode=0o600)
        need(digest(baseline)==plan["baseline_policy_sha256"],
             "POLICY_CHANGED_UNDER_LOCK")
        candidate=(json.dumps(expected_policy(baseline),indent=2,sort_keys=True)+"\n").encode()
        need(digest(candidate)==plan["candidate_policy_sha256"],
             "SIGNED_TARGET_CHANGED_UNDER_LOCK")
        # One-use audit record BEFORE any policy mutation, so an interrupted
        # or failed release can never consume its Owner signature twice.
        durable(attempted,{
            "schema_version":"1.0","source_sha":plan["source_sha"],
            "approval_id":approval,"action":ACTION,
            "scope_sha256":plan["scope_sha256"],
            "baseline_policy_sha256":plan["baseline_policy_sha256"],
            "candidate_policy_sha256":plan["candidate_policy_sha256"],
            "state":"consumed_before_production_mutation",
            "recorded_at":datetime.now(timezone.utc).isoformat()})
        atomic_policy(candidate)
    try:
        # The only service action is the existing watchdog one-shot.
        # No Ticket Core/MCP restarts or catalog timer changes.
        watchdog=subprocess.run(["/usr/bin/systemctl","start",
                                 "jason-production-drift-watchdog.service"],
                                 capture_output=True,text=True,timeout=90)
        observed=run_guard(ROOT_POLICY)
        need(watchdog.returncode==0 and observed["status"]=="pass"
             and observed["problems"]==[],
             "NATIVE_WATCHDOG_DID_NOT_VERIFY_AFTER_CONFIG_UPDATE")
        need(digest(file_bytes(FREEZE,uid=1000))==plan["freeze_sha256"] and
             CURRENT.resolve(strict=True).name==plan["rollback_sha"],
             "PROTECTED_PRODUCTION_CHANGED")
        # The existing native operator -> root transition is mandatory.
        # The Release Manager checks its LKG source under uid 1000; running
        # that client as root would fail its identity/source alignment check.
        trusted_runner=CURRENT/"tools/release_manager_host_runner.py"
        need(digest(file_bytes(trusted_runner,mode=0o664,limit=600000))==
             "7208832ecb575d549721788f196f85c7d6bd609794680fe099f6ff60401626a9",
             "NATIVE_OPERATOR_REVALIDATOR_CHANGED")
        snippet=(
            "from pathlib import Path;import sys;"
            "sys.path.insert(0,'/opt/jason/current/tools');"
            "import release_manager_host_runner as r;"
            "r.revalidate_circuit_breaker("
            "Path('/var/lib/jason/openclaw/release-manager'))"
        )
        result=subprocess.run([
            "/usr/sbin/runuser","-u","al","--",
            "/usr/bin/python3","-I","-c",snippet],
            capture_output=True,text=True,timeout=145)
        need(result.returncode==0,"NATIVE_BREAKER_REVALIDATION_DENIED")
        protected=json.loads(file_bytes(Path(
            "/var/lib/jason/openclaw/release-manager/production-control-state.json"),
            mode=0o600,limit=131072))
        breaker=protected.get("circuit_breaker") or {}
        need(breaker.get("state")=="closed"
             and breaker.get("reason")=="root_verified_revalidate"
             and breaker.get("revalidated_revision")==plan["rollback_sha"],
             "ROOT_NATIVE_BREAKER_CLOSEOUT_UNVERIFIED")
    except BaseException:
        # Exact automatic rollback is part of the SAME Owner scope, not a
        # second approval or unrelated mutation. Never clobber another root
        # release's changed policy.
        with lock_transaction():
            live=digest(file_bytes(ROOT_POLICY,mode=0o600))
            if live==plan["candidate_policy_sha256"]:
                atomic_policy(baseline)
            else:
                need(live==plan["baseline_policy_sha256"],
                     "CONCURRENT_ROOT_POLICY_CHANGED_NO_ROLLBACK")
        raise
    receipt={
       "schema_version":"1.0","status":"four_unit_scoped_backport_policy_reconciled",
       "action":ACTION,"source_sha":plan["source_sha"],"owner_approval_id":approval,
       "scope_sha256":plan["scope_sha256"],
       "baseline_policy_sha256":plan["baseline_policy_sha256"],
       "candidate_policy_sha256":plan["candidate_policy_sha256"],
       "added_allowed_system_units":list(CANDIDATE_NAMES),
       "watchdog":"pass","breaker_override":False,"native_breaker_revalidated":True,
       "ticket_core_restarts":0,"mcp_restarts":0,
       "completed_at":datetime.now(timezone.utc).isoformat(),
    }
    durable(accepted,receipt)
    print("SCOPED_BACKPORT_FOUR_UNIT_DRIFT_POLICY_RECONCILED=PASS",flush=True)
    print("PRODUCTION_BREAKER_REVALIDATED_NATIVELY=true",flush=True)
    print("TICKET_CORE_AND_MCP_UNCHANGED=true",flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--plan",required=True,type=Path)
    x=p.add_mutually_exclusive_group(required=True)
    x.add_argument("--preflight",action="store_true")
    x.add_argument("--execute",action="store_true")
    a=p.parse_args()
    try:
        if a.preflight:
            _,plan=inspect(a.plan)
            print("SCOPED_BACKPORT_EXACT_FOUR_UNIT_ROOT_PREFLIGHT=PASS")
            print("SOURCE_SHA="+plan["source_sha"])
            print("SCOPE_SHA256="+plan["scope_sha256"])
            print("ROOT_POLICY_WRITES=false; OWNER_PROOF_CONSUMED=false")
        else: apply(a.plan)
        return 0
    except BaseException as exc:
        print("SCOPED_BACKPORT_DRIFT_RECONCILE_DENIED="+type(exc).__name__+":"+str(exc)[:145],
              file=sys.stderr,flush=True)
        return 2
if __name__=="__main__":
    raise SystemExit(main())
