#!/usr/bin/env python3
"""Root-only, exact-scope CCC retirement and V2 baseline revalidation.

The authenticated local sudo invocation is the one-time approval for precisely
this maintenance action, NOT a production release or standing authorization.
Production freeze and running Runtime/MCP/host bytes are never modified.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import fcntl
import hashlib
import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path

import release_control_transition_worker as rootctl
import restore_previous_verified_lkg_cli as prior

ROOT = Path("/var/lib/jason/openclaw/release-manager")
LKG = "c43e88e072c0b35c5b342d5e712fe34565b3e0cd"
FAILED_LKG = "aa6fa38a29b803e11ada63afb3cf25d17b7daf44"
UNITS = ("jason-ccc.timer", "jason-ccc.service")
SYSTEM_UNITS = Path("/etc/systemd/system")
SOURCE = Path("/opt/jason/releases") / LKG / "infrastructure/ccc/systemd"
CONTROL = ROOT / "production-control-state.json"
DRIFT = ROOT / "production-drift.json"
FREEZE = ROOT / "production-deployment-freeze"
POLICY = Path("/etc/jason/release-readback-recovery/production-desired-state.json")
TRANSACTION_LOCK = ROOT / "production-transaction.lock"
AUDIT_DIR = ROOT / "root-operator-approvals"


def command(*argv: str, allowed: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(argv, text=True, capture_output=True, timeout=90, check=False)
    if result.returncode not in allowed:
        raise RuntimeError("native systemd operation failed: " + argv[1] + ": " + str(result.returncode))
    return result


def exact_file(path: Path, owner: int = 0) -> bytes:
    info = path.lstat()
    if (path.is_symlink() or not stat.S_ISREG(info.st_mode)
            or info.st_uid != owner or info.st_mode & 0o002
            or ((info.st_mode & 0o020) and info.st_gid != 0)):
        raise PermissionError("unsafe protected file: " + path.name)
    return path.read_bytes()


def freeze_snapshot() -> bytes:
    info = FREEZE.lstat()
    if (FREEZE.is_symlink() or not stat.S_ISREG(info.st_mode)
            or info.st_uid != 1000 or stat.S_IMODE(info.st_mode) != 0o600):
        raise PermissionError("production freeze ownership/mode mismatch")
    value = FREEZE.read_bytes()
    if not value:
        raise ValueError("original production freeze absent")
    return value


def validate_baseline() -> tuple[dict, dict]:
    state = rootctl.protected_read(CONTROL)
    drift = rootctl.protected_read(DRIFT)
    breaker = state.get("circuit_breaker") or {}
    if ((state.get("last_known_good") or {}).get("manifest") or {}).get("revision") != LKG:
        raise ValueError("root LKG must be exact recovered V2 revision")
    if (breaker.get("state") != "open"
            or breaker.get("source") != "production_drift_watchdog"
            or breaker.get("reason") != "continuous_production_drift_detected"):
        raise ValueError("root breaker does not reflect exact CCC-only drift")
    if (drift.get("status") != "drift_detected"
            or drift.get("problems") != [
                {"kind":"failed_system_unit","state":"failed","unit":"jason-ccc.service"}
            ]):
        raise ValueError("unreviewed production drift is present")
    policy = json.loads(exact_file(POLICY).decode("utf-8"))
    if (policy.get("schema_version") != "1.0"
            or any(unit not in policy.get("allowed_system_units", []) for unit in UNITS)
            or any(unit in policy.get("required_system_units", []) for unit in UNITS)):
        raise ValueError("root desired-state policy does not permit optional CCC retirement")
    if Path("/opt/jason/current").resolve() != Path("/opt/jason/releases") / LKG:
        raise ValueError("live release path is not exact V2")
    rootctl.verify_immutable_lkg_fingerprint(
        state["last_known_good"]["manifest"], rootctl.verify_health(LKG)
    )
    return state, drift


def validate_and_archive() -> tuple[Path, bool]:
    base = AUDIT_DIR.resolve(strict=True)
    if not base.is_dir() or base.stat().st_uid != 0 or base.stat().st_mode & 0o022:
        raise PermissionError("root recovery archive directory not safe")
    if SOURCE.resolve(strict=True).parts[:3] != ("/", "opt", "jason"):
        raise PermissionError("source release root invalid")
    for unit in UNITS:
        installed, baseline = SYSTEM_UNITS / unit, SOURCE / unit
        original = exact_file(installed)
        if original != exact_file(baseline):
            raise ValueError("installed CCC unit differs from immutable V2 source: " + unit)
    timer_enabled = command("systemctl", "is-enabled", UNITS[0], allowed=(0,1)).stdout.strip() == "enabled"
    if not timer_enabled:
        raise ValueError("CCC timer is not in the original enabled state")
    if command("systemctl", "show", "-p", "ActiveState", "--value", UNITS[1]).stdout.strip() != "failed":
        raise ValueError("exact CCC-only failed oneshot not observed live")
    archive = Path(tempfile.mkdtemp(prefix="ccc-exact-20261110-", dir=str(base)))
    os.chown(archive, 0, 0)
    os.chmod(archive, 0o700)
    for unit in UNITS:
        data = exact_file(SYSTEM_UNITS / unit)
        fd = os.open(archive / unit, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as dst:
            dst.write(data)
            dst.flush()
            os.fsync(dst.fileno())
    return archive, timer_enabled


def restore_units(archive: Path, timer_enabled: bool) -> None:
    """Restore only archived unit bytes and refresh evidence from live systemd.

    Never rewrite a stale pre-mutation drift report after systemd state changed.
    The breaker remains open; if fresh drift evaluation cannot pass, the prior
    report remains only until the normal watchdog can publish newer evidence.
    """
    for unit in UNITS:
        original = (archive / unit).read_bytes()
        path = SYSTEM_UNITS / unit
        if path.exists():
            if exact_file(path) != original:
                raise RuntimeError("cannot safely restore changed CCC unit")
            continue
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        with os.fdopen(fd, "wb") as out:
            out.write(original)
            out.flush()
            os.fsync(out.fileno())
        os.chown(path, 0, 0)
    command("systemctl", "daemon-reload")
    if timer_enabled:
        command("systemctl", "enable", "--now", UNITS[0])
    try:
        rootctl.refresh_stale_drift()
        print("ROLLBACK_DRIFT_READBACK=FRESH")
    except Exception as exc:
        print("ROLLBACK_DRIFT_READBACK=NOT_REFRESHED:" + type(exc).__name__)
        print("ROOT_BREAKER_REMAINS_OPEN=TRUE")


def recover_ccc() -> None:
    if os.geteuid() != 0:
        raise PermissionError("authenticated local sudo required")
    if not Path("/root/restore_previous_verified_lkg_cli.py").is_file():
        raise PermissionError("pinned prior V2 root-recovery helper is not installed")
    with TRANSACTION_LOCK.open("a+") as transaction:
        fcntl.flock(transaction, fcntl.LOCK_EX | fcntl.LOCK_NB)
        freeze = freeze_snapshot()
        state = rootctl.protected_read(CONTROL)
        live_lkg = ((state.get("last_known_good") or {}).get("manifest") or {}).get("revision")
        if live_lkg == FAILED_LKG:
            prior.recover()
            print("ROOT_PREVIOUS_LKG_RESTORED=PASS")
        elif live_lkg != LKG:
            raise ValueError("unexpected production root LKG")
        # Independent existing root control lock is held by prior.recover()
        # only during its atomic write. Acquire it again for the maintenance.
        with rootctl.LOCK.open("a+") as root_lock:
            fcntl.flock(root_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            validate_baseline()
            archive, timer_enabled = validate_and_archive()
            mutation_started = False
            breaker_committed = False
            preclose_state = None
            try:
                # CCC has no user or endpoint sessions; timer first prevents a
                # new oneshot while the fixed-scope unit files are archived.
                mutation_started = True
                command("systemctl", "stop", UNITS[0])
                command("systemctl", "disable", UNITS[0])
                command("systemctl", "stop", UNITS[1])
                for unit in UNITS:
                    path = SYSTEM_UNITS / unit
                    if exact_file(path) != (archive / unit).read_bytes():
                        raise RuntimeError("CCC unit changed during serialized retirement")
                    path.unlink()
                command("systemctl", "daemon-reload")
                command("systemctl", "reset-failed", UNITS[1], allowed=(0,1))
                for unit in UNITS:
                    if (SYSTEM_UNITS / unit).exists():
                        raise ValueError("CCC installed unit unexpectedly remains")
                rootctl.refresh_stale_drift()
                state = rootctl.protected_read(CONTROL)
                preclose_state = copy.deepcopy(state)
                updated = rootctl.apply_transition(
                    {"action":"revalidate","revision":LKG}, state
                )
                if (updated.get("circuit_breaker") or {}).get("state") != "closed":
                    raise ValueError("independent root revalidation did not close breaker")
                if freeze_snapshot() != freeze:
                    raise ValueError("production freeze was altered during recovery")
                # An audit record is durable before changing the root breaker.
                rootctl.write_json(archive / "intent.json", {
                    "schema_version":"1.0",
                    "status":"independent_health_pass_before_breaker_close",
                    "candidate_baseline":LKG,
                    "original_freeze_sha256":hashlib.sha256(freeze).hexdigest(),
                    "archived_units":list(UNITS),
                    "no_standing_authority":True,
                }, 0, 0)
                rootctl.write_json(CONTROL, updated, 0, 0)
                breaker_committed = True
                readback = rootctl.protected_read(CONTROL)
                if (readback.get("circuit_breaker") or {}).get("state") != "closed":
                    raise ValueError("root breaker readback mismatch")
                receipt = {
                    "schema_version":"1.0",
                    "operation":"owner_approved_exact_ccc_retirement_and_v2_lkg_revalidation",
                    "status":"pass",
                    "timestamp_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
                    "source":LKG,
                    "original_failed_lkg":FAILED_LKG,
                    "units_archived":[
                        {"name":u,
                         "sha256":hashlib.sha256((archive/u).read_bytes()).hexdigest()}
                        for u in UNITS
                    ],
                    "original_freeze_sha256":hashlib.sha256(freeze).hexdigest(),
                    "breaker":"closed_root_revalidated_V2",
                    "production_release_performed":False,
                    "runtime_or_mcp_restarted":False,
                    "no_standing_authority":True,
                }
                rootctl.write_json(archive / "receipt.json", receipt, 0, 0)
                print("CCC_UNIT_RETIREMENT=PASS")
                print("INDEPENDENT_ROOT_DRIFT=PASS")
                print("ROOT_BREAKER=CLOSED")
                print("ROOT_LKG=" + LKG)
                print("PRODUCTION_FREEZE_BYTE_IDENTICAL=PASS")
                print("NEXT_STEP=GOVERNED_EXACT_SHA_RELEASE_TO_ENABLE_NON_TEAMS_APPROVAL")
            except Exception:
                # If post-commit readback or receipt fails, first reopen the
                # root breaker before restoring the failed legacy scheduler.
                try:
                    if breaker_committed and preclose_state is not None:
                        rootctl.write_json(CONTROL, preclose_state, 0, 0)
                    if mutation_started:
                        restore_units(archive, timer_enabled)
                except Exception as rollback_error:
                    raise RuntimeError("CCC maintenance and unit rollback both failed") from rollback_error
                raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exact-ccc-recovery", action="store_true", required=True)
    args = parser.parse_args()
    recover_ccc()


if __name__ == "__main__":
    main()
