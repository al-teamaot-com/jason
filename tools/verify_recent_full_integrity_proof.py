#!/usr/bin/env python3
"""Fail-closed 24-hour reuse of a completed full SQLite integrity proof."""
from __future__ import annotations
import argparse
import json
import os
import stat
import time
from pathlib import Path

TIMEOUT_FAILURES = frozenset({"operational_health_timeout"})


def read_evidence(path: Path, expected_uid: int):
    try:
        info = os.lstat(path)
        if (not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != expected_uid
                or info.st_nlink != 1):
            return None
        with path.open("rb") as stream:
            raw = stream.read(1048577)
        if len(raw) > 1048576:
            return None
        data = json.loads(raw)
        return (data, info.st_mtime) if isinstance(data, dict) else None
    except (OSError, ValueError, TypeError):
        return None


def is_pass(data: dict) -> bool:
    proof = data.get("backup_restore_proof") or {}
    files = data.get("files") or {}
    return (
        data.get("status") == "pass"
        and data.get("snapshot_source_exit_code") == 0
        and data.get("provider_contacted") is False
        and data.get("provider_credentials_used") is False
        and data.get("failures") == []
        and isinstance(proof, dict)
        and proof.get("backup_integrity") == "ok"
        and proof.get("restore_integrity") == "ok"
        and proof.get("counts_match") is True
        and isinstance(files, dict)
        and all(
            isinstance(files.get(name), dict)
            and files[name].get("integrity") == "ok"
            for name in ("authority", "replay", "security_audit", "orchestration_audit")
        )
    )


def valid_recent_proof(current: Path, last_success: Path,
                       max_age_seconds: int, expected_uid: int,
                       now: float | None = None) -> bool:
    when = time.time() if now is None else now
    latest = read_evidence(current, expected_uid)
    saved = read_evidence(last_success, expected_uid)
    # A concrete failed integrity result after the last passing scan is not
    # equivalent to an inconclusive timeout. Never suppress that failure.
    good = [entry for entry in (latest, saved) if entry and is_pass(entry[0])]
    newest_pass_at = max((entry[1] for entry in good), default=0.0)
    if latest and latest[1] > newest_pass_at and latest[0].get("status") == "fail":
        failures = latest[0].get("failures")
        if not isinstance(failures, list) or set(failures) - TIMEOUT_FAILURES:
            return False
    for evidence in (latest, saved):
        if not evidence:
            continue
        data, mtime = evidence
        age = when - mtime
        if 0 <= age <= max_age_seconds and is_pass(data):
            return True
    return False


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--current", type=Path, required=True)
    p.add_argument("--last-success", type=Path, required=True)
    p.add_argument("--max-age-seconds", type=int, default=86400)
    p.add_argument("--expected-uid", type=int, required=True)
    args = p.parse_args()
    if args.max_age_seconds <= 0 or args.max_age_seconds > 86400:
        return 2
    return 0 if valid_recent_proof(
        args.current, args.last_success, args.max_age_seconds,
        args.expected_uid
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
