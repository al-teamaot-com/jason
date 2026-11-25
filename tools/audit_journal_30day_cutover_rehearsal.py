#!/usr/bin/env python3
"""Synthetic-only in-place SQLite replacement with verified backup and rollback.

The production canonical journal, its parent path and its hardlink/inode are
prohibited. Production requires a separately governed Root installer, exact
Owner authority, service quiescence, SQLite/WAL family backup and cutover proof.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import os
import shutil
import sqlite3
import stat

from tools.audit_journal_30day_maintenance import exact_cutoff, require, PROTECTED_SOURCE


def identity(path):
    p=Path(path).resolve(strict=True)
    st=p.lstat()
    require(stat.S_ISREG(st.st_mode) and not p.is_symlink()
        and st.st_uid==os.geteuid() and stat.S_IMODE(st.st_mode)==0o600
        and st.st_nlink==1, "SOURCE_REGULAR_PRIVATE")
    protected=PROTECTED_SOURCE
    if protected.exists():
        ps=protected.stat()
        require((st.st_dev,st.st_ino)!=(ps.st_dev,ps.st_ino),
            "PRODUCTION_INODE_FORBIDDEN")
    require(p!=protected and protected.parent not in p.parents,
        "PRODUCTION_PATH_FORBIDDEN")
    return p,st


def fingerprint(path):
    h=sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def single_file_snapshot(path):
    with sqlite3.connect("file:"+str(path)+"?mode=ro",uri=True,timeout=5) as db:
        db.execute("PRAGMA query_only=ON")
        require(db.execute("PRAGMA journal_mode").fetchone()[0]=="delete",
                "NON_STANDALONE_SQLITE_FAMILY")
        require(db.execute("PRAGMA quick_check").fetchone()==("ok",),
                "INVALID_SQLITE")
    require(not any(Path(str(path)+x).exists() for x in ("-wal","-shm","-journal")),
            "SQLITE_SIDECARS")


def in_place_rehearsal(*,source,replacement,backup,now,fault=None):
    """Rehearse EXACT same inode replacement: no root access or production."""
    src,st=identity(source)
    candidate,_=identity(replacement)
    backup=Path(backup)
    require(not backup.exists() and backup.parent.is_dir()
            and backup!=src and backup!=candidate, "CLEAN_BACKUP_REQUIRED")
    require(src!=candidate and src.stat().st_dev==candidate.stat().st_dev,
            "SYNTHETIC_SAME_VOLUME_REQUIRED")
    single_file_snapshot(src)
    single_file_snapshot(candidate)
    cutoff=exact_cutoff(now)
    with sqlite3.connect("file:"+str(candidate)+"?mode=ro",uri=True) as db:
        recent,old=db.execute(
            "SELECT count(*),sum(occurred_at<?) FROM orchestration_events",(cutoff,)
        ).fetchone()
    require((old or 0)==0,"OLD_EVENT_IN_REPLACEMENT")
    before=fingerprint(src)
    backup_fd=os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(backup_fd,"wb") as dst, src.open("rb") as origin:
        shutil.copyfileobj(origin,dst,4*1024*1024)
        dst.flush();os.fsync(dst.fileno())
    require(fingerprint(backup)==before,"BACKUP_INTEGRITY_FAILED")
    applied=False
    try:
        with src.open("r+b") as live, candidate.open("rb") as clean:
            assert os.fstat(live.fileno()).st_ino==st.st_ino
            live.seek(0)
            shutil.copyfileobj(clean,live,4*1024*1024)
            live.truncate(candidate.stat().st_size)
            live.flush();os.fsync(live.fileno())
        applied=True
        if fault: fault("after_replace")
        require(fingerprint(src)==fingerprint(candidate),"REPLACEMENT_HASH_MISMATCH")
        single_file_snapshot(src)
        with sqlite3.connect("file:"+str(src)+"?mode=ro",uri=True) as db:
            remaining,older=db.execute(
                "SELECT count(*),sum(occurred_at<?) FROM orchestration_events",(cutoff,)
            ).fetchone()
        require(remaining==recent and (older or 0)==0,"POST_REPLACE_RETENTION")
        return {"source_inode_preserved":src.stat().st_ino==st.st_ino,
             "before_bytes":st.st_size,"after_bytes":src.stat().st_size,
             "actual_logical_bytes_reclaimed":st.st_size-src.stat().st_size,
             "remaining_recent_rows":recent,
             "older_rows":0,"backup_sha256":before,"post_check":"ok",
             "production_modified":False}
    except BaseException:
        if applied or fingerprint(src)!=before:
            with src.open("r+b") as target,backup.open("rb") as saved:
                shutil.copyfileobj(saved,target,4*1024*1024)
                target.truncate(backup.stat().st_size)
                target.flush();os.fsync(target.fileno())
            require(fingerprint(src)==before,"ROLLBACK_CONTENT_HASH_MISMATCH")
            single_file_snapshot(src)
        raise
