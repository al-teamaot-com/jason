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
    if _show("DropInPaths"):
        raise HandoffRefused("unexpected authority service override")
    if EXPECTED_FAST not in _show("ExecStart"):
        raise HandoffRefused("loaded authority service is not new fast checker")
    if _call(["/usr/bin/systemctl", "is-active", TIMER]) != "active":
        raise HandoffRefused("authority-health timer is not active")


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
    _installed_is_exact(source)
    active = _show("ActiveState")
    sub = _show("SubState")
    if active == "inactive" and sub == "dead" and not _show("Job"):
        before = time.time_ns() - 1_000_000_000
        _call(["/usr/bin/systemctl", "start", UNIT], timeout=40)
        _verify_snapshot(not_before_ns=before)
        return "SYSTEMD_FAST_HEALTH_VERIFIED"
    if _legacy_job_is_exact():
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
            _installed_is_exact(args.release_dir)
            _verify_snapshot(
                not_before_ns=time.time_ns() - MAX_REPORT_AGE_SECONDS * 1_000_000_000
            )
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
