#!/usr/bin/env python3
"""One-time Owner-authenticated REAL full SQLite integrity proof recovery.

This is an emergency evidence repair, not a release promotion, waiver, restored
stale PASS, or generic root maintenance tool. It cannot run without fresh
Microsoft Entra JWT-bound Owner authorization and exact root-pinned sources.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import pwd
import shutil
import signal
import stat
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ACTION = "owner-full-sqlite-integrity-proof-90m-recovery-v1"
ROOT_SCRIPT = Path("/usr/local/lib/jason/owner_full_integrity_recovery.py")
SOURCE_DIR = Path("/usr/local/lib/jason/full-integrity-recovery-20261112")
SNAPSHOT = SOURCE_DIR / "openclaw_authority_health_snapshot.py"
CHECKER = SOURCE_DIR / "openclaw_authority_operational_health.py"
OWNER_HELPER = Path("/usr/local/lib/jason/owner_signer_recovery.py")
POLICY = Path("/etc/jason-owner-release/full-integrity-recovery-policy.json")
AUDIT = Path("/etc/jason-owner-release/full-integrity-recovery-ledger")
FREEZE = Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
CONTROL = Path("/var/lib/jason/openclaw/release-manager/production-control-state.json")
DRIFT = Path("/var/lib/jason/openclaw/release-manager/production-drift.json")
LOCK = Path("/var/lib/jason/openclaw/release-manager/production-transaction.lock")
FULL = Path("/var/lib/jason/openclaw/operational-full-health.json")
FAST = Path("/var/lib/jason/openclaw/operational-health.json")
ADVISORY = Path("/var/lib/jason/openclaw/owner-emergency-health-advisory.json")
HEALTH_SERVICE = "jason-openclaw-authority-health.service"
DRIFT_SERVICE = "jason-production-drift-watchdog.service"
FULL_SERVICE = "jason-openclaw-authority-full-integrity.service"
LKG = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
RUNTIME_IMAGE = "sha256:c43f9f7364a4b2b16bdec261fa35db2b861eabe959ba818f689582bbb1b7d132"
MCP_IMAGE = "sha256:b2f74bf1513568f6c9df7a2ffa764b1a5f43303c8317702741d646f223db1477"
FREEZE_SHA = "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
DURATION = 5400
SUPERVISOR_SECONDS = 5700
APPROVAL_SCOPE = "single read-only 90-minute full SQLite integrity/authority backup proof, gated service health recovery, native root revalidation"
AL_UID = 1000

class RecoveryDenied(PermissionError):
    pass


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def secure_file(path: Path, size: int = 524288) -> bytes:
    if path.is_symlink():
        raise RecoveryDenied("SYMLINK_SOURCE_DENIED")
    parent = path.parent.lstat()
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != 0
            or stat.S_IMODE(parent.st_mode) & 0o022):
        raise RecoveryDenied("ROOT_PARENT_UNSAFE")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        s = os.fstat(fd)
        if (not stat.S_ISREG(s.st_mode) or s.st_uid != 0
                or stat.S_IMODE(s.st_mode) & 0o022 or s.st_size > size):
            raise RecoveryDenied("ROOT_SOURCE_UNSAFE")
        raw = os.read(fd, size + 1)
        if len(raw) != s.st_size:
            raise RecoveryDenied("ROOT_SOURCE_LENGTH_CHANGED")
        return raw
    finally:
        os.close(fd)


def source_verification() -> dict:
    data = json.loads(secure_file(POLICY))
    expected = {
        "schema_version": "1.0", "exact_action": ACTION,
        "one_shot": True, "lkg_sha": LKG,
        "runtime_image": RUNTIME_IMAGE, "mcp_image": MCP_IMAGE,
        "freeze_sha256": FREEZE_SHA, "scan_timeout_seconds": DURATION,
        "supervisor_timeout_seconds": SUPERVISOR_SECONDS,
        "scope": APPROVAL_SCOPE, "source_script_sha256": data.get("source_script_sha256"),
        "snapshot_sha256": data.get("snapshot_sha256"),
        "checker_sha256": data.get("checker_sha256"),
        "trusted_owner_auth_sha256": data.get("trusted_owner_auth_sha256"),
    }
    if data != expected:
        raise RecoveryDenied("ROOT_EXACT_POLICY_SHAPE_MISMATCH")
    for path, key in (
        (ROOT_SCRIPT, "source_script_sha256"),
        (SNAPSHOT, "snapshot_sha256"),
        (CHECKER, "checker_sha256"),
        (OWNER_HELPER, "trusted_owner_auth_sha256"),
    ):
        if len(str(data[key])) != 64 or digest(secure_file(path)) != data[key]:
            raise RecoveryDenied("ROOT_PINNED_EXECUTABLE_HASH_MISMATCH")
    return data


def docker(name: str) -> dict:
    r = subprocess.run(["docker", "inspect", name], capture_output=True, text=True,
                       check=True, timeout=12)
    a = json.loads(r.stdout)
    if not isinstance(a, list) or len(a) != 1:
        raise RecoveryDenied("DOCKER_INSPECT_SHAPE")
    return a[0]


def host_identity() -> dict:
    if Path("/opt/jason/current").resolve(strict=True) != Path("/opt/jason/releases") / LKG:
        raise RecoveryDenied("HOST_LKG_CHANGED")
    runtime = docker("jason-runtime")
    mcp = docker("jason-mcp-pilot")
    if (runtime.get("Image") != RUNTIME_IMAGE
            or mcp.get("Image") != MCP_IMAGE
            or runtime.get("State", {}).get("Health", {}).get("Status") != "healthy"
            or mcp.get("State", {}).get("Status") != "running"):
        raise RecoveryDenied("DOCKER_IMAGE_OR_HEALTH_CHANGED")
    for x in (runtime, mcp):
        if x.get("Config", {}).get("Labels", {}).get(
                "com.teamaot.jason.source_revision") != LKG:
            raise RecoveryDenied("DOCKER_REVISION_CHANGED")
    if digest(FREEZE.read_bytes()) != FREEZE_SHA:
        raise RecoveryDenied("PRODUCTION_FREEZE_CHANGED")
    signer = [x for x in mcp.get("Mounts", []) if
              x.get("Destination") == "/run/jason-secrets/owner-release/private_key"
              and x.get("Source") == "/var/lib/jason/runtime-secrets/owner-release/private_key"
              and x.get("RW") is False]
    if len(signer) != 1:
        raise RecoveryDenied("OWNER_SIGNER_MOUNT_UNAVAILABLE")
    return {"runtime_id": runtime["Id"], "mcp_id": mcp["Id"]}


def protected_json(path: Path) -> dict:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_uid != 0 or stat.S_IMODE(s.st_mode) != 0o600:
            raise RecoveryDenied("PROTECTED_EVIDENCE_UNTRUSTED")
        payload = os.read(fd, 256 * 1024 + 1)
        if len(payload) > 256 * 1024:
            raise RecoveryDenied("PROTECTED_EVIDENCE_TOO_LARGE")
        return json.loads(payload)
    finally:
        os.close(fd)


def show_unit(name: str) -> str:
    r = subprocess.run(["systemctl", "show", name, "-p", "ActiveState",
                        "--value"],capture_output=True,text=True,check=True,timeout=15)
    return r.stdout.strip()


def preflight() -> dict:
    current = host_identity()
    control = protected_json(CONTROL)
    drift = protected_json(DRIFT)
    lkg = (control.get("last_known_good") or {}).get("manifest") or {}
    expected = {"revision":LKG,"host_revision":LKG,
                "runtime_revision":LKG,"mcp_revision":LKG,
                "runtime_image_id":RUNTIME_IMAGE,"mcp_image_id":MCP_IMAGE}
    for k,v in expected.items():
        if lkg.get(k) != v:
            raise RecoveryDenied("PROTECTED_LKG_IDENTITY_MISMATCH:" + k)
    breaker = control.get("circuit_breaker") or {}
    if breaker.get("state") != "open" or breaker.get("source") != "production_drift_watchdog":
        raise RecoveryDenied("EXACT_OPEN_BREAKER_NOT_OBSERVED")
    allowed = {("failed_system_unit","jason-openclaw-authority-health.service"),
               ("failed_system_unit","jason-grafana-assurance.service")}
    problems = drift.get("problems")
    observed = {(x.get("kind"),x.get("unit")) for x in problems or []
                if isinstance(x,dict)}
    if (drift.get("status") != "drift_detected"
            or ("failed_system_unit",HEALTH_SERVICE) not in observed
            or observed - allowed
            or len(observed) != len(problems or [])):
        raise RecoveryDenied("UNRELATED_DRIFT_DENIED")
    file = FULL.stat()
    actual = json.loads(FULL.read_text())
    if (not stat.S_ISREG(file.st_mode) or file.st_uid != AL_UID
            or stat.S_IMODE(file.st_mode) != 0o600
            or actual.get("status") != "fail"
            or actual.get("failures") != ["operational_health_timeout"]
            or actual.get("snapshot_source_exit_code") != 124):
        raise RecoveryDenied("NOT_A_PREVIOUS_FULL_PROOF_TIMEOUT")
    if show_unit(HEALTH_SERVICE) != "failed" or show_unit(FULL_SERVICE) == "active":
        raise RecoveryDenied("EXPECTED_HEALTH_SERVICE_STATE_NOT_FOUND")
    if (show_unit("jason-openclaw-authority-full-integrity.timer") != "active"
            or show_unit("jason-openclaw-authority-health.timer") != "active"):
        raise RecoveryDenied("EXISTING_HEALTH_TIMERS_NOT_ACTIVE")
    fs = shutil.disk_usage("/srv/jason/archive")
    if fs.free < 24 * (1024 ** 3):
        raise RecoveryDenied("ARCHIVE_CAPACITY_INSUFFICIENT")
    if list(AUDIT.glob(ACTION + ".*")):
        raise RecoveryDenied("ONE_SHOT_ALREADY_CONSUMED")
    return current


def owner_verifier():
    spec = importlib.util.spec_from_file_location("pinned_owner", str(OWNER_HELPER))
    if spec is None or spec.loader is None:
        raise RecoveryDenied("TRUSTED_OWNER_HELPER_UNAVAILABLE")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.trusted_signer()
    return m


def interactive_exact_owner(helper) -> str:
    base = "https://login.microsoftonline.com/" + helper.TENANT + "/oauth2/v2.0/"
    c = helper._form(base + "devicecode", {
        "client_id": helper.CLIENT_ID, "scope": helper.SCOPE,
    })
    if not all(isinstance(c.get(k), str) for k in (
            "device_code", "user_code", "verification_uri")):
        raise RecoveryDenied("OWNER_DEVICE_CHALLENGE_UNAVAILABLE")
    ttl = min(int(c.get("expires_in",0)),600)
    if ttl < 60:
        raise RecoveryDenied("OWNER_DEVICE_CHALLENGE_EXPIRED")
    print("EXACT_ACTION=" + ACTION, flush=True)
    print("ONE_FULL_INTEGRITY_CHECK_SECONDS_MAX=" + str(DURATION), flush=True)
    print("READ_ONLY_SQLITE_AND_TEMP_ARCHIVE_BACKUP=true", flush=True)
    print("MAY_CONSUME_HOST_CPU_DISK_FOR_UP_TO_90_MINUTES=true", flush=True)
    print("NO_RELEASE_OR_FREEZE_CHANGE=true", flush=True)
    print("BROWSER_VERIFICATION_URL=" + c["verification_uri"], flush=True)
    print("SIGN_IN_CODE=" + c["user_code"], flush=True)
    interval = max(5, min(20,int(c.get("interval",5))))
    deadline = time.monotonic()+ttl
    while time.monotonic() < deadline:
        time.sleep(interval)
        t=helper._form(base+"token",{
            "grant_type":"urn:ietf:params:oauth:grant-type:device_code",
            "client_id":helper.CLIENT_ID,"device_code":c["device_code"],
        })
        if isinstance(t.get("access_token"),str):
            return helper.jwt_owner(t["access_token"])
        if t.get("error") == "authorization_pending":
            continue
        if t.get("error") == "slow_down":
            interval=min(20,interval+5);continue
        raise RecoveryDenied("OWNER_EXACT_AUTHORIZATION_DENIED")
    raise RecoveryDenied("OWNER_EXACT_AUTHORIZATION_EXPIRED")


def root_record(path: Path, result: dict) -> None:
    data=(json.dumps(result,sort_keys=True,separators=(",",":"))+"\n").encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        os.fchown(fd,0,0)
        os.write(fd,data)
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def production_lock():
    fd=os.open(LOCK,os.O_RDWR|os.O_NOFOLLOW)
    try:
        s=os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_mode&0o002:
            raise RecoveryDenied("NATIVE_TRANSACTION_LOCK_UNSAFE")
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as e:raise RecoveryDenied("PRODUCTION_BUSY") from e
        try:yield
        finally:fcntl.flock(fd,fcntl.LOCK_UN)
    finally:os.close(fd)


def valid_full_proof(since: float) -> dict:
    s=FULL.stat()
    if (not stat.S_ISREG(s.st_mode) or stat.S_IMODE(s.st_mode) != 0o600
            or s.st_uid != AL_UID or s.st_mtime < since):
        raise RecoveryDenied("FRESH_FULL_PROOF_FILE_NOT_TRUSTED")
    r=json.loads(FULL.read_text(encoding="utf-8"))
    if (r.get("status") != "pass" or r.get("failures") != []
            or r.get("snapshot_source_exit_code") != 0
            or r.get("provider_contacted") is not False
            or r.get("provider_credentials_used") is not False):
        raise RecoveryDenied("COMPLETE_FULL_INTEGRITY_PASS_MISSING")
    for name,path in {
        "authority":"/var/lib/jason/authority/authority.sqlite3",
        "replay":"/var/lib/jason/openclaw/replay.sqlite3",
        "security_audit":"/var/lib/jason/openclaw/security-audit.sqlite3",
        "orchestration_audit":"/var/lib/jason/openclaw/orchestration-events.sqlite3",
    }.items():
        f=(r.get("files") or {}).get(name) or {}
        if (f.get("path") != path or f.get("present") is not True
                or f.get("mode") != "0o600" or f.get("integrity") != "ok"):
            raise RecoveryDenied("SQLITE_FILE_INTEGRITY_UNVERIFIED:" + name)
    b=r.get("backup_restore_proof") or {}
    if not (b.get("backup_integrity")=="ok"
            and b.get("restore_integrity")=="ok"
            and b.get("backup_mode")=="0o600"
            and b.get("restore_mode")=="0o600"
            and b.get("counts_match") is True):
        raise RecoveryDenied("AUTHORITY_BACKUP_RESTORE_PROOF_UNVERIFIED")
    keys=r.get("trusted_key_registry") or {}
    if (keys.get("present") is not True or keys.get("mode")!="0o600"
            or int(keys.get("active_records",0))<1):
        raise RecoveryDenied("TRUSTED_KEY_REGISTRY_PROOF_FAILED")
    if (r.get("delegations") or {}).get("expired_active_records",1)!=0:
        raise RecoveryDenied("EXPIRED_ACTIVE_AUTHORITY_DELEGATION")
    return {"integrity":True,"backup_restore":True,"full_result_recorded":True}


def terminate_scan_process_group(proc) -> None:
    # The real proof runs in its own session so an interrupted Owner terminal
    # cannot orphan the 36GB SQLite read/backup worker and its children.
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=20)


def recover_once() -> None:
    if os.geteuid()!=0 or sys.flags.isolated!=1:
        raise RecoveryDenied("ROOT_ISOLATED_PYTHON_REQUIRED")
    if Path(__file__).resolve(strict=True)!=ROOT_SCRIPT:
        raise RecoveryDenied("ROOT_INSTALLED_EXECUTABLE_REQUIRED")
    policy=source_verification()
    ledger=AUDIT.lstat()
    if (AUDIT.is_symlink() or ledger.st_uid!=0
            or stat.S_IMODE(ledger.st_mode)!=0o700):
        raise RecoveryDenied("ROOT_ONE_SHOT_LEDGER_UNSAFE")
    first=preflight()
    helper=owner_verifier()
    oid=interactive_exact_owner(helper)
    helper.trusted_signer()
    second=preflight()
    if second!=first:
        raise RecoveryDenied("LIVE_PRODUCTION_CHANGED_DURING_OWNER_AUTHORIZATION")
    with production_lock():
        third=preflight()
        if third!=first:
            raise RecoveryDenied("PRODUCTION_CHANGED_BEFORE_ONE_SHOT")
        start=time.time()
        root_record(AUDIT/(ACTION+".attempt.json"),{
            "schema_version":"1.0","exact_action":ACTION,
            "when_utc":datetime.now(timezone.utc).isoformat(),
            "owner_oid":oid,"script_sha256":policy["source_script_sha256"],
            "prior_runtime":first["runtime_id"],"prior_mcp":first["mcp_id"],
            "freeze_sha256":FREEZE_SHA,"one_shot":True,
            "standing_authority":False,"status":"claimed_before_full_proof",
        })
    record={"schema_version":"1.0","exact_action":ACTION,"status":"failed",
            "integrity_proof":False,"breaker_closed":False,
            "when_utc":datetime.now(timezone.utc).isoformat()}
    try:
        # The new source is a byte-pinned, root-owned copy of the EXACT
        # all-four-DB full SQLite checker merged into protected main.
        # Run as al at idle IO and lowest ordinary CPU scheduling priority.
        command=[
            "runuser","-u","al","--",
            "/usr/bin/ionice","-c","3",
            "/usr/bin/nice","-n","19",
            "/usr/bin/python3","-I",str(SNAPSHOT),
            "--output",str(FULL),
        ]
        proc=subprocess.Popen(
            command, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True,
        )
        old_term_handler=signal.getsignal(signal.SIGTERM)
        def interrupted(signum, frame):
            raise RecoveryDenied("FULL_PROOF_INTERRUPTED")
        signal.signal(signal.SIGTERM,interrupted)
        try:
            try:
                returncode=proc.wait(timeout=SUPERVISOR_SECONDS)
            except subprocess.TimeoutExpired:
                terminate_scan_process_group(proc)
                raise RecoveryDenied("REAL_FULL_INTEGRITY_SUPERVISOR_TIMEOUT")
            except BaseException:
                terminate_scan_process_group(proc)
                raise
        finally:
            signal.signal(signal.SIGTERM,old_term_handler)
        if returncode != 0:
            raise RecoveryDenied("REAL_FULL_INTEGRITY_PROOF_DID_NOT_PASS")
        record.update(valid_full_proof(start))
        record["integrity_proof"]=True
        with production_lock():
            if host_identity() != first:
                raise RecoveryDenied("PRODUCTION_CHANGED_DURING_FULL_PROOF")
            # Only after independently verifying genuine PASS is it allowed
            # to clear the stale failed *status* and run existing check units.
            subprocess.run(["systemctl","reset-failed",HEALTH_SERVICE],check=True,timeout=20)
            subprocess.run(["systemctl","start",HEALTH_SERVICE],check=True,timeout=90)
            fast=json.loads(FAST.read_text(encoding="utf-8"))
            if fast.get("status")!="pass" or fast.get("failures")!=[]:
                raise RecoveryDenied("FIVE_MINUTE_READ_HEALTH_NOT_VERIFIED")
        # The existing drift watchdog deliberately defers while the native
        # production lock is held. Release it BEFORE running the watchdog;
        # only a real independent drift PASS can allow root revalidation.
        subprocess.run(["systemctl","reset-failed",DRIFT_SERVICE],check=True,timeout=20)
        subprocess.run(["systemctl","start",DRIFT_SERVICE],check=True,timeout=90)
        actual=protected_json(DRIFT)
        if actual.get("status")!="pass" or actual.get("problems")!=[]:
            raise RecoveryDenied("ROOT_DESIRED_STATE_STILL_DRIFTED")
        # The normal existing al -> root-controlled transition revalidates
        # actual manifest and drift again. Never write root breaker state here.
        code=(
            "import sys;from pathlib import Path;"
            "sys.path.insert(0,'/home/al/.local/lib/jason');"
            "import release_manager_host_runner as r;"
            "r.revalidate_circuit_breaker(Path('/var/lib/jason/openclaw/release-manager'))"
        )
        subprocess.run(["runuser","-u","al","--","/usr/bin/python3","-c",code],
                       check=True,timeout=95,capture_output=True)
        control=protected_json(CONTROL)
        if (control.get("circuit_breaker",{}).get("state")!="closed"
                or (control.get("last_known_good",{}).get("manifest",{})
                    .get("revision"))!=LKG or host_identity()!=first):
            raise RecoveryDenied("ROOT_PRODUCTION_REVALIDATION_NOT_CONVERGED")
        record["breaker_closed"]=True
        record["status"]="verified"
    except Exception as exc:
        record["failure_type"]=type(exc).__name__
        record["failure_code"]=str(exc)[:120] if isinstance(exc,RecoveryDenied) else "NATIVE_RECOVERY_STEP_FAILED"
        raise
    finally:
        record["ended_at"]=datetime.now(timezone.utc).isoformat()
        root_record(AUDIT/(ACTION+".result.json"),record)
    print("REAL_SQLITE_INTEGRITY_PROOF=PASS")
    print("AUTHORITY_BACKUP_RESTORE=PASS")
    print("ROOT_BREAKER_CLOSED=VERIFIED")
    print("TICKET_RUNTIME_AND_MCP_UNCHANGED=true")
    print("FREEZE_UNCHANGED=true")
    print("OWNER_AUTH=verified_entra_oauth")


def main() -> int:
    parser=argparse.ArgumentParser()
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-only",action="store_true")
    mode.add_argument("--execute",action="store_true")
    args=parser.parse_args()
    try:
        if args.check_only:
            if os.geteuid()==0:
                source_verification(); preflight()
                print("ROOT_REAL_INTEGRITY_RECOVERY_PREFLIGHT=PASS")
            else:
                if Path("/opt/jason/current").resolve()!=Path("/opt/jason/releases")/LKG:
                    raise RecoveryDenied("NONROOT_BASELINE_MISMATCH")
                print("NONROOT_SOURCE_ONLY_PREFLIGHT=PASS")
            print("PROOF_RUN_EXECUTED=false")
        else:
            recover_once()
        return 0
    except Exception as exc:
        print("OWNER_FULL_INTEGRITY_RECOVERY=DENIED "+
              type(exc).__name__+":"+
              (str(exc)[:145] if isinstance(exc,RecoveryDenied) else "SENSITIVE_ERROR_REDACTED"),
              file=sys.stderr)
        return 1

if __name__=="__main__":
    raise SystemExit(main())
