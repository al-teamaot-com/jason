"""Stage C durable Ticket Core handoff: fail-closed SQLite copy primitive.

LIBRARY ONLY: No CLI, no root installer, no Owner authorization issuance.
An independently reviewed, signed root release must quiesce all producers,
hold the protected host transaction, and call this function BEFORE any
embedded/external hosting change. Never run against live production directly.
The previous source ledger is retained as immutable rollback evidence.
"""
from __future__ import annotations

import fcntl
from hashlib import sha256
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
from typing import Any
from urllib.parse import quote

OLD = Path("/var/lib/jason/openclaw/autonomy-operational-work.sqlite3")
NEW = Path("/var/lib/jason/ticket-core/autonomy-operational-work.sqlite3")

class LedgerSnapshotDenied(RuntimeError):
    pass

def _need(ok: bool, reason: str) -> None:
    if not ok:
        raise LedgerSnapshotDenied(reason)

def _regular(path: Path, uid: int) -> os.stat_result:
    _need(path.is_absolute() and ".." not in path.parts
          and not path.is_symlink() and not path.parent.is_symlink(),
          "CORE_SNAPSHOT_UNTRUSTED_PATH")
    try:
        s=path.lstat()
    except OSError as exc:
        raise LedgerSnapshotDenied("CORE_SNAPSHOT_MISSING_OBJECT") from exc
    _need(stat.S_ISREG(s.st_mode) and s.st_uid == uid
          and stat.S_IMODE(s.st_mode) == 0o600 and s.st_nlink == 1,
          "CORE_SNAPSHOT_UNTRUSTED_FILE")
    return s

def _sqlite_ro(db: Path) -> sqlite3.Connection:
    uri="file:" + quote(db.as_posix(), safe="/") + "?mode=ro"
    con=sqlite3.connect(uri, uri=True, timeout=6)
    con.execute("PRAGMA query_only=ON")
    return con

def _facts(db: Path) -> dict[str,Any]:
    con=_sqlite_ro(db)
    try:
        check=con.execute("PRAGMA quick_check").fetchone()
        _need(check is not None and check[0]=="ok",
              "CORE_SNAPSHOT_SQLITE_INTEGRITY_FAILED")
        required=("autonomy_ticket_scan_cycle","autonomy_ticket_worker_heartbeat")
        tables={r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        _need(all(t in tables for t in required),
              "CORE_SNAPSHOT_SCHEMA_MISSING")
        counts={name:int(con.execute(
            'SELECT COUNT(*) FROM "' + name.replace('"','""') + '"'
        ).fetchone()[0])
            for name in sorted(tables) if name.startswith("autonomy_")}
        latest=con.execute(
            "SELECT MAX(scanned_at) FROM autonomy_ticket_scan_cycle").fetchone()[0]
        _need(isinstance(latest,str) and len(latest)>0,
              "CORE_SNAPSHOT_SCAN_EVIDENCE_MISSING")
        return {"counts":counts,"latest_scan":latest}
    finally:
        con.close()

def _file_marker(path: Path) -> tuple[int,int,int,int] | None:
    try:
        s=path.lstat()
    except FileNotFoundError:
        return None
    _need(stat.S_ISREG(s.st_mode) and not path.is_symlink(),
          "CORE_SNAPSHOT_SIDECAR_NOT_REGULAR")
    return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)

def _journal_markers(path: Path) -> tuple[Any,Any]:
    return (
        _file_marker(Path(str(path)+"-wal")),
        _file_marker(path),
    )

def _same(actual:dict[str,Any], before:dict[str,Any])->bool:
    return actual == before

def snapshot_quiesced_ledger(
    source: Path, destination: Path, *, expected_uid:int=1000,
    expected_directory_uid:int=0,
) -> dict[str,Any]:
    """Snapshot full committed WAL-backed SQLite ledger under a free worker lock.

    REQUIREMENT FROM CALLER (not provided here): independent exact-Owner
    release transaction, no new provider claims, producer quiescence, one
    atomic rollback contract, freeze/hold/health readbacks.
    This function never stops workers, creates release approval, changes the
    production runtime, or activates the external worker.
    """
    source=Path(source); destination=Path(destination)
    src=_regular(source,expected_uid)
    lock=source.with_name(source.name+".owner.lock")
    ls=_regular(lock,expected_uid)
    _need(src.st_dev == ls.st_dev,"CORE_SNAPSHOT_DB_LOCK_DIFFERENT_FS")
    _need(destination.is_absolute() and ".." not in destination.parts
          and destination.parent != source.parent
          and not destination.is_symlink()
          and not destination.parent.is_symlink(),
          "CORE_SNAPSHOT_DESTINATION_NOT_ISOLATED")
    try:
        parent=destination.parent.lstat()
    except OSError as exc:
        raise LedgerSnapshotDenied("CORE_SNAPSHOT_DESTINATION_ROOT_MISSING") from exc
    _need(stat.S_ISDIR(parent.st_mode)
          and parent.st_uid == expected_directory_uid
          and stat.S_IMODE(parent.st_mode) == 0o700
          and parent.st_dev == src.st_dev,
          "CORE_SNAPSHOT_DESTINATION_ROOT_UNTRUSTED")
    new_lock=destination.with_name(destination.name+".owner.lock")
    _need(not destination.exists() and not destination.is_symlink()
          and not new_lock.exists() and not new_lock.is_symlink(),
          "CORE_SNAPSHOT_DESTINATION_ALREADY_PRESENT")

    fd=os.open(lock,os.O_RDWR|getattr(os,"O_NOFOLLOW",0)
               |getattr(os,"O_CLOEXEC",0))
    tmp:Path|None=None
    claimed=False
    staged_lock_inode:int|None=None
    installed=False
    try:
        st=os.fstat(fd)
        _need(st.st_dev==ls.st_dev and st.st_ino==ls.st_ino
              and st.st_uid==expected_uid,"CORE_SNAPSHOT_LOCK_INODE_CHANGED")
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            claimed=True
        except BlockingIOError as exc:
            raise LedgerSnapshotDenied("CORE_SNAPSHOT_WORKER_STILL_OWNS_LEDGER") from exc
        _need(_regular(source,expected_uid).st_ino == src.st_ino,
              "CORE_SNAPSHOT_SOURCE_INODE_CHANGED")
        markers=_journal_markers(source)
        old=_facts(source)
        new_fd,tmp_name=tempfile.mkstemp(
            prefix=".pmv4-c-snapshot-",suffix=".sqlite3",
            dir=destination.parent)
        tmp=Path(tmp_name)
        os.close(new_fd)
        read=_sqlite_ro(source)
        write=sqlite3.connect(tmp)
        try:
            read.backup(write,pages=64,sleep=0.01)
            write.commit()
        finally:
            write.close()
            read.close()
        copied=_facts(tmp)
        _need(_same(copied,old)
              and _journal_markers(source)==markers
              and _regular(lock,expected_uid).st_ino == ls.st_ino
              and _regular(source,expected_uid).st_ino == src.st_ino,
              "CORE_SNAPSHOT_SOURCE_CHANGED_DURING_BACKUP")
        with open(tmp,"rb") as f:
            digest=sha256()
            for chunk in iter(lambda:f.read(1024*1024),b""):
                digest.update(chunk)
        # Stage both new objects before installing the DB; no symlink aliases.
        lock_fd=os.open(new_lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY
                        |getattr(os,"O_NOFOLLOW",0),0o600)
        try:
            staged_lock_inode=os.fstat(lock_fd).st_ino
            os.fchmod(lock_fd,0o600)
            if os.geteuid()==0:
                os.fchown(lock_fd,expected_uid,expected_uid)
            os.fsync(lock_fd)
        finally:
            os.close(lock_fd)
        os.chmod(tmp,0o600)
        if os.geteuid()==0:
            os.chown(tmp,expected_uid,expected_uid)
        with open(tmp,"rb") as f:
            os.fsync(f.fileno())
        os.replace(tmp,destination)
        tmp=None
        installed=True
        dir_fd=os.open(destination.parent,os.O_RDONLY|os.O_DIRECTORY)
        try: os.fsync(dir_fd)
        finally: os.close(dir_fd)
        _need(_regular(destination,expected_uid).st_dev==src.st_dev
              and _regular(new_lock,expected_uid).st_dev==src.st_dev,
              "CORE_SNAPSHOT_TARGET_IDENTITY_FAILED")
        _need(_same(_facts(destination),copied),
              "CORE_SNAPSHOT_TARGET_READBACK_FAILED")
        _need(_journal_markers(source)==markers,
              "CORE_SNAPSHOT_SOURCE_CHANGED_AFTER_COMMIT")
        return {
            "status":"consistent_quiesced_snapshot",
            "source_device":src.st_dev,"source_inode":src.st_ino,
            "source_lock_inode":ls.st_ino,
            "new_ledger_inode":destination.stat().st_ino,
            "new_lock_inode":new_lock.stat().st_ino,
            "copied_sqlite_sha256":digest.hexdigest(),
            "scan_cycle_count":copied["counts"]["autonomy_ticket_scan_cycle"],
            "latest_scan":copied["latest_scan"],
            "source_retained":True,"external_worker_started":False,
            "provider_actions":False,
            "owner_authorization_issued":False,
        }
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
        # A failed pre-commit attempt may remove only the lock inode it just
        # created. Once DB is installed, retain both for root-audited recovery.
        if not installed and staged_lock_inode is not None:
            try:
                prior=new_lock.lstat()
                if (not new_lock.is_symlink()
                    and prior.st_ino==staged_lock_inode
                    and stat.S_ISREG(prior.st_mode)
                    and not destination.exists()):
                    new_lock.unlink()
            except FileNotFoundError:
                pass
        if claimed:
            fcntl.flock(fd,fcntl.LOCK_UN)
        os.close(fd)
