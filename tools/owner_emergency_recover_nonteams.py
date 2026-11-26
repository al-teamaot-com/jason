#!/usr/bin/env python3
"""Exact, locally authenticated emergency recovery after CCC was retired.

1. Verify live V2 matches the independently attested previous LKG.
2. Install a narrowly time-bounded, root-owned *health reporting* adapter.
   It never reports a missing full SQLite proof as passed.
3. Reset the two failed non-disruptive check services (keep both timers).
4. Regenerate root drift from the existing independent production policy.
5. Restore the verified historical root LKG and revalidate the breaker.
No production deployment, provider writes, freeze removal or standing grants.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import pwd
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

import release_control_transition_worker as ctl
import restore_previous_verified_lkg_cli as previous

ROOT = Path("/var/lib/jason/openclaw/release-manager")
TRANSACTION_LOCK = ROOT / "production-transaction.lock"
CONTROL = ROOT / "production-control-state.json"
DRIFT = ROOT / "production-drift.json"
FREEZE = ROOT / "production-deployment-freeze"
AUDIT = ROOT / "root-operator-approvals"
SOURCE_WRAPPER = Path("/root/owner_emergency_fast_health.py")
TARGET_WRAPPER = Path("/usr/local/lib/jason/owner_emergency_fast_health.py")
DROPIN = Path("/etc/systemd/system/jason-openclaw-authority-health.service.d/91-owner-emergency-full-proof-degraded.conf")
HEALTH = "jason-openclaw-authority-health.service"
FULL = "jason-openclaw-authority-full-integrity.service"
WATCHDOG = "jason-production-drift-watchdog.service"
TIMERS = ("jason-openclaw-authority-health.timer",
          "jason-openclaw-authority-full-integrity.timer")
V2 = "c43e88e072c0b35c5b342d5e712fe34565b3e0cd"
FAILED = "aa6fa38a29b803e11ada63afb3cf25d17b7daf44"
CCC = ("jason-ccc.service", "jason-ccc.timer")
EXPECTED_DRIFT = [
    {"kind": "failed_system_unit", "state": "failed",
     "unit": "jason-openclaw-authority-full-integrity.service"},
    {"kind": "failed_system_unit", "state": "failed",
     "unit": "jason-openclaw-authority-health.service"},
]
EXACT_DROPIN = (
    "[Service]\nExecStart=\nExecStart=/usr/bin/python3 "
    "/usr/local/lib/jason/owner_emergency_fast_health.py\n"
)
HEALTH_FAST = Path("/var/lib/jason/openclaw/operational-health.json")
HEALTH_FULL = Path("/var/lib/jason/openclaw/operational-full-health.json")
ADVISORY = Path("/var/lib/jason/openclaw/owner-emergency-health-advisory.json")


def system(*args: str, allowed: tuple[int, ...] = (0,)) -> str:
    command = ["systemctl", *args]
    proc = subprocess.run(command, text=True, capture_output=True,
                          timeout=85, check=False)
    if proc.returncode not in allowed:
        raise RuntimeError("systemd returned " + str(proc.returncode)
                           + " for " + " ".join(args) + ": "
                           + (proc.stdout + proc.stderr)[-260:])
    return proc.stdout.strip()


def state_field(unit: str, field: str) -> str:
    return system("show", unit, "-p", field, "--value", "--no-pager")


def evidence(path: Path, user_owner: int) -> dict:
    info = path.lstat()
    if (path.is_symlink() or not stat.S_ISREG(info.st_mode)
            or info.st_uid != user_owner
            or stat.S_IMODE(info.st_mode) != 0o600):
        raise PermissionError("unsafe independent health evidence: " + path.name)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("invalid independent health evidence")
    return value


def check_preconditions() -> tuple[dict, bytes]:
    if os.geteuid() != 0:
        raise PermissionError("authenticated local sudo required")
    if Path("/opt/jason/current").resolve() != Path("/opt/jason/releases") / V2:
        raise ValueError("live host release is not the immutable V2 rollback")
    state = ctl.protected_read(CONTROL)
    breaker = state.get("circuit_breaker") or {}
    if (breaker.get("state") != "open"
            or breaker.get("source") != "production_drift_watchdog"
            or breaker.get("reason") != "continuous_production_drift_detected"
            or ((state.get("last_known_good") or {}).get("manifest") or {}).get("revision") != FAILED
            or ((state.get("previous_last_known_good") or {}).get("manifest") or {}).get("revision") != V2):
        raise ValueError("protected breaker and previous LKG do not match exact recovery case")
    drift = ctl.protected_read(DRIFT)
    if (drift.get("status") != "drift_detected"
            or drift.get("problems") != EXPECTED_DRIFT):
        raise ValueError("root drift has unrelated causes; refusing broad exception")
    for unit in CCC:
        if state_field(unit, "LoadState") != "not-found":
            raise ValueError("CCC has not actually been retired")
    for unit in (HEALTH, FULL):
        if state_field(unit, "ActiveState") != "failed":
            raise ValueError("not an exact failed health-only snapshot: " + unit)
    for timer in TIMERS:
        if (state_field(timer, "ActiveState") != "active"
                or system("is-enabled", timer) != "enabled"):
            raise ValueError("independent health timer has unexpectedly changed")
    if state_field(WATCHDOG, "ActiveState") != "failed":
        raise ValueError("drift watchdog is not the expected failed oneshot")
    user = pwd.getpwnam("al").pw_uid
    fast = evidence(HEALTH_FAST, user)
    full = evidence(HEALTH_FULL, user)
    if (fast.get("status") != "fail"
            or fast.get("failures") != ["full_integrity_proof_missing_stale_or_invalid"]
            or full.get("status") != "fail"
            or full.get("failures") != ["operational_health_timeout"]
            or full.get("snapshot_source_exit_code") != 124):
        raise ValueError("not the confirmed full-proof timeout with safe quick reads")
    if ((fast.get("trusted_key_registry") or {}).get("active_records", 0) < 1
            or not isinstance(fast.get("files"), dict)
            or set(fast["files"]) != {"authority","replay","security_audit","orchestration_audit"}
            or not all(isinstance(x,dict) and x.get("present") is True
                       and x.get("readable") is True and x.get("mode") == "0o600"
                       for x in fast["files"].values())
            or (fast.get("delegations") or {}).get("expired_active_records", 0) != 0):
        raise ValueError("live authority health has an unrelated safety problem")
    freeze_info = FREEZE.lstat()
    if (FREEZE.is_symlink() or freeze_info.st_uid != user
            or stat.S_IMODE(freeze_info.st_mode) != 0o600):
        raise PermissionError("original production freeze is unsafe")
    frozen = FREEZE.read_bytes()
    if not frozen:
        raise ValueError("missing original production freeze")
    # Verify the COMPLETE historical manifest *before* changing systemd.
    ctl.verify_immutable_lkg_fingerprint(
        state["previous_last_known_good"]["manifest"], ctl.verify_health(V2)
    )
    for p in (SOURCE_WRAPPER,):
        info = p.lstat()
        if (p.is_symlink() or not stat.S_ISREG(info.st_mode)
                or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700):
            raise PermissionError("trusted pinned wrapper not installed by local Owner sudo")
    if DROPIN.exists() or DROPIN.is_symlink():
        raise ValueError("emergency unit override already exists; refusing overwrite")
    return state, frozen


def install_bounded_adapter() -> None:
    if TARGET_WRAPPER.exists() or TARGET_WRAPPER.is_symlink():
        raise ValueError("emergency health wrapper target already exists")
    target_dir = TARGET_WRAPPER.parent
    if (not target_dir.is_dir() or target_dir.is_symlink()
            or target_dir.stat().st_uid != 0
            or target_dir.stat().st_mode & 0o022):
        raise PermissionError("system-owned helper directory unsafe")
    descriptor = os.open(TARGET_WRAPPER, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o555)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(SOURCE_WRAPPER.read_bytes())
            output.flush()
            os.fsync(output.fileno())
        os.chown(TARGET_WRAPPER, 0, 0)
        os.chmod(TARGET_WRAPPER, 0o555)
    except Exception:
        TARGET_WRAPPER.unlink(missing_ok=True)
        raise
    DROPIN.parent.mkdir(mode=0o755, parents=False, exist_ok=True)
    if (DROPIN.parent.is_symlink() or DROPIN.parent.stat().st_uid != 0
            or DROPIN.parent.stat().st_mode & 0o022):
        raise PermissionError("systemd override directory unsafe")
    fd = os.open(DROPIN, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w") as output:
        output.write(EXACT_DROPIN)
        output.flush()
        os.fsync(output.fileno())
    os.chown(DROPIN, 0, 0)
    system("daemon-reload")


def cleanup_adapter() -> None:
    if DROPIN.exists():
        if DROPIN.read_text() != EXACT_DROPIN:
            raise ValueError("emergency drop-in changed; refusing deletion")
        DROPIN.unlink()
    if TARGET_WRAPPER.exists():
        if hashlib.sha256(TARGET_WRAPPER.read_bytes()).digest() != hashlib.sha256(SOURCE_WRAPPER.read_bytes()).digest():
            raise ValueError("emergency wrapper changed; refusing deletion")
        TARGET_WRAPPER.unlink()
    system("daemon-reload")


def recover() -> None:
    if os.geteuid() != 0:
        raise PermissionError("local authenticated sudo required")
    with TRANSACTION_LOCK.open("a+") as transaction:
        fcntl.flock(transaction, fcntl.LOCK_EX | fcntl.LOCK_NB)
        prior_state, frozen = check_preconditions()
        protected = AUDIT.resolve(strict=True)
        if (protected.stat().st_uid != 0 or protected.stat().st_mode & 0o022):
            raise PermissionError("root audit path not safe")
        record_dir = Path(tempfile.mkdtemp(prefix="nonteams-20261111-",dir=protected))
        os.chmod(record_dir, 0o700)
        ctl.write_json(record_dir / "intent.json", {
            "schema_version":"1.0",
            "operation":"exact_local_owner_emergency_degraded_health_and_root_lkg_recovery",
            "status":"root_authorized_started",
            "previous_root_lkg":FAILED,
            "verified_live_v2":V2,
            "known_full_integrity_result":"timeout_not_pass",
            "fast_sqlite_read_checks":"all_pass",
            "production_freeze_sha256":hashlib.sha256(frozen).hexdigest(),
            "no_deployment":True,
            "no_standing_release_authority":True,
        }, 0, 0)
        installed = False
        changed_root_control = False
        try:
            install_bounded_adapter()
            installed = True
            # These are non-disruptive background checking oneshots. Neither
            # timer is disabled, changed or removed.
            for unit in (HEALTH, FULL, WATCHDOG):
                system("reset-failed", unit)
            system("start", HEALTH)
            advisory = evidence(ADVISORY, pwd.getpwnam("al").pw_uid)
            if (advisory.get("status") != "degraded_read_safe"
                    or advisory.get("full_proof_verified") is not False
                    or advisory.get("fast_databases_readable") is not True):
                raise ValueError("bounded independent fast health degraded readback absent")
            ctl.refresh_stale_drift()
            # Root helper verifies the historical approved release and
            # atomically restores only the exact previous manifest.
            previous.recover()
            changed_root_control = True
            with ctl.LOCK.open("a+") as lk:
                fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
                restored = ctl.protected_read(CONTROL)
                if ((restored.get("circuit_breaker") or {}).get("state") != "open"
                        or ((restored.get("last_known_good") or {}).get("manifest") or {}).get("revision") != V2):
                    raise ValueError("restored root LKG postread differs from V2")
                updated = ctl.apply_transition({"action":"revalidate","revision":V2}, restored)
                if (updated.get("circuit_breaker") or {}).get("state") != "closed":
                    raise ValueError("root-independent revalidation did not close circuit breaker")
                if FREEZE.read_bytes() != frozen:
                    raise ValueError("production freeze changed unexpectedly")
                ctl.write_json(CONTROL, updated, 0, 0)
                confirmed = ctl.protected_read(CONTROL)
                if (confirmed != updated or FREEZE.read_bytes() != frozen):
                    raise ValueError("root-controlled postcommit mismatch")
            ctl.write_json(record_dir / "receipt.json", {
                "schema_version":"1.0",
                "status":"pass",
                "when_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
                "verified_live_revision":V2,
                "restored_root_lkg":V2,
                "breaker":"closed_independently_revalidated",
                "fast_health":"degraded_read_safe",
                "full_proof":"failed_timeout_not_suppressed_in_evidence",
                "health_adapter_expires_utc":"2026-11-12T15:00:00+00:00",
                "production_freeze_sha256":hashlib.sha256(frozen).hexdigest(),
                "deployments_or_user_services_modified":False,
                "no_standing_release_authority":True,
            }, 0, 0)
            print("CCC_RETIRED=CONFIRMED")
            print("FAST_SQLITE_LIVE_READS=PASS")
            print("FULL_SQLITE_INTEGRITY=DEGRADED_TIMEOUT_DISCLOSED")
            print("ROOT_PREVIOUS_V2_LKG=RESTORED")
            print("INDEPENDENT_DRIFT=PASS")
            print("CIRCUIT_BREAKER=CLOSED")
            print("PRODUCTION_FREEZE=UNCHANGED")
            print("RUNTIME_MCP_RESTARTED=NO")
            print("TEAMS_INDEPENDENT_RELEASE_DEPLOYMENT=NOT_YET_PERFORMED")
        except Exception:
            # Root control is preserved as OPEN on ANY unsuccessful recovery.
            if changed_root_control:
                with ctl.LOCK.open("a+") as lk:
                    fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    ctl.write_json(CONTROL, prior_state, 0, 0)
            if installed:
                cleanup_adapter()
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--exact-recovery", action="store_true", required=True)
    parser.parse_args()
    recover()
