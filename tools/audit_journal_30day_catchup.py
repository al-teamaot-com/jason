#!/usr/bin/env python3
"""Read-only live-source delta reconciliation to a non-production 30-day candidate.

A successfully built candidate remains PREPRODUCTION ONLY. This tool does not
stop writers, move production database families, delete source events, or approve
a release. A protected Root switchover must separately prove a write barrier.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time

from tools.audit_journal_30day_staging import (
    COLUMNS, PRODUCTION, STAGING_ROOT, proof, cutoff_iso, file_hash
)


def update_candidate(source, candidate, *, min_source_rowid, cutoff, callback=None):
    source, candidate = Path(source), Path(candidate)
    proof(source.is_file() and not source.is_symlink()
          and candidate.is_file() and not candidate.is_symlink()
          and (source.stat().st_dev,source.stat().st_ino) !=
              (candidate.stat().st_dev,candidate.stat().st_ino),
          "SOURCE_CANDIDATE_SEPARATION")
    proof(min_source_rowid >= 0, "HIGH_WATER_MARK_REQUIRED")
    src = sqlite3.connect("file:" + str(source) + "?mode=ro", uri=True, timeout=3)
    src.execute("PRAGMA query_only=ON")
    dst = None
    count = 0
    older_removed = 0
    began = time.monotonic()
    try:
        src.execute("BEGIN")
        current_highwater = src.execute("SELECT MAX(rowid) FROM orchestration_events").fetchone()[0] or 0
        proof(current_highwater >= min_source_rowid, "SOURCE_ROWID_ROLLBACK")
        dst = sqlite3.connect(str(candidate),timeout=30,isolation_level=None)
        dst.execute("PRAGMA busy_timeout=30000")
        dst.execute("PRAGMA journal_mode=DELETE")
        dst.execute("PRAGMA synchronous=FULL")
        dst.execute("BEGIN IMMEDIATE")
        result=dst.execute("DELETE FROM orchestration_events WHERE occurred_at < ?",(cutoff,))
        older_removed=result.rowcount
        projection=",".join(COLUMNS)
        query=src.execute(
            "SELECT " + projection + " FROM orchestration_events "
            "WHERE rowid>? AND rowid<=? AND occurred_at>=? ORDER BY rowid",
            (min_source_rowid,current_highwater,cutoff)
        )
        insert="INSERT INTO orchestration_events ("+projection+") VALUES ("+",".join("?" for _ in COLUMNS)+")"
        while True:
            batch=query.fetchmany(2500)
            if not batch:break
            dst.executemany(insert,batch)
            count+=len(batch)
            if callback and count%25000==0:callback(count)
        stats=dst.execute(
            "SELECT COUNT(*),MIN(occurred_at),MAX(occurred_at),SUM(occurred_at<?)"
            " FROM orchestration_events",(cutoff,)
        ).fetchone()
        proof(stats[0]>=count and (stats[3] or 0)==0, "RETENTION_WINDOW_VALIDATION")
        dst.execute("COMMIT")
        result={
            "phase":"offline_catchup_only_not_activated",
            "cutoff_utc":cutoff,
            "source_snapshot_max_rowid":current_highwater,
            "last_applied_from_rowid":min_source_rowid,
            "rows_added":count, "expired_rows_removed_from_staging":older_removed,
            "destination_count":stats[0], "destination_earliest":stats[1],
            "destination_latest":stats[2],
            "duration_seconds":round(time.monotonic()-began,1),
            "production_source_read_only":True,"production_cutover_performed":False,
        }
        dst.close()
        dst=None
        src.execute("COMMIT")
        check=sqlite3.connect("file:"+str(candidate)+"?mode=ro",uri=True,timeout=3)
        try:
            check.execute("PRAGMA query_only=ON")
            proof(check.execute("PRAGMA quick_check").fetchone()==("ok",),
                "CANDIDATE_SQLITE_INTEGRITY")
            result["sqlite_quick_check"]="ok"
        finally:check.close()
        result["candidate_bytes"]=candidate.stat().st_size
        result["candidate_sha256"]=file_hash(candidate)
        return result
    except Exception:
        if dst is not None:
            try:dst.execute("ROLLBACK")
            except sqlite3.Error:pass
        raise
    finally:
        if dst is not None:dst.close()
        src.close()


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--outdir",required=True)
    ap.add_argument("--cutoff-utc",required=True)
    args=ap.parse_args()
    directory=Path(args.outdir)
    proof(directory.is_dir() and not directory.is_symlink()
          and directory.parent==STAGING_ROOT
          and directory.name.startswith("journal-retention-30day-")
          and directory.stat().st_dev != PRODUCTION.stat().st_dev,
          "OFFLINE_ARCHIVE_DRIVE_CUSTODY")
    now=datetime.now(timezone.utc)
    cutoff=datetime.fromisoformat(args.cutoff_utc)
    proof(cutoff.tzinfo is not None and now-timedelta(days=31) <
          cutoff.astimezone(timezone.utc) < now-timedelta(days=29),
          "30DAY_BOUNDARY")
    manifest=directory/"recent-30day-manifest.json"
    original=directory/"recent-30day-staged.sqlite3"
    proof(manifest.is_file() and original.is_file(), "COMPLETE_BASE_STAGE_REQUIRED")
    row=json.loads(manifest.read_text())
    proof(row["phase"]=="staged_recent_only_not_activated"
          and row["destination"]==str(original)
          and row["source"]==str(PRODUCTION)
          and row["cutoff_utc"] < args.cutoff_utc
          and row["destination_sha256"]==file_hash(original),
          "BASE_STAGE_MANIFEST_MISMATCH")
    candidate=directory/"recent-30day-catchup.sqlite3"
    proof(not candidate.exists(), "CATCHUP_ALREADY_EXISTS")
    shutil.copyfile(original,candidate,follow_symlinks=False)
    os.chmod(candidate,0o600)
    cutoff_utc=cutoff.astimezone(timezone.utc).isoformat()
    result=update_candidate(PRODUCTION,candidate,
        min_source_rowid=row["source_snapshot_max_rowid"],cutoff=cutoff_utc,
        callback=lambda count:print("OFFLINE_DELTA_ROWS",count,flush=True))
    receipt=directory/"recent-30day-catchup-manifest.json"
    proof(not receipt.exists(), "CATCHUP_RECEIPT_ALREADY_EXISTS")
    result["base_stage_sha256"]=row["destination_sha256"]
    fd=os.open(receipt,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"w") as out:
        json.dump(result,out,sort_keys=True,indent=2)
        out.write("\n");out.flush();os.fsync(out.fileno())
    print("RECENT_ONLY_OFFLINE_CATCHUP_COMPLETE",json.dumps(result,sort_keys=True),flush=True)


if __name__ == "__main__":main()
