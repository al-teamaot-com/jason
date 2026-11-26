#!/usr/bin/env python3
"""Build a verified recent-only SQLite snapshot on the archive DRIVE.

Source is read ONLY. This script never executes on the production database as
a mutator, removes no historical source data, and never activates its output.
The active database can be switched only by a separately governed Root cutover.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import stat
import time

PRODUCTION = Path("/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3")
STAGING_ROOT = Path("/srv/jason/archive/engineering-artifacts")
COLUMNS = ("event_id", "schema_version", "event_type", "execution_id",
    "correlation_id", "organization_id", "principal_id", "capability_name",
    "stage", "payload", "occurred_at")
CREATE = """
CREATE TABLE orchestration_events (
    event_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    event_type TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    capability_name TEXT NOT NULL,
    stage TEXT NOT NULL,
    payload TEXT NOT NULL,
    occurred_at TEXT NOT NULL
)
"""
INDEXES = (
    "CREATE INDEX ix_orchestration_execution ON orchestration_events(execution_id, occurred_at, event_id)",
    "CREATE INDEX ix_orchestration_correlation ON orchestration_events(correlation_id, occurred_at, event_id)",
)


def proof(condition, code):
    if not condition:
        raise PermissionError("30DAY_STAGE_" + code)


def file_hash(path):
    h = sha256()
    with path.open("rb") as fd:
        for chunk in iter(lambda: fd.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def cutoff_iso(clock, days=30):
    proof(clock.tzinfo is not None and days == 30, "UTC_30DAY_ONLY")
    return (clock.astimezone(timezone.utc) - timedelta(days=days)).isoformat()


def stage_recent(source, destination, *, cutoff, batch_size=2500, callback=None):
    """Make a non-live, integrity checked snapshot. No source writes or rename."""
    source, destination = Path(source), Path(destination)
    proof(destination != source and not destination.exists(), "SOURCE_OR_DESTINATION")
    proof(source.is_file() and not source.is_symlink(), "SOURCE_NOT_REGULAR")
    dest_tmp = destination.with_name(destination.name + ".incomplete")
    proof(not dest_tmp.exists(), "PARTIAL_STAGING_ALREADY_EXISTS")
    src = sqlite3.connect("file:" + str(source) + "?mode=ro", uri=True, timeout=3)
    src.execute("PRAGMA query_only=ON")
    dst = None
    rows_copied = 0
    last_event = None
    total_before = None
    high_water = None
    began = time.monotonic()
    try:
        src.execute("BEGIN")
        source_columns = tuple(r[1] for r in src.execute("PRAGMA table_info(orchestration_events)"))
        proof(source_columns == COLUMNS, "SOURCE_SCHEMA_MISMATCH")
        total_before = src.execute("SELECT COUNT(*) FROM orchestration_events").fetchone()[0]
        high_water = src.execute("SELECT MAX(rowid) FROM orchestration_events").fetchone()[0] or 0
        dst = sqlite3.connect(str(dest_tmp), timeout=30, isolation_level=None)
        os.chmod(dest_tmp, 0o600)
        dst.execute("PRAGMA page_size=4096")
        dst.execute("PRAGMA journal_mode=OFF")
        dst.execute("PRAGMA synchronous=OFF")
        dst.execute("PRAGMA cache_size=-65536")
        dst.execute(CREATE)
        projection = ",".join(COLUMNS)
        select = src.execute(
            "SELECT " + projection + " FROM orchestration_events WHERE occurred_at>=? ORDER BY rowid",
            (cutoff,),
        )
        insert = "INSERT INTO orchestration_events (" + projection + ") VALUES (" + ",".join("?" for _ in COLUMNS) + ")"
        dst.execute("BEGIN")
        last_log = time.monotonic()
        while True:
            batch = select.fetchmany(batch_size)
            if not batch:
                break
            dst.executemany(insert, batch)
            rows_copied += len(batch)
            last_event = batch[-1][0]
            if callback and time.monotonic() - last_log > 15:
                callback(rows_copied, total_before, time.monotonic()-began)
                last_log = time.monotonic()
        dst.execute("COMMIT")
        for statement in INDEXES:
            dst.execute(statement)
        check = dst.execute("PRAGMA quick_check").fetchone()
        proof(check == ("ok",), "DESTINATION_SQLITE_QUICK_CHECK_FAILED")
        stats = dst.execute(
            "SELECT COUNT(*), SUM(occurred_at<?), MIN(occurred_at), MAX(occurred_at) FROM orchestration_events",
            (cutoff,)
        ).fetchone()
        proof(stats[0] == rows_copied and (stats[1] or 0) == 0
              and 0 <= rows_copied <= total_before, "RECENT_ONLY_PROOF_FAILED")
        dst.close()
        dst = None
        src.execute("COMMIT")
        source_info = source.stat()
        fd = os.open(dest_tmp, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(dest_tmp, destination)
        dfd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
        return {
            "schema_version":"1.0", "phase":"staged_recent_only_not_activated",
            "source":str(source), "destination":str(destination),
            "created_utc":datetime.now(timezone.utc).isoformat(),
            "cutoff_utc":cutoff, "retention_days":30,
            "source_snapshot_total":total_before,
            "source_snapshot_max_rowid":high_water,
            "source_snapshot_old_excluded":total_before - rows_copied,
            "destination_row_count":rows_copied,
            "destination_older_than_cutoff":0,
            "destination_earliest_at":stats[2],
            "destination_latest_at":stats[3],
            "destination_last_event_id":last_event,
            "destination_bytes":destination.stat().st_size,
            "destination_sha256":file_hash(destination),
            "source_inode_at_end":source_info.st_ino,
            "source_dev_at_end":source_info.st_dev,
            "source_was_read_only":True,
            "production_cutover_performed":False,
            "duration_seconds":round(time.monotonic() - began,1),
            "sqlite_quick_check":"ok",
        }
    finally:
        if dst is not None:
            dst.close()
        try:
            src.close()
        except sqlite3.Error:
            pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--outdir",required=True)
    p.add_argument("--cutoff-utc",required=True)
    args = p.parse_args()
    outdir = Path(args.outdir)
    proof(outdir.is_absolute() and outdir.parent == STAGING_ROOT and
          outdir.name.startswith("journal-retention-30day-")
          and outdir.is_dir() and not outdir.is_symlink(), "STAGING_PATH")
    proof(outdir.stat().st_uid==os.geteuid()
          and not outdir.stat().st_mode & 0o022, "STAGING_DIR_CUSTODY")
    proof(PRODUCTION.stat().st_dev != outdir.stat().st_dev, "MUST_STAGE_ON_SECOND_DRIVE")
    now=datetime.now(timezone.utc)
    given=datetime.fromisoformat(args.cutoff_utc)
    proof(given.tzinfo is not None and now-timedelta(days=31) < given.astimezone(timezone.utc)
          < now-timedelta(days=29), "CUTOFF_BOUNDARY")
    name = "recent-30day-staged.sqlite3"
    result = stage_recent(PRODUCTION, outdir/name, cutoff=given.astimezone(timezone.utc).isoformat(),
                          callback=lambda done,total,t: print("RECENT_ONLY_STAGE",done,total,
                              "SECONDS",round(t,1),flush=True))
    manifest = outdir/"recent-30day-manifest.json"
    proof(not manifest.exists(), "MANIFEST_ALREADY_EXISTS")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    fd = os.open(manifest,flags,0o600)
    with os.fdopen(fd,"w") as out:
        json.dump(result,out,sort_keys=True,indent=2)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    print("RECENT_ONLY_STAGE_COMPLETE",json.dumps(result,sort_keys=True),flush=True)


if __name__ == "__main__":
    main()
