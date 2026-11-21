"""Opt-in bounded journal reader/writer. No authority or maintenance executor.

The immutable Root profile/catalog selects storage. Runtime consumers append only
to the current UID1000 journal and read Root-custodied closed history. The legacy
store remains the default until a separately governed release adopts this profile.
"""
from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager, closing
from dataclasses import dataclass
from hashlib import blake2b, sha256
from datetime import timezone
import fcntl
import json
import mmap
import os
from pathlib import Path
import sqlite3
import stat
import threading
import time

from .event_store import OrchestrationEvent, SQLiteOrchestrationEventStore, _SCHEMA

PROFILE = Path("/run/jason/audit-journal/profile.json")
CANONICAL = Path("/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3")
COLUMNS = ("event_id","schema_version","event_type","execution_id","correlation_id",
           "organization_id","principal_id","capability_name","stage","payload","occurred_at")
META_SCHEMA = """
CREATE TABLE audit_journal_meta (epoch TEXT PRIMARY KEY);
CREATE TABLE audit_journal_inflight (execution_id TEXT PRIMARY KEY, remaining_bytes INTEGER NOT NULL);
"""
INSERT = "INSERT INTO orchestration_events("+",".join(COLUMNS)+") VALUES ("+",".join("?" for _ in COLUMNS)+")"


class JournalUnavailable(RuntimeError): pass
class JournalCapacityExceeded(JournalUnavailable): pass


def need(ok,reason):
    if not ok:raise JournalUnavailable(reason)


def fingerprint(meta):
    return {name:getattr(meta,field) for name,field in (
        ("device","st_dev"),("inode","st_ino"),("bytes","st_size"),
        ("mtime_ns","st_mtime_ns"),("ctime_ns","st_ctime_ns"))}


def read_control(path,uid,mode=0o444,maximum=16*1024*1024):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,"rb") as stream:
        meta=os.fstat(stream.fileno())
        need(stat.S_ISREG(meta.st_mode) and meta.st_uid==uid and meta.st_gid==uid
             and meta.st_nlink==1 and stat.S_IMODE(meta.st_mode)==mode
             and 0<meta.st_size<=maximum,"JOURNAL_CONTROL_FILE_IDENTITY")
        raw=stream.read(maximum+1)
    need(len(raw)==meta.st_size,"JOURNAL_CONTROL_CHANGED")
    return json.loads(raw)


@dataclass(frozen=True)
class JournalProfile:
    active: Path
    control: Path
    archives: Path
    pending: Path
    custody_uid: int=0
    writer_uid: int=1000
    target_bytes: int=1073741824
    ceiling_bytes: int=2147483648
    maximum_event_bytes: int=262144
    execution_reserve_bytes: int=8388608
    maximum_inflight: int=32
    cached_archives: int=32
    fixture: bool=False

    @classmethod
    def load(cls,path=PROFILE,*,fixture=False):
        path=Path(path).absolute()
        if not fixture:
            need(path==PROFILE,"JOURNAL_FIXED_PROFILE_REQUIRED")
            owner=0
        else:
            owner=os.geteuid()
            need(not path.is_relative_to("/var/lib/jason") and not path.is_relative_to("/etc/jason"),
                 "JOURNAL_FIXTURE_ONLY")
        data=read_control(path,owner)
        need(data.get("schema_version")=="1.0" and data.get("enabled") is True
             and data.get("adoption") == ("fixture" if fixture else "root_adopted"),
             "JOURNAL_POLICY_NOT_ADOPTED")
        need(all(type(data.get(k)) is int for k in ("writer_uid","target_bytes","ceiling_bytes",
             "maximum_event_bytes","execution_reserve_bytes","maximum_inflight")),
             "JOURNAL_POLICY_INTEGER_BOUNDS")
        result=cls(active=Path(data["active"]),control=path.parent,
            archives=Path(data["archives"]),pending=Path(data["pending"]),
            custody_uid=owner,writer_uid=data["writer_uid"],
            target_bytes=data["target_bytes"],ceiling_bytes=data["ceiling_bytes"],
            maximum_event_bytes=data["maximum_event_bytes"],
            execution_reserve_bytes=data["execution_reserve_bytes"],
            maximum_inflight=data["maximum_inflight"],cached_archives=data.get("cached_archives",32),
            fixture=fixture)
        need(result.active.is_absolute() and result.archives.is_absolute() and result.pending.is_absolute()
             and 0<result.target_bytes<result.ceiling_bytes
             and 4096<=result.maximum_event_bytes<=1048576
             and result.execution_reserve_bytes>=(((result.maximum_event_bytes+4095)//4096)+16)*8192*8
             and result.maximum_inflight*result.execution_reserve_bytes<result.ceiling_bytes
             and 1<=result.maximum_inflight<=128 and 1<=result.cached_archives<=128,
             "JOURNAL_POLICY_BOUNDS")
        if not fixture:need(result.active==CANONICAL and result.writer_uid==1000,"JOURNAL_FIXED_ACTIVE_REQUIRED")
        for directory in (result.control,result.archives,result.pending):
            meta=directory.lstat()
            need(not directory.is_symlink() and stat.S_ISDIR(meta.st_mode) and meta.st_uid==owner
                 and not meta.st_mode&0o022,"JOURNAL_CUSTODY_DIRECTORY")
        return result

    @contextmanager
    def gate(self,exclusive=False,timeout=30):
        path=self.control/"handoff.lock"
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
        try:
            meta=os.fstat(fd)
            need(stat.S_ISREG(meta.st_mode) and meta.st_uid==self.custody_uid and meta.st_nlink==1
                 and stat.S_IMODE(meta.st_mode)==0o644,"JOURNAL_GATE_IDENTITY")
            deadline=time.monotonic()+timeout
            while True:
                try:
                    fcntl.flock(fd,(fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)|fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    need(time.monotonic()<deadline,"JOURNAL_HANDOFF_WAIT_EXCEEDED")
                    time.sleep(0.01)
            yield
        finally:os.close(fd)

    def catalog(self):
        value=read_control(self.control/"catalog.json",self.custody_uid)
        need(value.get("schema_version")=="1.0" and value.get("mode") in (
             "legacy","segmented_initializing","segmented"),"JOURNAL_TRANSITION_OR_INVALID_CATALOG")
        need(type(value.get("generation")) is int and isinstance(value.get("segments"),list),
             "JOURNAL_CATALOG_SCHEMA")
        identifiers=[entry.get("id") for entry in value["segments"]]
        need(len(set(identifiers))==len(identifiers),"JOURNAL_DUPLICATE_SEGMENT")
        return value

    def artifact(self,record,*,filter_record=None):
        selected=filter_record or record
        name=selected["file"]
        need(isinstance(name,str) and name and "/" not in name and "\\" not in name
             and name not in (".",".."),"JOURNAL_ARTIFACT_NAME")
        base=self.archives if record["state"]=="sealed" else self.pending
        need(record["state"] in ("sealed","pending"),"JOURNAL_SEGMENT_STATE")
        path=base/name
        meta=path.lstat()
        need(not path.is_symlink() and stat.S_ISREG(meta.st_mode) and meta.st_uid==self.custody_uid
             and meta.st_gid==self.custody_uid and meta.st_nlink==1
             and stat.S_IMODE(meta.st_mode)==0o444
             and fingerprint(meta)==selected["fingerprint"],"JOURNAL_CUSTODY_OR_FINGERPRINT_CHANGED")
        return path

    def active_identity(self):
        meta=self.active.lstat()
        need(not self.active.is_symlink() and stat.S_ISREG(meta.st_mode)
             and meta.st_uid==self.writer_uid and meta.st_gid==self.writer_uid and meta.st_nlink==1
             and stat.S_IMODE(meta.st_mode)==0o600,"JOURNAL_ACTIVE_FILE_IDENTITY")

    def active_bytes(self):
        total=self.active.lstat().st_size
        wal=Path(str(self.active)+"-wal")
        try:
            meta=wal.lstat()
            need(not wal.is_symlink() and stat.S_ISREG(meta.st_mode) and meta.st_uid==self.writer_uid,
                 "JOURNAL_WAL_IDENTITY")
            total+=meta.st_size
        except FileNotFoundError:pass
        return total


class SegmentedOrchestrationEventStore:
    def __init__(self,profile):
        self.profile=profile
        self._mutex=threading.RLock()
        self._cache=OrderedDict()
        self._generation=None

    @contextmanager
    def _active(self,catalog,*,write=False):
        p=self.profile;p.active_identity()
        db=sqlite3.connect(p.active.as_uri()+("?mode=rw" if write else "?mode=ro"),
                           uri=True,timeout=30,check_same_thread=False)
        db.row_factory=sqlite3.Row
        try:
            if not write:db.execute("PRAGMA query_only=ON")
            if catalog["mode"]!="legacy":
                epoch=db.execute("SELECT epoch FROM audit_journal_meta").fetchone()
                need(epoch is not None and epoch[0]==catalog["epoch"],"JOURNAL_ACTIVE_EPOCH_MISMATCH")
            yield db
            if write:db.commit()
        except BaseException:
            if write:db.rollback()
            raise
        finally:db.close()

    def _refresh(self,catalog):
        if self._generation!=catalog["generation"]:
            self.close()
            self._generation=catalog["generation"]
        for record in catalog["segments"]:
            self.profile.artifact(record)
            for item in record.get("filters",{}).values():
                self.profile.artifact(record,filter_record=item)

    def _archive(self,record):
        path=self.profile.artifact(record)
        key=("db",record["id"])
        if key in self._cache:
            value=self._cache.pop(key);self._cache[key]=value;return value
        # Standalone closed DELETE-mode files are independently sealed before
        # publication. Never use immutable=1 for an active or merely pending DB.
        uri=path.as_uri()+"?mode=ro"+("&immutable=1" if record["state"]=="sealed" else "")
        value=sqlite3.connect(uri,uri=True,timeout=5,check_same_thread=False)
        value.row_factory=sqlite3.Row
        value.execute("PRAGMA query_only=ON")
        self._cache[key]=value;self._trim()
        return value

    @contextmanager
    def _archive_query(self,record,sql,arguments):
        db=self._archive(record)
        try:yield db.execute(sql,arguments)
        finally:
            if record["state"]=="pending":
                self._cache.pop(("db",record["id"]),None)
                db.close()

    def _trim(self):
        while len(self._cache)>self.profile.cached_archives:
            _,item=self._cache.popitem(last=False)
            if isinstance(item,tuple):
                mapping,stream=item;mapping.close();stream.close()
            else:item.close()

    def _maybe(self,record,key,value):
        item=record.get("filters",{}).get(key)
        if item is None:return True
        path=self.profile.artifact(record,filter_record=item)
        need(type(item.get("bits")) is int and item["bits"]>=8 and item.get("hashes")==7
             and path.stat().st_size==(item["bits"]+7)//8,"JOURNAL_FILTER_BOUNDS")
        cachekey=("filter",record["id"],key)
        if cachekey in self._cache:
            cached=self._cache.pop(cachekey);self._cache[cachekey]=cached
        else:
            stream=path.open("rb");mapping=mmap.mmap(stream.fileno(),0,access=mmap.ACCESS_READ)
            cached=(mapping,stream);self._cache[cachekey]=cached;self._trim()
        raw=blake2b(str(value).encode(),digest_size=16).digest()
        first,second=int.from_bytes(raw[:8],"little"),int.from_bytes(raw[8:],"little")|1
        return all(cached[0][bit//8]&(1<<(bit%8)) for bit in (
            (first+i*second)%item["bits"] for i in range(7)))

    def _query(self,key,value):
        need(key in ("event_id","execution_id","correlation_id"),"JOURNAL_READER_KEY")
        with self._mutex,self.profile.gate():
            catalog=self.profile.catalog();self._refresh(catalog)
            found={}
            for record in catalog["segments"]:
                if self._maybe(record,key,value):
                    with self._archive_query(record,
                            "SELECT * FROM orchestration_events WHERE "+key+"=?",(value,)) as rows:
                        for row in rows:
                            need(row["event_id"] not in found,"JOURNAL_DUPLICATE_HISTORY_EVENT")
                            found[row["event_id"]]=SQLiteOrchestrationEventStore._from_row(row)
            with self._active(catalog) as db:
                for row in db.execute("SELECT * FROM orchestration_events WHERE "+key+"=?",(value,)):
                    need(row["event_id"] not in found,"JOURNAL_DUPLICATE_HISTORY_EVENT")
                    found[row["event_id"]]=SQLiteOrchestrationEventStore._from_row(row)
            return tuple(sorted(found.values(),key=lambda item:(item.occurred_at,item.event_id)))

    def get(self,event_id):return next(iter(self._query("event_id",event_id)),None)
    def list_by_execution(self,execution_id):return self._query("execution_id",execution_id)
    def list_by_correlation(self,correlation_id):return self._query("correlation_id",correlation_id)

    def append(self,event_type,payload):
        self.append_event(OrchestrationEvent(event_type=event_type,execution_id=str(payload["execution_id"]),
            correlation_id=str(payload["correlation_id"]),organization_id=str(payload["organization_id"]),
            principal_id=str(payload["principal_id"]),capability_name=str(payload["capability_name"]),
            stage=str(payload["stage"]),payload=dict(payload)))

    def append_event(self,event):
        serialized=json.dumps(dict(event.payload),sort_keys=True,separators=(",",":"),allow_nan=False)
        values=(event.event_id,event.schema_version,event.event_type,event.execution_id,event.correlation_id,
                event.organization_id,event.principal_id,event.capability_name,event.stage,serialized,
                event.occurred_at.astimezone(timezone.utc).isoformat())
        need(all(len(str(value).encode())<=512 for value in values[:9]),
             "JOURNAL_EVENT_METADATA_TOO_LARGE")
        bytecount=sum(len(str(v).encode()) for v in values)
        need(bytecount<=self.profile.maximum_event_bytes,"JOURNAL_EVENT_TOO_LARGE")
        with self._mutex,self.profile.gate():
            catalog=self.profile.catalog();self._refresh(catalog)
            for record in catalog["segments"]:
                if self._maybe(record,"event_id",event.event_id):
                    with self._archive_query(record,"SELECT 1 FROM orchestration_events WHERE event_id=?",
                                             (event.event_id,)) as rows:
                        need(rows.fetchone() is None,"JOURNAL_EVENT_ALREADY_EXISTS")
            with self._active(catalog,write=True) as db:
                if catalog["mode"]!="legacy":
                    # Serialize capacity reservations and the append in this ONE
                    # SQLite transaction; no cross-database atomicity assumption.
                    db.execute("BEGIN IMMEDIATE")
                    pending=db.execute("SELECT remaining_bytes FROM audit_journal_inflight WHERE execution_id=?",
                                       (event.execution_id,)).fetchone()
                    charge=(((bytecount+4095)//4096)+16)*8192
                    if event.event_type=="orchestration.request.received" and pending is None:
                        count=db.execute("SELECT count(*) FROM audit_journal_inflight").fetchone()[0]
                        reserve=self.profile.maximum_inflight*self.profile.execution_reserve_bytes
                        if count>=self.profile.maximum_inflight or (
                            self.profile.active_bytes()+reserve+charge>=self.profile.ceiling_bytes):
                            raise JournalCapacityExceeded("JOURNAL_NEW_EXECUTION_CAPACITY")
                        db.execute("INSERT INTO audit_journal_inflight VALUES (?,?)",
                                   (event.execution_id,self.profile.execution_reserve_bytes))
                        pending=(self.profile.execution_reserve_bytes,)
                    if pending is not None:
                        if pending[0]<charge:raise JournalCapacityExceeded("JOURNAL_EXECUTION_RESERVE_EXHAUSTED")
                        db.execute("UPDATE audit_journal_inflight SET remaining_bytes=remaining_bytes-? WHERE execution_id=?",
                                   (charge,event.execution_id))
                    elif self.profile.active_bytes()+charge+(
                            self.profile.maximum_inflight*self.profile.execution_reserve_bytes
                            )>=self.profile.ceiling_bytes:
                        raise JournalCapacityExceeded("JOURNAL_OBSERVER_CAPACITY")
                try:db.execute(INSERT,values)
                except sqlite3.IntegrityError as exc:
                    if "JASON_AUDIT_JOURNAL_MAINTENANCE" in str(exc):
                        raise JournalUnavailable("JOURNAL_MAINTENANCE_ADMISSION_PAUSED") from exc
                    raise ValueError("Orchestration event already exists: "+event.event_id) from exc
                if catalog["mode"]!="legacy" and (
                    event.event_type in ("orchestration.capability.completed","orchestration.capability.failed",
                                        "orchestration.request.terminated","orchestration.check_only.validated")
                    or (event.stage.casefold()=="denied" and event.event_type.startswith("orchestration."))):
                    db.execute("DELETE FROM audit_journal_inflight WHERE execution_id=?",(event.execution_id,))

    def close(self):
        with self._mutex:
            for item in self._cache.values():
                if isinstance(item,tuple):
                    mapping,stream=item;mapping.close();stream.close()
                else:item.close()
            self._cache.clear()


def configured_journal(path):
    """Called by the legacy factory only for the explicit adopted canonical path."""
    selected=os.getenv("JASON_ORCHESTRATION_EVENT_JOURNAL_PROFILE","")
    if not selected:return None
    need(selected==str(PROFILE),"JOURNAL_FIXED_PROFILE_REQUIRED")
    profile=JournalProfile.load(PROFILE)
    if Path(path).absolute()!=profile.active:return None
    return SegmentedOrchestrationEventStore(profile)
