#!/usr/bin/env python3
"""Read-only admission for a *future* Teams-governed second-drive SQLite cutover.

This file NEVER copies, checkpoints, moves, truncates, restarts or switches
production database files. It reports exact paths, device/headroom and bounded
SQLite metadata before an independent Release Manager transaction is proposed.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import stat
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

LEGACY = Path("/var/lib/jason/openclaw")
ARCHIVE = Path("/srv/jason/archive")
TARGET = ARCHIVE / "operational-ledgers"
FILES = ("orchestration-events.sqlite3", "reflection.sqlite3")
SIDECARS = ("-wal", "-shm")
GiB = 1024 ** 3
PROTECTED_MINIMUM_HEADROOM = 20 * GiB


class MigrationAdmissionDenied(RuntimeError):
    pass


def _regular_file(path: Path, *, uid: int) -> dict[str, int]:
    if path.is_symlink():
        raise MigrationAdmissionDenied("symlinked ledger path: " + path.name)
    try:
        st = path.lstat()
    except FileNotFoundError as error:
        raise MigrationAdmissionDenied("missing ledger file: " + path.name) from error
    if (not stat.S_ISREG(st.st_mode) or st.st_uid != uid or st.st_nlink != 1
            or stat.S_IMODE(st.st_mode) != 0o600):
        raise MigrationAdmissionDenied("unsafe ledger file identity: " + path.name)
    return {"bytes": st.st_size, "inode": st.st_ino, "device": st.st_dev}


def _bounded_sqlite_probe(path: Path, *, orchestration: bool) -> dict[str, object]:
    # mode=ro, query_only and a last-rowid lookup avoid long full integrity scans,
    # accidental schema creation, and reading private event payloads.
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=3)) as db:
            db.execute("PRAGMA query_only=ON")
            if db.execute("PRAGMA query_only").fetchone() != (1,):
                raise MigrationAdmissionDenied("SQLite query-only invariant failed")
            journal = str(db.execute("PRAGMA journal_mode").fetchone()[0])
            pages = int(db.execute("PRAGMA page_count").fetchone()[0])
            free = int(db.execute("PRAGMA freelist_count").fetchone()[0])
            if orchestration:
                schema = db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name='orchestration_events'"
                ).fetchone()
                if schema != ("orchestration_events",):
                    raise MigrationAdmissionDenied("expected immutable event schema missing")
                last = db.execute("SELECT MAX(rowid) FROM orchestration_events").fetchone()[0]
                if last is None:
                    raise MigrationAdmissionDenied("source event ledger unexpectedly empty")
                return {
                    "journal_mode": journal,
                    "pages": pages,
                    "free_pages": free,
                    "last_rowid": int(last),
                }
            schema = db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
            if int(schema) < 1:
                raise MigrationAdmissionDenied("reflection database has no schema")
            return {"journal_mode": journal, "pages": pages, "free_pages": free}
    except sqlite3.Error as error:
        raise MigrationAdmissionDenied("read-only SQLite probe failed") from error


def _device(path: Path) -> int:
    return path.stat().st_dev


def inspect(
    *,
    legacy: Path = LEGACY,
    archive: Path = ARCHIVE,
    target: Path | None = None,
    expected_uid: int | None = None,
) -> dict[str, object]:
    target = target or (archive / "operational-ledgers")
    uid = os.geteuid() if expected_uid is None else expected_uid
    now = datetime.now(timezone.utc).isoformat()
    evidence: dict[str, object] = {
        "schema_version": "1.0",
        "action": "read_only_secondary_ledger_admission",
        "checked_at": now,
        "source_root": str(legacy),
        "archive_mount": str(archive),
        "target_root": str(target),
        "cutover_authorized": False,
        "data_mutated": False,
        "services_restarted": False,
        "requires_exact_teams_release": True,
    }
    try:
        if (legacy.is_symlink() or archive.is_symlink()
                or not legacy.is_dir() or not archive.is_dir()
                or not os.path.ismount(archive)):
            raise MigrationAdmissionDenied("missing or symlinked independent archive mount")
        if _device(legacy) == _device(archive) or _device(Path("/")) == _device(archive):
            raise MigrationAdmissionDenied("archive shares primary device")
        if target.parent != archive or target.is_symlink():
            raise MigrationAdmissionDenied("unapproved target identity")
        if target.exists():
            # No migration may silently overwrite an existing staged or live target.
            raise MigrationAdmissionDenied("target already exists: requires immutable stage reconciliation")
        v = os.statvfs(archive)
        available = int(v.f_frsize * v.f_bavail)
        if (v.f_files > 0 and v.f_favail < 10000):
            raise MigrationAdmissionDenied("insufficient independent archive inodes")
        entries: dict[str, object] = {}
        total = 0
        for name in FILES:
            path = legacy / name
            entry = _regular_file(path, uid=uid)
            entry["sqlite"] = _bounded_sqlite_probe(
                path, orchestration=(name == "orchestration-events.sqlite3"))
            total += entry["bytes"]
            for suffix in SIDECARS:
                side = legacy / (name + suffix)
                if side.exists() or side.is_symlink():
                    val = _regular_file(side, uid=uid)
                    entry[suffix.lstrip("-")] = val["bytes"]
                    total += val["bytes"]
            entries[name] = entry
        evidence["source_files"] = entries
        evidence["source_total_bytes"] = total
        evidence["archive_available_bytes"] = available
        # Preserve a separate 20 GiB reserve after an *additional* complete
        # destination copy; no live source is removed as part of admission.
        if available - total < PROTECTED_MINIMUM_HEADROOM:
            raise MigrationAdmissionDenied("insufficient space for full preserved snapshot plus reserve")
        evidence["status"] = "preflight_pass"
    except (OSError, MigrationAdmissionDenied) as error:
        evidence["status"] = "preflight_denied"
        evidence["reason"] = str(error)[:200]
    return evidence


def inspect_container_routes(legacy: Path = LEGACY) -> dict[str, object]:
    """Prove both live writer containers still target one exact existing ledger.

    Docker's raw environment may contain credentials. Never return/log it:
    only these two exact safe route keys and openclaw mount metadata.
    """
    try:
        proc = subprocess.run(
            ["docker", "inspect", "jason-runtime", "jason-mcp-pilot"],
            capture_output=True, text=True, check=True, timeout=15,
        )
        raw = json.loads(proc.stdout)
        if not isinstance(raw, list) or len(raw) != 2:
            raise MigrationAdmissionDenied("unexpected live writer container set")
        proof: dict[str, object] = {}
        expected = str(legacy / FILES[0])
        for rec in raw:
            name = str(rec.get("Name") or "").lstrip("/")
            if name not in {"jason-runtime", "jason-mcp-pilot"} or name in proof:
                raise MigrationAdmissionDenied("unexpected writer identity")
            if rec.get("State", {}).get("Running") is not True:
                raise MigrationAdmissionDenied("writer container not running: " + name)
            env = dict(item.split("=", 1) for item in rec["Config"]["Env"]
                       if isinstance(item, str) and "=" in item)
            route = str(env.get("JASON_ORCHESTRATION_EVENTS_DB") or "")
            if route != expected:
                raise MigrationAdmissionDenied("split or unreviewed event route: " + name)
            mounts = [
                m for m in rec.get("Mounts") or []
                if m.get("Destination") == str(legacy)
            ]
            if (len(mounts) != 1 or mounts[0].get("Source") != str(legacy)
                    or mounts[0].get("RW") is not True):
                raise MigrationAdmissionDenied("unexpected writer data bind: " + name)
            proof[name] = {"source_path": route, "openclaw_mount_rw": True}
        if len(proof) != 2:
            raise MigrationAdmissionDenied("required writer container missing")
        return proof
    except (subprocess.SubprocessError, OSError, ValueError, KeyError, TypeError) as error:
        raise MigrationAdmissionDenied("cannot verify live writer route") from error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true", required=True)
    args = parser.parse_args()
    del args
    result = inspect()
    if result["status"] == "preflight_pass":
        try:
            result["live_writer_routes"] = inspect_container_routes()
        except MigrationAdmissionDenied as error:
            result["status"] = "preflight_denied"
            result["reason"] = str(error)[:200]
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "preflight_pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
