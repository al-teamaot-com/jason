#!/usr/bin/env python3
"""One-use, Owner-authenticated correction of an already approved catalog root install.
No image promotion, provider write, service restart, freeze removal, or broad authority.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import pwd
from pathlib import Path
import stat
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from uuid import uuid4

ACTION = "catalog-postinstall-three-blobs-four-units-v1"
CONFIRM = "APPROVE-EXACT-CATALOG-POSTINSTALL-REPAIR-ONLY"
SELF = Path("/root/catalog-postinstall-repair-20261117.py")
BUNDLE = Path("/usr/local/lib/jason/catalog-scoped-promotion")
POLICY = Path("/etc/jason/release-readback-recovery/production-desired-state.json")
ROOT_POLICY = Path("/etc/jason-owner-release/catalog-scoped-promotion-installed.json")
CONTROL = Path("/var/lib/jason/openclaw/release-manager/production-control-state.json")
DRIFT = Path("/var/lib/jason/openclaw/release-manager/production-drift.json")
FREEZE = Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
OWNER = Path("/usr/local/lib/jason/owner_signer_recovery.py")
WORKER = Path("/usr/local/lib/jason/release_host_reconcile_worker.py")
LEDGER = Path("/var/lib/jason-catalog-scoped-promotion/postinstall-repair")
EXPECTED_SOURCE = "01ba71c54d9dd0391734b16a92d0b292fc457ae9"
FREEZE_SHA = "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
WORKER_SHA = "55890d6725cc49c2e70743ced3632a79817267764a1dbaa876bdd9e77a5e8e18"
OWNER_SHA = "24d3632a4b0aa60851a1c82ccb15539eb823dd26afa5a1a2cc8c7afc54d72153"
FILES = (
    ("infrastructure/openclaw-operations/systemd/jason-catalog-scoped-recovery.service",
     "/etc/systemd/system/jason-catalog-scoped-recovery.service",
     "23c01396da6c62b22ba3d89fd9196d88a0a21d408d2381cd518332de929e1a06"),
    ("infrastructure/openclaw-operations/systemd/jason-catalog-scoped-recovery.timer",
     "/etc/systemd/system/jason-catalog-scoped-recovery.timer",
     "41ab29fe56a3d5b454fd323e25f36ab49cacc2fcc6c074e052a6d2a35bc0f2fe"),
    ("tools/pmv4_mcp_projection.py", "/opt/jason/current/tools/pmv4_mcp_projection.py",
     "14cf45ae64a913503e89f97fe508b348a6965c1a70cbeda52397f7eed7c9c235"),
)
UNITS = tuple(sorted((
    "jason-catalog-root-bootstrap-recovery.service",
    "jason-catalog-root-bootstrap-recovery.timer",
    "jason-catalog-scoped-recovery.service",
    "jason-catalog-scoped-recovery.timer",
)))
BUNDLE_DIRS = tuple(BUNDLE / p for p in (
    "infrastructure", "infrastructure/openclaw-operations",
    "infrastructure/openclaw-operations/systemd",
))

def denied(reason):
    raise PermissionError("CATALOG_MINIMAL_REPAIR_DENIED_" + reason)

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def protected_read(path, modes=(0o600, 0o644, 0o755), maximum=250000, owner_uid=0):
    if path.is_symlink():
        denied("SYMLINK_" + path.name)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != owner_uid or
                st.st_nlink != 1 or stat.S_IMODE(st.st_mode) not in modes or
                not 0 < st.st_size <= maximum):
            denied("PROTECTED_FILE_" + path.name)
        raw = os.read(fd, maximum + 1)
        if len(raw) != st.st_size:
            denied("PARTIAL_READ_" + path.name)
        return raw, stat.S_IMODE(st.st_mode)
    finally:
        os.close(fd)

def atomic_root_json(path, value):
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    fd, temp = tempfile.mkstemp(prefix=".catalog-repair-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

def root_dir(path, mode=0o755):
    st = path.lstat()
    if path.is_symlink() or not stat.S_ISDIR(st.st_mode) or st.st_uid != 0 or stat.S_IMODE(st.st_mode) != mode:
        denied("DIRECTORY_TRUST_" + path.name)

def preflight():
    if os.geteuid() != 0 or os.environ.get("SUDO_USER") != "al":
        denied("AUTHENTICATED_HOST_OWNER_REQUIRED")
    st = SELF.lstat()
    if SELF.is_symlink() or not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or stat.S_IMODE(st.st_mode) != 0o500:
        denied("ROOT_OWNED_PINNED_ENTRY_REQUIRED")
    root_dir(BUNDLE)
    root_dir(BUNDLE / "tools")
    root_dir(LEDGER.parent, 0o700)
    frozen, _ = protected_read(FREEZE, modes=(0o600,), maximum=4096, owner_uid=pwd.getpwnam('al').pw_uid)
    if digest(frozen) != FREEZE_SHA:
        denied("FREEZE_MISMATCH")
    worker, _ = protected_read(WORKER, modes=(0o755,), maximum=300000)
    if digest(worker) != WORKER_SHA:
        denied("WORKER_MISMATCH")
    verifier, _ = protected_read(OWNER, modes=(0o555,), maximum=50000)
    if digest(verifier) != OWNER_SHA:
        denied("OWNER_VERIFIER_MISMATCH")
    installed, _ = protected_read(ROOT_POLICY, modes=(0o600,), maximum=8192)
    installed = json.loads(installed)
    if installed.get("source_sha") != EXPECTED_SOURCE or installed.get("root_worker_sha256") != WORKER_SHA:
        denied("CATALOG_INSTALLED_POLICY_MISMATCH")
    if (installed.get("recovery_service_sha256") != FILES[0][2] or
            installed.get("recovery_timer_sha256") != FILES[1][2]):
        denied("ROOT_RECOVERY_UNIT_POLICY_MISMATCH")
    if any(x.exists() or x.is_symlink() for x in BUNDLE_DIRS):
        denied("REPAIR_DIRECTORIES_ALREADY_EXIST")
    copies = {}
    for relative, source, expected in FILES:
        src = Path(source)
        raw, _ = protected_read(src, modes=(0o644, 0o664), maximum=100000)
        if digest(raw) != expected:
            denied("SOURCE_BLOB_DRIFT_" + src.name)
        target = BUNDLE / relative
        if target.exists() or target.is_symlink():
            denied("TARGET_ALREADY_EXISTS_" + target.name)
        copies[target] = raw
    policy_before, mode = protected_read(POLICY, modes=(0o600, 0o644), maximum=100000)
    doc = json.loads(policy_before)
    allowed = doc.get("allowed_system_units")
    if doc.get("schema_version") != "1.0" or not isinstance(allowed, list) or any(not isinstance(x, str) for x in allowed):
        denied("DESIRED_STATE_SCHEMA")
    if len(set(allowed)) != len(allowed) or set(UNITS) & set(allowed):
        denied("DESIRED_STATE_DUPLICATE_OR_ALREADY_REPAIRED")
    doc["allowed_system_units"] = sorted(allowed + list(UNITS))
    policy_after = (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode()
    drift, _ = protected_read(DRIFT, modes=(0o600,), maximum=131072)
    drift = json.loads(drift)
    problems = drift.get("problems")
    expected_problems = {("undeclared_installed_system_unit", unit) for unit in UNITS}
    if drift.get("status") != "drift_detected" or not isinstance(problems, list) or {
            (x.get("kind"), x.get("unit")) for x in problems if isinstance(x, dict)
        } != expected_problems or len(problems) != 4:
        denied("OTHER_PRODUCTION_DRIFT_PRESENT")
    state, _ = protected_read(CONTROL, modes=(0o600,), maximum=131072)
    state = json.loads(state)
    if (state.get("circuit_breaker") or {}).get("state") != "open":
        denied("OPEN_BREAKER_EXPECTED_DURING_RECOVERY")
    for timer in ("jason-catalog-scoped-recovery.timer", "jason-catalog-root-bootstrap-recovery.timer"):
        for action in ("is-enabled", "is-active"):
            x = subprocess.run(("systemctl", action, timer), capture_output=True, text=True, timeout=10)
            if x.returncode or x.stdout.strip() != ("enabled" if action == "is-enabled" else "active"):
                denied("ROOT_RECOVERY_TIMER_INACTIVE")
    return policy_before, policy_after, mode, copies

def fresh_entra_owner():
    spec = importlib.util.spec_from_file_location("catalog_repair_pinned_entra_verifier", OWNER)
    if spec is None or spec.loader is None:
        denied("ENTRA_VERIFIER_LOAD")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    if (helper.TENANT != "f7054323-d52b-4863-8c2f-1898f0b6077c" or
            helper.CLIENT_ID != "9b9996e9-5c34-48b7-948c-f44f89352f89" or
            helper.SCOPE != "https://mcp-jason.teamaot.com/mcp/Jason.Read"):
        denied("OWNER_TENANT_PROFILE_MISMATCH")
    url = "https://login.microsoftonline.com/" + helper.TENANT + "/oauth2/v2.0/"
    challenge = helper._form(url + "devicecode", {"client_id": helper.CLIENT_ID, "scope": helper.SCOPE})
    if not all(isinstance(challenge.get(x), str) for x in ("device_code", "user_code", "verification_uri")):
        denied("OWNER_DEVICE_CHALLENGE")
    expiry = min(int(challenge.get("expires_in", 0)), 600)
    if expiry < 60:
        denied("OWNER_CHALLENGE_TTL")
    print("BROWSER_VERIFICATION_URL=" + challenge["verification_uri"], flush=True)
    print("SIGN_IN_CODE=" + challenge["user_code"], flush=True)
    deadline = time.monotonic() + expiry
    interval = max(5, min(int(challenge.get("interval", 5)), 20))
    while time.monotonic() < deadline:
        time.sleep(interval)
        response = helper._form(url + "token", {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": helper.CLIENT_ID, "device_code": challenge["device_code"],
        })
        if isinstance(response.get("access_token"), str):
            return helper.jwt_owner(response["access_token"])
        if response.get("error") == "slow_down":
            interval = min(interval + 5, 20)
        elif response.get("error") != "authorization_pending":
            denied("OWNER_SIGNIN_REJECTED")
    denied("OWNER_SIGNIN_EXPIRED")

def execute():
    original, changed, original_mode, copies = preflight()
    print("EXACT_ACTION=" + ACTION, flush=True)
    print("INSTALLED_CATALOG_SOURCE_SHA=" + EXPECTED_SOURCE, flush=True)
    print("FREEZE_SHA256=" + FREEZE_SHA, flush=True)
    print("DRIFT_POLICY_BEFORE_SHA256=" + digest(original), flush=True)
    print("DRIFT_POLICY_AFTER_SHA256=" + digest(changed), flush=True)
    print("ADDED_ROOT_FILES=" + str(len(copies)), flush=True)
    print("ALLOWED_SYSTEM_UNIT_ADDITIONS=" + ",".join(UNITS), flush=True)
    print("IMAGE_PROMOTION_APPROVED=false", flush=True)
    print("AUTOTASK_PROVIDER_WRITES_APPROVED=false", flush=True)
    oid = fresh_entra_owner()
    if input("Type " + CONFIRM + " to approve ONLY the listed postinstall repair: ").strip() != CONFIRM:
        denied("EXACT_OWNER_CONSENT_MISSING")
    # Recheck the pinned freeze, root policy, source files and desired-state bytes.
    before_again, after_again, mode_again, copies_again = preflight()
    if before_again != original or after_again != changed or mode_again != original_mode or copies_again != copies:
        denied("PRODUCTION_CHANGED_DURING_OWNER_AUTH")
    if not LEDGER.exists():
        LEDGER.mkdir(mode=0o700)
    root_dir(LEDGER, 0o700)
    approval = "catalog-postinstall-" + uuid4().hex
    record = LEDGER / (approval + ".json")
    backup = LEDGER / (approval + "-before.json")
    intent = {
        "schema": "1.0", "action": ACTION, "approval_id": approval,
        "owner_oid": oid, "approval_text": CONFIRM,
        "source_sha": EXPECTED_SOURCE, "freeze_sha256": FREEZE_SHA,
        "root_file_sha256": {str(path): digest(blob) for path, blob in copies.items()},
        "drift_policy_before_sha256": digest(original),
        "drift_policy_after_sha256": digest(changed),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "owner_approved_before_mutation",
        "production_images_changed": False, "provider_writes": False,
    }
    # Durable approval evidence and rollback bytes before changing any installed path.
    fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(original); f.flush(); os.fsync(f.fileno())
    fd = os.open(record, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write((json.dumps(intent, sort_keys=True) + "\n").encode()); f.flush(); os.fsync(f.fileno())
    made_dirs, made_files = [], []
    new_policy_written = False
    try:
        for folder in BUNDLE_DIRS:
            folder.mkdir(mode=0o755)
            root_dir(folder)
            made_dirs.append(folder)
        for path, blob in copies.items():
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
            with os.fdopen(fd, "wb") as f:
                f.write(blob); f.flush(); os.fsync(f.fileno())
            made_files.append(path)
            if digest(path.read_bytes()) != digest(blob):
                denied("COPIED_FILE_HASH_MISMATCH")
        fd, tmp = tempfile.mkstemp(prefix=".catalog-policy-", dir=POLICY.parent)
        try:
            os.fchmod(fd, original_mode)
            with os.fdopen(fd, "wb") as f:
                f.write(changed); f.flush(); os.fsync(f.fileno())
            new_policy_written = True
            os.replace(tmp, POLICY)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        now, _ = protected_read(POLICY, modes=(original_mode,), maximum=100000)
        if digest(now) != digest(changed):
            denied("POLICY_READBACK_MISMATCH")
        frozen, _ = protected_read(FREEZE, modes=(0o600,), maximum=4096, owner_uid=pwd.getpwnam('al').pw_uid)
        if digest(frozen) != FREEZE_SHA:
            denied("FREEZE_CHANGED")
        intent["status"] = "exact_three_blob_four_unit_repair_verified"
        intent["completed_at"] = datetime.now(timezone.utc).isoformat()
        atomic_root_json(record, intent)
        print(json.dumps({"status": intent["status"], "approval_id": approval,
                          "owner_oid": oid, "root_files_added": len(copies),
                          "allowed_units_added": len(UNITS), "freeze_unchanged": True,
                          "image_promotion_approved": False, "autotask_provider_writes_approved": False},
                         sort_keys=True), flush=True)
    except BaseException as original_error:
        rollback_good = True
        try:
            if new_policy_written:
                actual, _ = protected_read(POLICY, modes=(original_mode,), maximum=100000)
                if digest(actual) == digest(changed):
                    fd, tmp = tempfile.mkstemp(prefix=".catalog-policy-rollback-", dir=POLICY.parent)
                    with os.fdopen(fd, "wb") as f:
                        os.fchmod(f.fileno(), original_mode)
                        f.write(original); f.flush(); os.fsync(f.fileno())
                    os.replace(tmp, POLICY)
                elif digest(actual) != digest(original):
                    denied("UNRECOGNIZED_POLICY_CHANGE_DO_NOT_ROLLBACK")
            for path in reversed(made_files):
                if digest(path.read_bytes()) != digest(copies[path]):
                    denied("UNKNOWN_FILE_DRIFT_DO_NOT_REMOVE")
                path.unlink()
            for folder in reversed(made_dirs):
                folder.rmdir()
        except BaseException:
            rollback_good = False
        intent["status"] = "repair_rolled_back_verified" if rollback_good else "repair_rollback_unverified"
        intent["failed_at"] = datetime.now(timezone.utc).isoformat()
        atomic_root_json(record, intent)
        if not rollback_good:
            denied("ROLLBACK_UNVERIFIED_HUMAN_RECOVERY_REQUIRED")
        raise original_error

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--execute", action="store_true")
    a = parser.parse_args()
    if a.check_only == a.execute:
        denied("EXACT_MODE_REQUIRED")
    if a.check_only:
        original, changed, mode, copies = preflight()
        print(json.dumps({"status": "READONLY_PREFLIGHT_PASS_NOT_APPROVED",
                          "action": ACTION, "root_files_to_add": len(copies),
                          "allowed_units_to_add": len(UNITS),
                          "desired_policy_before_sha256": digest(original),
                          "desired_policy_after_sha256": digest(changed),
                          "production_mutations": False}, sort_keys=True))
    else:
        execute()

if __name__ == "__main__":
    main()
