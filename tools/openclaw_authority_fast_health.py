#!/usr/bin/env python3
"""Frequent read-only JKD-001 health; require a recent independent FULL proof.

The five-minute service must not perform SQLite integrity scans, DDL, backups,
or schema migrations while CCC/provider operations use the authority database.
The full integrity and restore proof remains mandatory on a separate timer.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import tempfile

from openclaw_authority_health_snapshot import write_atomic_snapshot
from openclaw_authority_operational_health import (
    DEFAULT_AUTHORITY, DEFAULT_REPLAY, DEFAULT_SECURITY, DEFAULT_ORCH,
    DEFAULT_REGISTRY, registry_health,
)

DEFAULT_OUTPUT = Path("/var/lib/jason/openclaw/operational-health.json")
DEFAULT_FULL = Path("/var/lib/jason/openclaw/operational-full-health.json")
MAX_FULL_AGE_SECONDS = 30 * 60 * 60
DATABASES = {
    "authority": DEFAULT_AUTHORITY,
    "replay": DEFAULT_REPLAY,
    "security_audit": DEFAULT_SECURITY,
    "orchestration_audit": DEFAULT_ORCH,
}


def full_proof(path: Path, databases: dict[str, Path], now: datetime) -> tuple[dict, int] | None:
    """Never accept a missing/stale/partial/unsafe file as an integrity proof."""
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
            return None
        if info.st_uid != os.geteuid():
            return None
        age = (now - datetime.fromtimestamp(info.st_mtime, tz=timezone.utc)).total_seconds()
        if not (0 <= age <= MAX_FULL_AGE_SECONDS):
            return None
        evidence = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(evidence, dict) or evidence.get("status") != "pass":
            return None
        if evidence.get("snapshot_source_exit_code") != 0:
            return None
        if evidence.get("provider_contacted") is not False or evidence.get("provider_credentials_used") is not False:
            return None
        files = evidence.get("files")
        if not isinstance(files, dict) or set(files) != set(databases):
            return None
        for name, database in databases.items():
            entry = files.get(name)
            if not isinstance(entry, dict) or (
                entry.get("path") != str(database) or entry.get("present") is not True
                or entry.get("mode") != "0o600" or entry.get("integrity") != "ok"
            ):
                return None
        backup = evidence.get("backup_restore_proof")
        if not isinstance(backup, dict) or not all((
            backup.get("backup_integrity") == "ok",
            backup.get("restore_integrity") == "ok",
            backup.get("backup_mode") == "0o600",
            backup.get("restore_mode") == "0o600",
            backup.get("counts_match") is True,
        )):
            return None
        registry = evidence.get("trusted_key_registry")
        if not isinstance(registry, dict) or (
            registry.get("present") is not True
            or registry.get("mode") != "0o600"
            or int(registry.get("active_records", 0) or 0) < 1
        ):
            return None
        if not isinstance(evidence.get("delegations"), dict):
            return None
        return evidence, int(age)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def adopt_legacy_proof(output: Path, full: Path, databases: dict[str, Path], now: datetime) -> None:
    """Copy the prior actual full PASS, preserving its age; NEVER fabricate one."""
    if full.exists() or full.is_symlink():
        return
    if full_proof(output, databases, now) is None:
        return
    full.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".full-health-adopt-", dir=full.parent)
    temp = Path(temp_name)
    try:
        os.close(fd)
        shutil.copy2(output, temp)
        os.chmod(temp, 0o600)
        if full_proof(temp, databases, now) is None:
            return
        os.replace(temp, full)
    finally:
        if temp.exists():
            temp.unlink()


def read_only_probe(path: Path) -> bool:
    """Short schema lookup with no schema initialization and no database write."""
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=3.0)) as conn:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
        return True
    except (sqlite3.Error, OSError, ValueError):
        return False


def current_delegations(path: Path) -> dict[str, int] | None:
    """A bounded read-only live delegation view; never extend permissions."""
    result = {"active": 0, "expired_active_records": 0, "inactive": 0}
    now = datetime.now(timezone.utc)
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=3.0)) as conn:
            conn.execute("PRAGMA query_only=ON")
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='delegations'").fetchone():
                return result
            for (raw,) in conn.execute("SELECT payload FROM delegations"):
                record = json.loads(raw)
                if record.get("status") != "active":
                    result["inactive"] += 1
                    continue
                expiry = datetime.fromisoformat(record["effective_until"])
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                result["expired_active_records" if expiry <= now else "active"] += 1
        return result
    except (sqlite3.Error, OSError, ValueError, KeyError, TypeError):
        return None


def check(
    *,
    output: Path,
    full_path: Path,
    databases: dict[str, Path] | None = None,
    registry_path: Path = DEFAULT_REGISTRY,
    now: datetime | None = None,
) -> dict:
    databases = DATABASES if databases is None else databases
    now = datetime.now(timezone.utc) if now is None else now
    adopt_legacy_proof(output, full_path, databases, now)
    verified = full_proof(full_path, databases, now)
    failures = []
    if verified is None:
        failures.append("full_integrity_proof_missing_stale_or_invalid")
    files = {}
    for name, path in databases.items():
        present = path.is_file()
        mode = oct(path.stat().st_mode & 0o777) if present else None
        readable = read_only_probe(path) if present and mode == "0o600" else False
        files[name] = {"path": str(path), "present": present, "mode": mode,
                       "readable": readable, "integrity": "not_run_in_frequent_check"}
        if not present or mode != "0o600" or not readable:
            failures.append(name + "_unavailable_or_unsafe")
    try:
        keys = registry_health(registry_path)
        if keys.get("present") is not True or keys.get("mode") != "0o600" or int(keys.get("active_records", 0)) < 1:
            failures.append("trusted_key_registry_unhealthy")
    except (OSError, ValueError, TypeError, KeyError):
        keys = {}
        failures.append("trusted_key_registry_unreadable")
    delegations = current_delegations(databases["authority"]) if files["authority"]["readable"] else None
    if delegations is None:
        failures.append("delegation_read_failed")
    evidence, full_age = verified if verified is not None else ({}, None)
    return {
        "status": "pass" if not failures else "fail",
        "check_mode": "frequent_read_only_plus_recent_full_integrity",
        "full_proof_age_seconds": full_age,
        "full_proof_status": "pass" if verified is not None else "missing_or_invalid",
        "files": files,
        "authority_counts": evidence.get("authority_counts", {}),
        "delegations": delegations or {},
        "trusted_key_registry": keys,
        "backup_restore_proof": evidence.get("backup_restore_proof", {}),
        "failures": failures,
        "provider_contacted": False,
        "provider_credentials_used": False,
        "snapshot_source_exit_code": 0 if not failures else 2,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed fast authority health with separate full integrity proof")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--full-evidence", type=Path, default=DEFAULT_FULL)
    args = parser.parse_args()
    report = check(output=args.output, full_path=args.full_evidence)
    write_atomic_snapshot(args.output, report)
    print(json.dumps({"status": report["status"], "check_mode": report["check_mode"],
                      "failures": report["failures"]}, sort_keys=True))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
