"""Synthetic-only rehearsal of an atomic, SQLite-aware two-ledger snapshot.

No production CLI, service controls, or cutover operation is provided here.
A real cutover must first be integrated into the canonical Production Manager,
which supplies the signed Teams approval and a verified quiescence barrier.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from jason_secondary_ledger_preflight import FILES


class StagingDenied(RuntimeError):
    pass


SAFE_FIXTURE_ROOTS = (
    Path("/tmp"),
    Path("/srv/jason/archive/engineering-worktrees"),
)


def _synthetic_fixture_path(path: Path) -> bool:
    """Only developer test fixtures, never an arbitrary live host location."""
    if path.is_symlink():
        return False
    resolved = path.resolve(strict=False)
    return any(resolved != root and root in resolved.parents for root in SAFE_FIXTURE_ROOTS)


def _source_identity(path: Path) -> tuple[tuple[int, int, int, int], ...]:
    result = []
    for p in (path, path.with_name(path.name + "-wal")):
        if p.is_symlink():
            raise StagingDenied("source symlink denied")
        try:
            s = p.lstat()
        except FileNotFoundError:
            if p != path:
                result.append((0, 0, 0, 0))
                continue
            raise StagingDenied("source database missing") from None
        if (not stat.S_ISREG(s.st_mode) or s.st_uid != os.geteuid()
                or stat.S_IMODE(s.st_mode) != 0o600 or s.st_nlink != 1):
            raise StagingDenied("source database identity denied")
        result.append((s.st_ino, s.st_size, s.st_mtime_ns, s.st_dev))
    return tuple(result)


def _snapshot_identity(db: sqlite3.Connection, name: str) -> dict[str, object]:
    db.execute("PRAGMA query_only=ON")
    tables = [
        str(row[0]) for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    if not tables or len(tables) > 25:
        raise StagingDenied("unexpected snapshot schema")
    if name == FILES[0]:
        if "orchestration_events" not in tables:
            raise StagingDenied("orchestration table missing")
        count, rowid = db.execute(
            "SELECT COUNT(*), MAX(rowid) FROM orchestration_events"
        ).fetchone()
        if not count or rowid is None:
            raise StagingDenied("orchestration ledger empty")
        first = db.execute(
            "SELECT event_id FROM orchestration_events ORDER BY rowid LIMIT 1"
        ).fetchone()[0]
        last = db.execute(
            "SELECT event_id FROM orchestration_events ORDER BY rowid DESC LIMIT 1"
        ).fetchone()[0]
        # Event IDs are not disclosed in the evidence; hashes attest samples.
        sample = hashlib.sha256(
            (str(first) + ":" + str(last)).encode("utf-8")
        ).hexdigest()
        return {"tables": tables, "event_count": int(count),
                "last_rowid": int(rowid), "sample_sha256": sample}
    if "reflection_records" not in tables:
        raise StagingDenied("unexpected snapshot schema: reflection records missing")
    counts: dict[str, int] = {}
    for table in tables:
        safe = table.replace('"', '""')
        (quantity,) = db.execute('SELECT COUNT(*) FROM "' + safe + '"').fetchone()
        counts[table] = int(quantity)
    return {"tables": tables, "table_counts": counts}


def _logical_identity(path: Path, name: str) -> dict[str, object]:
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
        return _snapshot_identity(db, name)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stage_synthetic_quiesced_copy(source_root: Path, target: Path) -> dict[str, object]:
    """Stage a two-database proof in a TEST fixture, never on production paths.

    This is intentionally not callable against the protected primary ledger
    or the approved production archive location. Quiescence/Teams checks are
    outside this module, so activating a live copy would be unsafe.
    """
    source_root, target = Path(source_root), Path(target)
    if (not _synthetic_fixture_path(source_root)
            or not _synthetic_fixture_path(target)
            or target.parent != source_root.parent
            or source_root.is_symlink() or target.is_symlink()
            or target.exists() or target.parent.is_symlink()
            or not source_root.is_dir() or not target.parent.is_dir()
            or source_root.stat().st_uid != os.geteuid()
            or target.parent.stat().st_uid != os.geteuid()):
        raise StagingDenied("production or unsafe source/target denied")
    stamp_before = {
        name: _source_identity(source_root / name) for name in FILES
    }
    if target.resolve(strict=False) == source_root.resolve(strict=False):
        raise StagingDenied("source and destination alias")
    created = False
    try:
        target.mkdir(mode=0o700)
        created = True
        proofs = {}
        for name in FILES:
            source, destination = source_root / name, target / name
            before = _logical_identity(source, name)
            with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as origin:
                with closing(sqlite3.connect(destination)) as copied:
                    origin.backup(copied, pages=128, sleep=0.005)
            os.chmod(destination, 0o600)
            with closing(sqlite3.connect(destination)) as checker:
                if checker.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise StagingDenied("backup integrity denied")
            after = _logical_identity(destination, name)
            if before != after:
                raise StagingDenied("backup parity denied")
            proofs[name] = {
                "logical_identity": after,
                "bytes": destination.stat().st_size,
                "sha256": _sha256(destination),
            }
        if stamp_before != {
            name: _source_identity(source_root / name) for name in FILES
        }:
            raise StagingDenied("source mutated during presumed quiescence")
        record = {
            "schema_version": "1.0",
            "status": "synthetic_snapshot_staged_and_verified",
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "cutover_authorized": False,
            "source_retired": False,
            "test_only": True,
            "files": proofs,
        }
        manifest = target / "synthetic-manifest.json"
        with manifest.open("x", encoding="utf-8") as handle:
            os.chmod(manifest, 0o600)
            json.dump(record, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        return record
    except Exception:
        if created:
            # Only this fresh synthetic test destination is removed; production
            # directories are refused before any creation or deletion.
            shutil.rmtree(target)
        raise
