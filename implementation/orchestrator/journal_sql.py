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
import shutil
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
            db.execute("INSERT INTO audit_journal_inflight VALUES (?,?,?)",
                       tuple(row) if len(row)==3 else (*row,0))
        db.commit()
    path.chmod(0o600)


def proof(path,*,deadline=None,chunks=None):
    with connection(path,deadline=deadline) as db:
        need(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","JOURNAL_FULL_INTEGRITY_FAILED")
        shape=[list(r) for r in db.execute(
            "SELECT name,sql FROM sqlite_master WHERE tbl_name='orchestration_events' ORDER BY name")]
        schema=sha256(canonical(shape)).hexdigest()
        digest=sha256();count=0;part=sha256();part_count=0;index=0
        expected=[] if chunks is None else list(chunks)
        while index<len(expected) and expected[index]["events"]==0:
            need(expected[index]["content_sha256"]==sha256(b"").hexdigest(),"JOURNAL_EMPTY_SEGMENT_PROOF");index+=1
        for row in db.execute("SELECT "+",".join(COLUMNS)+" FROM orchestration_events ORDER BY rowid"):
            encoded=canonical(list(row))+b"\n";digest.update(encoded);count+=1
            if chunks is not None:
                need(index<len(expected),"JOURNAL_RECONSTRUCTION_EXTRA_ROWS")
                part.update(encoded);part_count+=1
                if part_count==expected[index]["events"]:
                    need(part.hexdigest()==expected[index]["content_sha256"],"JOURNAL_RECONSTRUCTION_CONTENT_PARITY")
                    index+=1;part=sha256();part_count=0
                    while index<len(expected) and expected[index]["events"]==0:
                        need(expected[index]["content_sha256"]==sha256(b"").hexdigest(),"JOURNAL_EMPTY_SEGMENT_PROOF");index+=1
        if chunks is not None:
            need(index==len(expected) and part_count==0,"JOURNAL_RECONSTRUCTION_MISSING_ROWS")
    return {"integrity":"ok","events":count,"content_order":"rowid","content_sha256":digest.hexdigest(),
            "file_sha256":file_hash(path),"schema_sha256":schema}


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
        rows=[list(r) for r in db.execute("SELECT execution_id,remaining_bytes,provider_started FROM audit_journal_inflight")
              ] if "audit_journal_inflight" in tables else []
        epoch=db.execute("SELECT epoch FROM audit_journal_meta").fetchone()[0] if "audit_journal_meta" in tables else None
        watermark=db.execute("SELECT COALESCE(MAX(rowid),0) FROM orchestration_events").fetchone()[0]
        pending=db.execute("SELECT count(*),min(queued_at) FROM audit_journal_pending_outcomes").fetchone()             if "audit_journal_pending_outcomes" in tables else (0,None)
    return {"epoch":epoch,"watermark":watermark,"reservations":rows,
            "pending_outcomes":pending[0],
            "oldest_outcome_age_seconds":None if pending[1] is None else max(0,time.time()-pending[1])}


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


def rebuild(paths,target,proofs=None):
    need(paths and not os.path.lexists(target),"JOURNAL_ROLLBACK_TARGET_PRESENT")
    provided=[None]*len(paths) if proofs is None else proofs
    need(len(provided)==len(paths),"JOURNAL_RECONSTRUCTION_PROOF_COUNT")
    expected=[given if given is not None else proof(path) for path,given in zip(paths,provided)]
    need(all(p["integrity"]=="ok" and p["schema_sha256"]==expected[0]["schema_sha256"] for p in expected),
         "JOURNAL_RECONSTRUCTION_SOURCE_SCHEMA")
    # Copy the already indexed legacy baseline; never reinsert tens of millions
    # of historical rows through Python. Later segments are appended in SQLite.
    shutil.copyfile(paths[0],target);Path(target).chmod(0o600)
    need(file_hash(target)==expected[0]["file_sha256"],"JOURNAL_RECONSTRUCTION_SEED_BYTES")
    with connection(target,write=True) as dst:
        for index,path in enumerate(paths[1:],1):
            alias="journal_source_"+str(index)
            dst.execute("ATTACH DATABASE ? AS "+alias,(Path(path).as_uri()+"?mode=ro",))
            try:
                with dst:
                    try:
                        dst.execute("INSERT INTO orchestration_events("+",".join(COLUMNS)+") SELECT "+
                                    ",".join(COLUMNS)+" FROM "+alias+".orchestration_events ORDER BY rowid")
                    except sqlite3.IntegrityError as exc:raise RuntimeError("JOURNAL_HISTORY_CONFLICT") from exc
            finally:dst.execute("DETACH DATABASE "+alias)
    # One actual full target integrity/content scan independently validates EACH
    # source's ordered content hash, rather than combining hashes as if that were
    # a fresh whole-file proof. Custodied source proofs avoid another old scan.
    return proof(target,chunks=expected)


def legacy_restore_proof(source,target):
    need(not os.path.lexists(target),"JOURNAL_LEGACY_RESTORE_TARGET_PRESENT")
    shutil.copyfile(source,target);Path(target).chmod(0o600)
    with connection(target) as db:
        ids=[r[0] for r in db.execute(
            "SELECT event_id FROM orchestration_events WHERE rowid IN "
            "((SELECT min(rowid) FROM orchestration_events),(SELECT max(rowid) FROM orchestration_events))")]
    from .event_store import SQLiteOrchestrationEventStore
    legacy=SQLiteOrchestrationEventStore(target)
    try:
        for identifier in ids:
            need(legacy.get(identifier).event_id==identifier,"JOURNAL_LEGACY_READER_RESTORE_FAILED")
    finally:legacy.close()
    checkpoint(target)
    return {"proof":proof(target),"legacy_reader_gets":len(ids),
            "provider_contacted":False,"provider_credentials_used":False}


def archive_readback(source,profile):
    from .segmented_journal import JournalProfile,SegmentedOrchestrationEventStore
    p=JournalProfile(**{k:(Path(v) if k in ("active","control","archives","pending") else v)
                       for k,v in profile.items()})
    with connection(source) as db:
        rows=list(db.execute("SELECT * FROM orchestration_events WHERE rowid IN "
             "((SELECT min(rowid) FROM orchestration_events),(SELECT max(rowid) FROM orchestration_events))"))
    from .event_store import SQLiteOrchestrationEventStore
    store=SegmentedOrchestrationEventStore(p)
    try:
        for row in rows:
            need(store.get(row["event_id"])==SQLiteOrchestrationEventStore._from_row(row),
                 "JOURNAL_ARCHIVED_READER_PARITY_FAILED")
    finally:store.close()
    return {"reads_verified":True,"event_probes":len(rows),"provider_contacted":False}


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


def admission_barrier(path,enabled,block_invoking=False):
    # This is an explicitly scoped operational maintenance barrier, never a
    # grant or a way to execute provider work. Existing outcomes may finish.
    with connection(path,write=True) as db:
        if enabled:
            db.execute("""CREATE TRIGGER IF NOT EXISTS audit_journal_maintenance_admission
BEFORE INSERT ON orchestration_events
WHEN NEW.event_type = 'orchestration.request.received'
BEGIN SELECT RAISE(ABORT,'JASON_AUDIT_JOURNAL_MAINTENANCE'); END""")
        else:db.execute("DROP TRIGGER IF EXISTS audit_journal_maintenance_admission")
        if enabled and block_invoking:
            db.execute("""CREATE TRIGGER IF NOT EXISTS audit_journal_maintenance_invoking
BEFORE INSERT ON orchestration_events
WHEN NEW.event_type = 'orchestration.capability.invoking'
BEGIN SELECT RAISE(ABORT,'JASON_AUDIT_JOURNAL_MAINTENANCE'); END""")
        else:db.execute("DROP TRIGGER IF EXISTS audit_journal_maintenance_invoking")


def live_claim_count(cutoff):
    from datetime import datetime
    stamp=datetime.fromisoformat(cutoff.replace("Z","+00:00"))
    need(stamp.tzinfo is not None,"JOURNAL_DRAIN_CUTOFF_REQUIRES_TIMEZONE")
    path=Path("/var/lib/jason/governed-ticket-shared/governed-execution.sqlite3")
    with connection(path) as db:
        # Historical unresolved claims remain untouched. Only a current process
        # generation could still be executing an already-consumed provider write.
        count=0
        for row in db.execute("SELECT consumed_at FROM governed_action_approvals WHERE state='consumed'"):
            try:at=datetime.fromisoformat(row[0].replace("Z","+00:00"))
            except (ValueError,TypeError,AttributeError):raise RuntimeError("JOURNAL_CONSUMED_CLAIM_TIMESTAMP_UNKNOWN")
            need(at.tzinfo is not None,"JOURNAL_CONSUMED_CLAIM_TIMESTAMP_UNKNOWN")
            count+=at>=stamp
    return {"consumed_since_cutoff":count,"claim_mutations":0}


def dispatch(operation,args):
    if operation=="create_active":
        create_active(args["target"],args["epoch"],args.get("reservations",()));return {"created":True}
    if operation=="checkpoint":checkpoint(args["path"]);return {"checkpointed":True}
    if operation=="state":return active_state(args["path"])
    if operation=="proof":return proof(args["path"],deadline=time.monotonic()+args.get("seconds",10800))
    if operation=="snapshot":return snapshot(args["source"],args["target"])
    if operation=="filters":return filters(args["source"],args["directory"],args["identifier"],args["events"])
    if operation=="rebuild":return rebuild(args["paths"],args["target"],args.get("proofs"))
    if operation=="legacy_restore_proof":return legacy_restore_proof(args["source"],args["target"])
    if operation=="archive_readback":return archive_readback(args["source"],args["profile"])
    if operation=="reconcile_outcomes":
        from .segmented_journal import JournalProfile,SegmentedOrchestrationEventStore
        p=JournalProfile(**{k:(Path(v) if k in ("active","control","archives","pending") else v)
                           for k,v in args["profile"].items()})
        store=SegmentedOrchestrationEventStore(p)
        try:return store.reconcile_outcomes(args.get("maximum",100))
        finally:store.close()
    if operation=="append_sources":return append_sources(args["paths"],args["target"])
    if operation=="validate_filters":return validate_filters(args["source"],args["directory"],args["records"])
    if operation=="merge_tail":return merge_tail(**args)
    if operation=="tail_budget":return tail_budget(**args)
    if operation=="reader_probes":
        need(1<=len(args["paths"])<=2,"JOURNAL_PROBE_PATH_BOUND")
        identifiers=[]
        for path in args["paths"]:
            with connection(path) as db:
                identifiers.extend(r[0] for r in db.execute("SELECT event_id FROM orchestration_events WHERE rowid IN "
                    "((SELECT min(rowid) FROM orchestration_events),(SELECT max(rowid) FROM orchestration_events))"))
        return {"event_ids":list(dict.fromkeys(identifiers)),"provider_invocations":0}
    if operation=="live_claim_count":return live_claim_count(args["cutoff"])
    if operation=="barrier":
        admission_barrier(args["path"],args["enabled"],args.get("block_invoking",False));return {"enabled":args["enabled"]}
    raise PermissionError("JOURNAL_SQL_OPERATION_NOT_REGISTERED")
