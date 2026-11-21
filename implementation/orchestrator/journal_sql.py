"""Fixed SQLite operations for the governed journal controller.

The Root controller runs these operations as the existing writer UID. Paths are
selected by the installed controller policy, never by an MCP/Teams caller.
"""
from __future__ import annotations

from contextlib import contextmanager, closing
from hashlib import blake2b,sha256
import json
import os
from pathlib import Path
import sqlite3
import stat
import time

from .segmented_journal import COLUMNS, INSERT, META_SCHEMA, need
from .event_store import _SCHEMA


def file_hash(path):
    value=sha256()
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,"rb") as stream:
        meta=os.fstat(stream.fileno())
        need(stat.S_ISREG(meta.st_mode) and meta.st_nlink==1,"JOURNAL_HASH_FILE_IDENTITY")
        for chunk in iter(lambda:stream.read(1024*1024),b""):value.update(chunk)
    return value.hexdigest()


@contextmanager
def connection(path,*,write=False,deadline=None):
    path=Path(path)
    db=sqlite3.connect(path.as_uri()+("?mode=rw" if write else "?mode=ro"),uri=True,timeout=5)
    db.row_factory=sqlite3.Row
    db.execute("PRAGMA cache_size=-65536")
    db.execute("PRAGMA mmap_size=268435456")
    if not write:db.execute("PRAGMA query_only=ON")
    if deadline is not None:
        db.set_progress_handler(lambda:time.monotonic()>=deadline,1000)
    try:
        yield db
        if write:db.commit()
    except BaseException:
        if write:db.rollback()
        raise
    finally:db.close()


def canonical(value):return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()


def create_active(target,epoch,reservations=()):
    path=Path(target)
    need(not os.path.lexists(path),"JOURNAL_CREATE_TARGET_PRESENT")
    with closing(sqlite3.connect(path)) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(_SCHEMA+META_SCHEMA)
        db.execute("INSERT INTO audit_journal_meta VALUES (?)",(epoch,))
        for row in reservations:
            db.execute("INSERT INTO audit_journal_inflight VALUES (?,?)",row)
        db.commit()
    path.chmod(0o600)


def proof(path,*,deadline=None):
    with connection(path,deadline=deadline) as db:
        need(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","JOURNAL_FULL_INTEGRITY_FAILED")
        digest=sha256();count=0
        for row in db.execute("SELECT "+",".join(COLUMNS)+" FROM orchestration_events ORDER BY rowid"):
            digest.update(canonical(list(row))+b"\n");count+=1
    return {"integrity":"ok","events":count,"content_order":"rowid","content_sha256":digest.hexdigest(),
            "file_sha256":file_hash(path)}


def checkpoint(path):
    with connection(path,write=True) as db:
        mode=db.execute("PRAGMA journal_mode").fetchone()[0]
        row=db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        need(row[0]==0 and (mode!="wal" or row[1:]==(0,0)),"JOURNAL_WAL_NOT_CLOSED")
        need(db.execute("PRAGMA journal_mode=DELETE").fetchone()[0]=="delete",
             "JOURNAL_STANDALONE_FORMAT_REQUIRED")


def active_state(path):
    with connection(path) as db:
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        rows=[list(r) for r in db.execute("SELECT execution_id,remaining_bytes FROM audit_journal_inflight")
              ] if "audit_journal_inflight" in tables else []
        epoch=db.execute("SELECT epoch FROM audit_journal_meta").fetchone()[0] if "audit_journal_meta" in tables else None
        watermark=db.execute("SELECT COALESCE(MAX(rowid),0) FROM orchestration_events").fetchone()[0]
    return {"epoch":epoch,"watermark":watermark,"reservations":rows}


def snapshot(source,target,seconds=60):
    need(not os.path.lexists(target),"JOURNAL_SNAPSHOT_TARGET_PRESENT")
    with connection(source) as src,closing(sqlite3.connect(target)) as dst:
        deadline=time.monotonic()+seconds
        def progress(status,remaining,total):
            need(time.monotonic()<deadline,"JOURNAL_SNAPSHOT_DEADLINE")
        src.backup(dst,pages=256,sleep=0.01,progress=progress)
        need(dst.execute("PRAGMA journal_mode=DELETE").fetchone()[0]=="delete",
             "JOURNAL_SNAPSHOT_FORMAT")
    Path(target).chmod(0o600)
    return active_state(target)


def filters(source,directory,identifier,events):
    # One large pre-existing legacy journal uses its own existing indexes.
    # New daily artifacts have compact separate lookup filters.
    if events>5000000:return {}
    bits=max(64,events*12);out={}
    need(bits<=512*1024*1024,"JOURNAL_FILTER_SIZE_BOUND")
    for key in ("event_id","execution_id","correlation_id"):
        raw=bytearray((bits+7)//8)
        with connection(source) as db:
            for row in db.execute("SELECT "+key+" FROM orchestration_events"):
                digest=blake2b(str(row[0]).encode(),digest_size=16).digest()
                first=int.from_bytes(digest[:8],"little");second=int.from_bytes(digest[8:],"little")|1
                for i in range(7):
                    bit=(first+i*second)%bits;raw[bit//8]|=1<<(bit%8)
        target=Path(directory)/(identifier+"."+key+".filter")
        with target.open("xb") as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        target.chmod(0o600)
        out[key]={"file":target.name,"bits":bits,"hashes":7,"sha256":file_hash(target)}
    return out


def validate_filters(source,directory,records):
    for key,item in records.items():
        need(key in ("event_id","execution_id","correlation_id"),"JOURNAL_FILTER_KEY")
        raw=(Path(directory)/item["file"]).read_bytes()
        need(file_hash(Path(directory)/item["file"])==item["sha256"],"JOURNAL_FILTER_HASH")
        bits=item["bits"]
        need(len(raw)==(bits+7)//8 and item["hashes"]==7,"JOURNAL_FILTER_SHAPE")
        with connection(source) as db:
            for row in db.execute("SELECT "+key+" FROM orchestration_events"):
                digest=blake2b(str(row[0]).encode(),digest_size=16).digest()
                a=int.from_bytes(digest[:8],"little");b=int.from_bytes(digest[8:],"little")|1
                need(all(raw[((a+i*b)%bits)//8] & (1<<(((a+i*b)%bits)%8))
                         for i in range(7)),"JOURNAL_FILTER_FALSE_NEGATIVE")
    return {"all_keys_read_back":True,"filter_count":len(records)}


def append_sources(paths,target):
    with connection(target,write=True) as dst:
        dst.execute("BEGIN IMMEDIATE")
        for path in paths:
            with connection(path) as src:
                for row in src.execute("SELECT "+",".join(COLUMNS)+" FROM orchestration_events ORDER BY rowid"):
                    prior=dst.execute("SELECT "+",".join(COLUMNS)+" FROM orchestration_events WHERE event_id=?",
                                      (row["event_id"],)).fetchone()
                    if prior is None:dst.execute(INSERT,tuple(row))
                    else:need(tuple(prior)==tuple(row),"JOURNAL_HISTORY_CONFLICT")
    return proof(target)


def rebuild(paths,target):
    need(not os.path.lexists(target),"JOURNAL_ROLLBACK_TARGET_PRESENT")
    with closing(sqlite3.connect(target)) as dst:
        dst.executescript(_SCHEMA)
        with dst:
            for path in paths:
                with connection(path) as src:
                    for row in src.execute("SELECT "+",".join(COLUMNS)+" FROM orchestration_events ORDER BY rowid"):
                        try:dst.execute(INSERT,tuple(row))
                        except sqlite3.IntegrityError as exc:raise RuntimeError("JOURNAL_HISTORY_CONFLICT") from exc
    Path(target).chmod(0o600)
    return proof(target)


def tail_budget(source,watermark,maximum_rows=100000,maximum_bytes=134217728,seconds=10):
    count=size=0
    with connection(source,deadline=time.monotonic()+seconds) as db:
        for row in db.execute("SELECT "+",".join(COLUMNS)+" FROM orchestration_events WHERE rowid>? ORDER BY rowid",
                              (watermark,)):
            count+=1;size+=len(canonical(list(row)))
            need(count<=maximum_rows and size<=maximum_bytes,"JOURNAL_ROLLBACK_TAIL_BUDGET")
    return {"events":count,"bytes":size}


def merge_tail(source,target,watermark,maximum_rows,maximum_bytes,seconds):
    count=0;size=0;tail_hash=sha256();deadline=time.monotonic()+seconds
    with connection(source,deadline=deadline) as src,connection(target,write=True,deadline=deadline) as dst:
        dst.execute("BEGIN IMMEDIATE")
        for row in src.execute("SELECT "+",".join(COLUMNS)+" FROM orchestration_events WHERE rowid>? ORDER BY rowid",
                               (watermark,)):
            values=tuple(row);encoded=canonical(list(values))
            count+=1;size+=len(encoded)
            need(count<=maximum_rows and size<=maximum_bytes,"JOURNAL_ROLLBACK_TAIL_BUDGET")
            prior=dst.execute("SELECT "+",".join(COLUMNS)+" FROM orchestration_events WHERE event_id=?",
                              (row["event_id"],)).fetchone()
            if prior is not None:
                need(tuple(prior)==values,"JOURNAL_ROLLBACK_TAIL_CONFLICT")
            else:dst.execute(INSERT,values)
            tail_hash.update(encoded+b"\n")
    return {"events":count,"bytes":size,"sha256":tail_hash.hexdigest()}


def admission_barrier(path,enabled):
    # This is an explicitly scoped operational maintenance barrier, never a
    # grant or a way to execute provider work. Existing outcomes may finish.
    with connection(path,write=True) as db:
        if enabled:
            db.execute("""CREATE TRIGGER IF NOT EXISTS audit_journal_maintenance_admission
BEFORE INSERT ON orchestration_events
WHEN NEW.event_type = 'orchestration.request.received'
BEGIN SELECT RAISE(ABORT,'JASON_AUDIT_JOURNAL_MAINTENANCE'); END""")
        else:db.execute("DROP TRIGGER IF EXISTS audit_journal_maintenance_admission")


def dispatch(operation,args):
    if operation=="create_active":
        create_active(args["target"],args["epoch"],args.get("reservations",()));return {"created":True}
    if operation=="checkpoint":checkpoint(args["path"]);return {"checkpointed":True}
    if operation=="state":return active_state(args["path"])
    if operation=="proof":return proof(args["path"],deadline=time.monotonic()+args.get("seconds",10800))
    if operation=="snapshot":return snapshot(args["source"],args["target"])
    if operation=="filters":return filters(args["source"],args["directory"],args["identifier"],args["events"])
    if operation=="rebuild":return rebuild(args["paths"],args["target"])
    if operation=="append_sources":return append_sources(args["paths"],args["target"])
    if operation=="validate_filters":return validate_filters(args["source"],args["directory"],args["records"])
    if operation=="merge_tail":return merge_tail(**args)
    if operation=="tail_budget":return tail_budget(**args)
    if operation=="barrier":
        admission_barrier(args["path"],args["enabled"]);return {"enabled":args["enabled"]}
    raise PermissionError("JOURNAL_SQL_OPERATION_NOT_REGISTERED")
