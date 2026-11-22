#!/usr/bin/env python3
"""Source-only scoped full-health wrapper for the relocated audit database.

This is NOT an installer or approval mechanism. Production entry requires an
independently signed exact-action, root-owned install and unit integration.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

from openclaw_authority_health_snapshot import (
    write_atomic_snapshot, completed_timeout_stages,
)

AUDIT = Path("/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3")
OUTPUT = Path("/var/lib/jason/openclaw/operational-full-health.json")
ARCHIVE = Path("/srv/jason/archive/authority-health-scratch")
TRUSTED_ENTRYPOINT = Path(
    "/usr/local/lib/jason/audit-journal/native-health/openclaw_authority_live_audit_full_snapshot.py"
)
DEADLINE = 5400
FULL_NAMES = frozenset(("authority", "replay", "security_audit", "orchestration_audit"))


def secure_live_audit() -> None:
    info = AUDIT.lstat()
    if (AUDIT.is_symlink() or not stat.S_ISREG(info.st_mode)
            or info.st_uid != 1000 or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1):
        raise PermissionError("LIVE_AUDIT_FILE_NOT_TRUSTED")


def full_pass(report: dict, code: int) -> bool:
    if (code != 0 or report.get("status") != "pass"
            or report.get("failures") != []
            or report.get("provider_contacted") is not False
            or report.get("provider_credentials_used") is not False):
        return False
    if os.getenv("JASON_ORCHESTRATION_EVENT_JOURNAL_PROFILE",""):
        try:
            from orchestrator.journal_health import validate_full_evidence
            validate_full_evidence(report)
        except (OSError,ValueError,KeyError,TypeError,RuntimeError):
            return False
    files = report.get("files")
    if not isinstance(files, dict) or set(files) != FULL_NAMES:
        return False
    if (not isinstance(files.get("orchestration_audit"), dict)
            or files["orchestration_audit"].get("path") != str(AUDIT)):
        return False
    if any(not isinstance(x, dict) or x.get("integrity") != "ok"
           or x.get("present") is not True or x.get("mode") != "0o600"
           for x in files.values()):
        return False
    backup = report.get("backup_restore_proof")
    if not isinstance(backup, dict) or any(
        backup.get(k) != v for k, v in (
            ("backup_integrity", "ok"), ("restore_integrity", "ok"),
            ("backup_mode", "0o600"), ("restore_mode", "0o600"),
            ("counts_match", True),
        )
    ):
        return False
    keys = report.get("trusted_key_registry")
    if not isinstance(keys, dict):
        return False
    try:
        valid_keys = (keys.get("present") is True
                      and keys.get("mode") == "0o600"
                      and int(keys.get("active_records", 0) or 0) >= 1)
    except (TypeError, ValueError):
        return False
    delegations = report.get("delegations")
    return (valid_keys and isinstance(delegations, dict)
            and delegations.get("expired_active_records") == 0)


def failed(reason: str, code: int, *, stages: dict | None = None) -> dict:
    output = {
        "status": "fail", "failures": [reason],
        "snapshot_source_exit_code": code,
        "provider_contacted": False, "provider_credentials_used": False,
        "orchestration_audit_path": str(AUDIT),
    }
    if stages is not None:
        output["completed_stage_seconds"] = stages
    return output


def full_snapshot(*, output: Path = OUTPUT, archive: Path = ARCHIVE) -> int:
    checker = Path(__file__).with_name("openclaw_authority_operational_health.py")
    try:
        secure_live_audit()
        if checker.is_symlink() or not checker.is_file():
            raise PermissionError("PINNED_FULL_CHECKER_MISSING")
        with tempfile.TemporaryDirectory(
            prefix="jason-authority-live-audit-", dir=archive,
        ) as scratch:
            completed = subprocess.run(
                [
                    sys.executable, str(checker),
                    "--backup-temp-root", scratch,
                    "--orchestration-audit", str(AUDIT),
                ],
                check=False, capture_output=True, text=True, timeout=DEADLINE,
            )
    except subprocess.TimeoutExpired as exc:
        report = failed(
            "operational_health_timeout", 124,
            stages=completed_timeout_stages(exc.stderr),
        )
        report["snapshot_timeout_seconds"] = DEADLINE
        write_atomic_snapshot(output, report)
        return 124
    except (PermissionError, OSError):
        write_atomic_snapshot(output, failed("live_audit_proof_launch_denied", 2))
        return 2

    try:
        proof = json.loads(completed.stdout)
    except (ValueError, TypeError):
        proof = {}
    if not isinstance(proof, dict) or not full_pass(proof, completed.returncode):
        write_atomic_snapshot(output, failed("full_proof_missing_or_invalid", 2))
        return 2
    proof["snapshot_source_exit_code"] = 0
    write_atomic_snapshot(output, proof)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    path = Path(__file__).resolve(strict=True)
    info = path.stat()
    parent = path.parent.stat()
    if (path != TRUSTED_ENTRYPOINT or info.st_uid != 0
            or info.st_mode & 0o222 or parent.st_uid != 0
            or parent.st_mode & 0o022 or args.output != OUTPUT):
        raise SystemExit("GOVERNED_ROOT_INSTALL_AND_EXACT_OUTPUT_REQUIRED")
    return full_snapshot()


if __name__ == "__main__":
    raise SystemExit(main())
