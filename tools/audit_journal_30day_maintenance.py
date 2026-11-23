#!/usr/bin/env python3
"""Offline 30-day orchestration retention conversion and repeatable expiration.

No production paths, activation, provider effects, or archive of expired events.
Live execution is prohibited until a separately governed exact Root release
supplies admission/serialization/health/rollback and installs trusted source.
"""
from __future__ import annotations

from datetime import datetime,timezone,timedelta
from pathlib import Path
import sqlite3
import os
import stat
import time

PROTECTED_SOURCE=Path("/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3")
ARCHIVE=Path("/srv/jason/archive/engineering-artifacts")
INDEX="CREATE INDEX IF NOT EXISTS ix_orchestration_occurred_at ON orchestration_events(occurred_at,event_id)"


def require(v,code):
    if not v:
        raise PermissionError("AUDIT_RETENTION_30DAY_"+code)


def permitted_nonproduction_database(path,*,must_be_on_archive=False):
    p=Path(path).resolve(strict=True)
    require(p.is_file() and not p.is_symlink() and p!=PROTECTED_SOURCE,
            "PRODUCTION_SOURCE_FORBIDDEN")
    require(p.stat().st_uid==os.geteuid() and stat.S_IMODE(p.stat().st_mode)==0o600,
            "PRIVATE_WRITABLE_STAGING_CUSTODY")
    if must_be_on_archive:
        root=ARCHIVE.resolve(strict=True)
        require(root in p.parents and p.stat().st_dev==root.stat().st_dev,
                "SECOND_DRIVE_REQUIRED")
    return p


def exact_cutoff(now):
    require(now.tzinfo is not None,"TZ_AWARE_CLOCK")
    return (now.astimezone(timezone.utc)-timedelta(days=30)).isoformat()


def prepare_incremental_maintenance(path,*,must_be_on_archive=False):
    """One-time offline conversion; runs only on a stand-alone recent-only DB."""
    p=permitted_nonproduction_database(path,must_be_on_archive=must_be_on_archive)
    with sqlite3.connect(p,timeout=10) as db:
        mode=db.execute("PRAGMA journal_mode").fetchone()[0]
        require(mode in ("delete","truncate"),"SINGLE_FILE_OFFLINE_ONLY")
        require(db.execute("PRAGMA auto_vacuum").fetchone()[0] in (0,2),
                "SOURCE_AUTOVACUUM_UNEXPECTED")
        db.execute("PRAGMA auto_vacuum=INCREMENTAL")
        db.execute("VACUUM")
        db.execute(INDEX)
        db.commit()
        require(db.execute("PRAGMA auto_vacuum").fetchone()[0]==2,
                "INCREMENTAL_VACUUM_NOT_INSTALLED")
        require(db.execute("PRAGMA quick_check").fetchone()==("ok",),
                "OFFLINE_INTEGRITY")
    return {"maintenance_auto_vacuum":"INCREMENTAL","time_index":"ix_orchestration_occurred_at",
            "retention_days":30, "production_modified":False,
            "database_bytes":p.stat().st_size}


def expire_offline(path,*,now,limit=25000,maximum_batches=10000):
    p=permitted_nonproduction_database(path)
    require(0<limit<=25000 and 0<maximum_batches<=10000,"BOUNDED_BATCH")
    cutoff=exact_cutoff(now)
    started=time.monotonic()
    with sqlite3.connect(p,timeout=30,isolation_level=None) as db:
        db.execute("PRAGMA busy_timeout=30000")
        require(db.execute("PRAGMA auto_vacuum").fetchone()[0]==2,
                "INCREMENTAL_VACUUM_REQUIRED")
        require(db.execute("PRAGMA journal_mode").fetchone()[0] in ("delete","truncate"),
                "OFFLINE_SINGLE_FILE_ONLY")
        indexes={row[1] for row in db.execute("PRAGMA index_list(orchestration_events)")}
        require("ix_orchestration_occurred_at" in indexes,
                "TIMESTAMP_INDEX_REQUIRED")
        deleted=0
        batches=0
        while batches<maximum_batches:
            db.execute("BEGIN IMMEDIATE")
            changed=db.execute(
                "DELETE FROM orchestration_events WHERE rowid IN "
                "(SELECT rowid FROM orchestration_events WHERE occurred_at<? "
                "ORDER BY occurred_at LIMIT ?)",(cutoff,limit)
            ).rowcount
            db.execute("COMMIT")
            batches+=1
            deleted+=changed
            if changed==0:break
        else:
            raise TimeoutError("AUDIT_RETENTION_30DAY_BATCH_LIMIT")
        db.execute("PRAGMA incremental_vacuum")
        remaining_old=db.execute(
            "SELECT count(*) FROM orchestration_events WHERE occurred_at<?",
            (cutoff,)
        ).fetchone()[0]
        require(remaining_old==0,"RECENT_ONLY_NOT_VERIFIED")
        check=db.execute("PRAGMA quick_check").fetchone()
        require(check==("ok",),"POST_EXPIRATION_INTEGRITY")
        new_count=db.execute("SELECT COUNT(*) FROM orchestration_events").fetchone()[0]
    return {"cutoff_utc":cutoff,"deleted_expired_events":deleted,
      "remaining_old_events":0,"retained_events":new_count,
      "batches":batches,"bytes_after":p.stat().st_size,
      "sqlite_quick_check":"ok","production_modified":False,
      "duration_seconds":round(time.monotonic()-started,2)}
