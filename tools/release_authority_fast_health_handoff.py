#!/usr/bin/env python3
"""Bounded release handoff from an in-flight legacy SQLite scan to fast health.

Runs ONLY inside the native root-owned immutable host reconciler. A long-running
legacy oneshot is never stopped, killed, restarted or claimed to have finished.
The exact installed new systemd definition and timer are verified, while an
independent real fast-health probe is run as the unprivileged service account.
The full integrity/restore proof remains mandatory and must be recent and PASS.

Do not use this to accept an unrelated activating service or stale evidence.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import time

UNIT = "jason-openclaw-authority-health.service"
TIMER = "jason-openclaw-authority-health.timer"
EXPECTED_FAST = "/opt/jason/current/tools/openclaw_authority_fast_health.py"
LEGACY = "/opt/jason/current/tools/openclaw_authority_health_snapshot.py"
OUTPUT = Path("/var/lib/jason/openclaw/operational-health.json")
FULL = Path("/var/lib/jason/openclaw/operational-full-health.json")
INSTALLED = Path("/etc/systemd/system") / UNIT
PROC_ROOT = Path("/proc")
UNIT_IN_RELEASE = "infrastructure/openclaw-operations/systemd/" + UNIT
CHECK_MODE = "frequent_read_only_plus_recent_full_integrity"
MAX_REPORT_AGE_SECONDS = 360
MAX_FULL_AGE_SECONDS = 30 * 60 * 60
OWNER_DROPIN = Path("/etc/systemd/system/jason-openclaw-authority-health.service.d/91-owner-emergency-full-proof-degraded.conf")
OWNER_HANDLER = Path("/usr/local/lib/jason/owner_emergency_fast_health.py")
OWNER_HANDLER_SOURCE = Path("tools/owner_emergency_fast_health.py")
OWNER_ADVISORY = Path("/var/lib/jason/openclaw/owner-emergency-health-advisory.json")
OWNER_EXPIRY = "2026-11-12T15:00:00+00:00"
OWNER_EXPIRY_TIMESTAMP = 1794495600
EXACT_OWNER_DROPIN = (
    b"[Service]\nExecStart=\nExecStart=/usr/bin/python3 "
    + str(OWNER_HANDLER).encode("ascii") + b"\n"
)


class HandoffRefused(RuntimeError):
    pass


def _call(command: list[str], *, timeout: int = 12) -> str:
    try:
        result = subprocess.run(
            command, check=True, capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise HandoffRefused("bounded systemd or health command failed") from exc
    return result.stdout.strip()


def _show(prop: str, *, unit: str = UNIT) -> str:
    return _call(["/usr/bin/systemctl", "show", unit, "-p", prop, "--value"], timeout=9)


def _trusted_root_regular(info: os.stat_result) -> bool:
    return (
        stat.S_ISREG(info.st_mode) and info.st_uid == 0
        and not (info.st_mode & stat.S_IWOTH)
        and not (info.st_mode & stat.S_IWGRP and info.st_gid != 0)
    )


def _installed_is_exact(source: Path) -> None:
    expected = source / UNIT_IN_RELEASE
    for p in (expected, INSTALLED):
        try:
            info = p.lstat()
        except OSError as exc:
            raise HandoffRefused("canonical authority service unit unavailable") from exc
        if p.is_symlink() or not _trusted_root_regular(info):
            raise HandoffRefused("authority service unit not securely root-owned")
    if expected.read_bytes() != INSTALLED.read_bytes():
        raise HandoffRefused("installed authority service differs from exact immutable release")
    if _show("FragmentPath") != str(INSTALLED):
        raise HandoffRefused("loaded systemd unit is not canonical authority service")
    dropins = _show("DropInPaths")
    if dropins:
        # Only this separately Owner-approved emergency override is admitted.
        # Its root-only program must equal the immutable reviewed release bytes.
        if dropins != str(OWNER_DROPIN):
            raise HandoffRefused("unexpected authority service override")
        for candidate in (OWNER_DROPIN, OWNER_HANDLER, source / OWNER_HANDLER_SOURCE):
            try:
                info = candidate.lstat()
            except OSError as exc:
                raise HandoffRefused("exact Owner emergency override unavailable") from exc
            if candidate.is_symlink() or not _trusted_root_regular(info):
                raise HandoffRefused("untrusted Owner emergency override")
        if (OWNER_DROPIN.read_bytes() != EXACT_OWNER_DROPIN
                or OWNER_HANDLER.read_bytes()
                    != (source / OWNER_HANDLER_SOURCE).read_bytes()):
            raise HandoffRefused("Owner emergency override differs from reviewed source")
        if time.time() >= OWNER_EXPIRY_TIMESTAMP:
            raise HandoffRefused("Owner emergency override expired")
        if f"argv[]=/usr/bin/python3 {OWNER_HANDLER} ;" not in _show("ExecStart"):
            raise HandoffRefused("loaded Owner emergency fast checker differs")
    elif EXPECTED_FAST not in _show("ExecStart"):
        raise HandoffRefused("loaded authority service is not new fast checker")
    if _call(["/usr/bin/systemctl", "is-active", TIMER]) != "active":
        raise HandoffRefused("authority-health timer is not active")
    return bool(dropins)


def _legacy_job_is_exact() -> bool:
    if _show("ActiveState") != "activating" or _show("SubState") != "start":
        return False
    job = _show("Job")
    raw_pid = _show("ExecMainPID")
    if not job or not job.isdecimal() or not raw_pid.isdecimal() or int(raw_pid) < 2:
        return False
    pid = int(raw_pid)
    proc = PROC_ROOT / str(pid)
    try:
        info = proc.stat()
        argv = (proc / "cmdline").read_bytes().split(b"\0")
    except OSError:
        return False
    account = pwd.getpwnam("al")
    return (
        info.st_uid == account.pw_uid
        and len(argv) >= 2
        and argv[0] in (b"/usr/bin/python3", b"/usr/bin/python3.12")
        and argv[1] == LEGACY.encode("ascii")
    )


def _verify_snapshot(*, not_before_ns: int) -> None:
    try:
        meta = OUTPUT.lstat()
        if (not stat.S_ISREG(meta.st_mode) or OUTPUT.is_symlink()
                or meta.st_uid != pwd.getpwnam("al").pw_uid
                or stat.S_IMODE(meta.st_mode) != 0o600 or meta.st_size > 131072
                or meta.st_mtime_ns < not_before_ns):
            raise HandoffRefused("fast health result missing, stale or unsafe")
        report = json.loads(OUTPUT.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise HandoffRefused("fast health result could not be verified") from exc
    if (not isinstance(report, dict) or report.get("status") != "pass"
            or report.get("check_mode") != CHECK_MODE
            or report.get("full_proof_status") != "pass"
            or report.get("snapshot_source_exit_code") != 0
            or report.get("provider_contacted") is not False
            or report.get("provider_credentials_used") is not False
            or report.get("failures") != []):
        raise HandoffRefused("fast health did not return independent PASS")
    age = report.get("full_proof_age_seconds")
    if type(age) is not int or not (0 <= age <= MAX_FULL_AGE_SECONDS):
        raise HandoffRefused("independent full-integrity/restore proof not recent")


def _read_owned_evidence(path: Path, *, not_before_ns: int) -> dict:
    try:
        info = path.lstat()
        if (path.is_symlink() or not stat.S_ISREG(info.st_mode)
                or info.st_uid != pwd.getpwnam("al").pw_uid
                or stat.S_IMODE(info.st_mode) != 0o600
                or not (0 < info.st_size <= 131072)
                or info.st_mtime_ns < not_before_ns):
            raise HandoffRefused("emergency evidence absent, stale or untrusted")
        report = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise HandoffRefused("emergency evidence malformed")
        return report
    except (OSError, ValueError, TypeError) as exc:
        raise HandoffRefused("emergency evidence unavailable") from exc


def _verify_emergency_snapshot(*, not_before_ns: int) -> None:
    if time.time() >= OWNER_EXPIRY_TIMESTAMP:
        raise HandoffRefused("Owner emergency expired")
    report = _read_owned_evidence(OUTPUT, not_before_ns=not_before_ns)
    advisory = _read_owned_evidence(OWNER_ADVISORY, not_before_ns=not_before_ns)
    full = _read_owned_evidence(FULL, not_before_ns=0)
    files = report.get("files")
    keys = report.get("trusted_key_registry")
    delegations = report.get("delegations")
    expected = {"authority", "replay", "security_audit", "orchestration_audit"}
    if (report.get("status") != "fail"
            or report.get("check_mode") != CHECK_MODE
            or report.get("full_proof_status") != "missing_or_invalid"
            or report.get("snapshot_source_exit_code") != 2
            or report.get("failures") != ["full_integrity_proof_missing_stale_or_invalid"]
            or report.get("provider_contacted") is not False
            or report.get("provider_credentials_used") is not False
            or not isinstance(files, dict) or set(files) != expected
            or any(not isinstance(x, dict) or x.get("present") is not True
                   or x.get("readable") is not True or x.get("mode") != "0o600"
                   for x in files.values())
            or not isinstance(keys, dict) or keys.get("present") is not True
            or keys.get("mode") != "0o600" or
            not isinstance(keys.get("active_records"), int)
            or keys["active_records"] < 1
            or not isinstance(delegations, dict)
            or delegations.get("expired_active_records") != 0):
        raise HandoffRefused("emergency fast SQLite/authority read checks failed")
    if (full.get("status") != "fail"
            or full.get("failures") != ["operational_health_timeout"]
            or full.get("snapshot_source_exit_code") != 124
            or full.get("provider_contacted") is not False
            or full.get("provider_credentials_used") is not False):
        raise HandoffRefused("emergency missing proof is not the reviewed timeout")
    if (advisory.get("status") != "degraded_read_safe"
            or advisory.get("expires_at") != OWNER_EXPIRY
            or advisory.get("full_proof_verified") is not False
            or advisory.get("fast_databases_readable") is not True
            or advisory.get("full_proof_reason") != "full_integrity_proof_missing_stale_or_invalid"
            or advisory.get("no_authority_granted") is not True
            or advisory.get("approval_boundary") !=
                "local_root_owner_emergency_recovery_only"):
        raise HandoffRefused("emergency health evidence lacks bounded Owner approval")


def _run_direct_probe(source: Path) -> None:
    # The fallback runs ONLY for the exact still-running legacy oneshot.
    # No start/stop/restart/kill or modification of its systemd job.
    fast = source / "tools/openclaw_authority_fast_health.py"
    try:
        info = fast.lstat()
    except OSError as exc:
        raise HandoffRefused("immutable fast-health program unavailable") from exc
    if fast.is_symlink() or not _trusted_root_regular(info):
        raise HandoffRefused("immutable fast-health program is untrusted")
    before = time.time_ns() - 1_000_000_000
    _call([
        "/usr/sbin/runuser", "-u", "al", "--",
        "/usr/bin/python3", str(fast),
        "--output", str(OUTPUT), "--full-evidence", str(FULL),
    ], timeout=35)
    _verify_snapshot(not_before_ns=before)


def reconcile(source: Path) -> str:
    if os.geteuid() != 0:
        raise HandoffRefused("native root host reconciliation required")
    if source.name != Path("/opt/jason/current").resolve().name:
        raise HandoffRefused("candidate source must be the current immutable host release")
    emergency = _installed_is_exact(source)
    active = _show("ActiveState")
    sub = _show("SubState")
    if active == "inactive" and sub == "dead" and not _show("Job"):
        before = time.time_ns() - 1_000_000_000
        _call(["/usr/bin/systemctl", "start", UNIT], timeout=40)
        if emergency:
            _verify_emergency_snapshot(not_before_ns=before)
            return "OWNER_EMERGENCY_DEGRADED_READ_SAFE_NOT_FULL_PASS"
        _verify_snapshot(not_before_ns=before)
        return "SYSTEMD_FAST_HEALTH_VERIFIED"
    if not emergency and _legacy_job_is_exact():
        _run_direct_probe(source)
        return "INFLIGHT_LEGACY_SCAN_FAST_HEALTH_VERIFIED"
    raise HandoffRefused("authority service state not safely eligible for fast-health handoff")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.verify_only:
            if os.geteuid() != 0:
                raise HandoffRefused("native root host verification required")
            emergency = _installed_is_exact(args.release_dir)
            before = time.time_ns() - MAX_REPORT_AGE_SECONDS * 1_000_000_000
            if emergency:
                _verify_emergency_snapshot(not_before_ns=before)
                print("JASON_AUTHORITY_FAST_HEALTH_FINAL_READBACK=DEGRADED_READ_SAFE_NOT_FULL_PASS")
            else:
                _verify_snapshot(not_before_ns=before)
                print("JASON_AUTHORITY_FAST_HEALTH_FINAL_READBACK=PASS")
        else:
            result = reconcile(args.release_dir)
            print("JASON_AUTHORITY_FAST_HEALTH_TRANSITION=" + result)
        return 0
    except HandoffRefused as exc:
        print("JASON_AUTHORITY_FAST_HEALTH_TRANSITION=DENY " + str(exc))
        return 9


if __name__ == "__main__":
    raise SystemExit(main())
