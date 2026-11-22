#!/usr/bin/env python3
"""Daily audit migration rehearsal using the real event schema and reader contract.

This is an engineering preparation tool, NOT a production installer. Workspaces
must start empty. No caller can select a production database or a provider.
"""
from __future__ import annotations

from contextlib import contextmanager, closing
from datetime import datetime, timezone
from hashlib import sha256
import fcntl
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import time
from uuid import uuid4

from orchestrator.event_store import OrchestrationEvent, SQLiteOrchestrationEventStore, _SCHEMA

COLUMNS = ("event_id", "schema_version", "event_type", "execution_id", "correlation_id",
           "organization_id", "principal_id", "capability_name", "stage", "payload", "occurred_at")
SQL_COLUMNS = ",".join(COLUMNS)
INSERT = "INSERT INTO orchestration_events (" + SQL_COLUMNS + ") VALUES (" + ",".join("?" for _ in COLUMNS) + ")"
FORMAT = "audit-journal-migration-rehearsal-v1"


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(path):
    result = sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024*1024), b""):
            result.update(part)
    return result.hexdigest()


def sync(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)


def atomic(path, value):
    temporary = path.with_name("." + path.name + "." + uuid4().hex)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(canonical(value)); output.flush(); os.fsync(output.fileno())
    os.replace(temporary, path); sync(path.parent)


@contextmanager
def database(path, *, writable=False):
    if not writable:
        meta = path.lstat()
        require(stat.S_ISREG(meta.st_mode) and meta.st_nlink == 1, "DATABASE_FILE_IDENTITY")
    db = sqlite3.connect(path.as_uri() + ("?mode=rw" if writable else "?mode=ro"), uri=True, timeout=5)
    if not writable: db.execute("PRAGMA query_only=ON")
    db.row_factory = sqlite3.Row
    try:
        yield db
        if writable: db.commit()
    except BaseException:
        if writable: db.rollback()
        raise
    finally: db.close()


def create_database(path):
    require(not os.path.lexists(path), "DATABASE_TARGET_ALREADY_EXISTS")
    db = sqlite3.connect(path)
    try:
        db.execute("PRAGMA journal_mode=WAL"); db.executescript(_SCHEMA); db.commit()
    finally: db.close()
    path.chmod(0o600)


def checkpoint(path):
    with database(path, writable=True) as db:
        row = db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        require(row[0] == 0 and row[1] == 0 and row[2] == 0, "WAL_CHECKPOINT_NOT_COMPLETE")
    require(not Path(str(path)+"-wal").exists() or Path(str(path)+"-wal").stat().st_size == 0,
            "NONEMPTY_WAL")


def require_no_observed_handles(path):
    """Fixture guard only. Denied /proc entries are NOT a production proof."""
    identity=path.stat()
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():continue
        try:
            for handle in (proc/"fd").iterdir():
                try:
                    meta=handle.stat()
                    require((meta.st_dev,meta.st_ino)!=(identity.st_dev,identity.st_ino),
                            "LEGACY_CONNECTION_STILL_OPEN")
                except (FileNotFoundError,PermissionError,ProcessLookupError):continue
        except (FileNotFoundError,PermissionError,ProcessLookupError):continue


def content_proof(path):
    """Full disposable-data proof; production budgets are a separate acceptance gate."""
    with database(path) as db:
        require(db.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "SQLITE_INTEGRITY_FAILED")
        h = sha256(); count = 0
        for row in db.execute("SELECT "+SQL_COLUMNS+" FROM orchestration_events ORDER BY event_id"):
            h.update(canonical(list(row))+b"\n"); count += 1
    return {"events": count, "content_sha256": h.hexdigest(), "file_sha256": digest(path)}


class Workspace:
    """A private, synthetic workspace. All paths are relative and confined."""
    def __init__(self, root):
        self.root = Path(root).absolute()
        require(not self.root.is_symlink() and self.root.is_dir(), "WORKSPACE_DIRECTORY_REQUIRED")
        meta = self.root.lstat()
        require(meta.st_uid == os.geteuid() and stat.S_IMODE(meta.st_mode) == 0o700,
                "PRIVATE_WORKSPACE_REQUIRED")
        self.catalog = self.root/"catalog.json"
        self.transaction = self.root/"transaction.json"
        self.gate = self.root/"writers.lock"
        require(json.loads(self.catalog.read_bytes())["format"] == FORMAT, "REHEARSAL_WORKSPACE_ONLY")

    @classmethod
    def create(cls, root):
        root = Path(root).absolute()
        if root.exists():
            require(root.is_dir() and not root.is_symlink() and not any(root.iterdir()), "EMPTY_WORKSPACE_REQUIRED")
        else: root.mkdir(mode=0o700)
        root.chmod(0o700)
        for name in ("pending", "archive", "evidence", "rollback", "secondary-copy"): (root/name).mkdir(mode=0o700)
        (root/"writers.lock").touch(mode=0o600)
        create_database(root/"live.sqlite3")
        atomic(root/"catalog.json", {"format":FORMAT, "mode":"legacy", "generation":0, "segments":[]})
        return cls(root)

    def path(self, name):
        require(isinstance(name,str) and name and not name.startswith("/") and
                ".." not in name.split("/") and "\x00" not in name, "RELATIVE_PATH_REQUIRED")
        path = self.root/name
        require(path.resolve().is_relative_to(self.root.resolve()) and
                all(not p.is_symlink() for p in (path, *path.parents) if p != self.root.parent),
                "LINKED_WORKSPACE_PATH")
        return path

    @contextmanager
    def locked(self, exclusive=False):
        fd = os.open(self.gate, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            meta = os.fstat(fd)
            require(stat.S_ISREG(meta.st_mode) and meta.st_nlink==1 and meta.st_uid==os.geteuid(),
                    "WRITER_GATE_IDENTITY")
            fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            yield
        finally: os.close(fd)

    def state(self, *, pending_allowed=False):
        require(pending_allowed or not self.transaction.exists(), "MIGRATION_RECOVERY_REQUIRED")
        value = json.loads(self.catalog.read_bytes())
        require(value["format"]==FORMAT and value["mode"] in ("legacy","segmented"), "CATALOG_SCHEMA")
        for segment in value["segments"]:
            self.path(segment["path"])
            require(segment["state"] in ("pending","sealed"), "SEGMENT_STATE")
        return value

    def paths(self, state):
        for segment in state["segments"]:
            if segment["state"]=="sealed":
                require(digest(self.path(segment["path"]))==segment["proof"]["file_sha256"],
                        "SEALED_SEGMENT_HASH_MISMATCH")
        return [self.path(s["path"]) for s in state["segments"]] + [self.root/"live.sqlite3"]

    def get(self, event_id):
        return next(iter(self.query("event_id",event_id)),None)

    def query(self, key, value):
        require(key in ("event_id","execution_id","correlation_id"), "READER_KEY_NOT_ALLOWED")
        with self.locked():
            state = self.state(); found = {}
            for path in self.paths(state):
                with database(path) as db:
                    for row in db.execute("SELECT * FROM orchestration_events WHERE "+key+"=?",(value,)):
                        require(row["event_id"] not in found, "DUPLICATE_HISTORY_EVENT")
                        found[row["event_id"]] = SQLiteOrchestrationEventStore._from_row(row)
            return tuple(sorted(found.values(),key=lambda e:(e.occurred_at,e.event_id)))

    def list_by_execution(self, execution_id): return self.query("execution_id",execution_id)
    def list_by_correlation(self, correlation_id): return self.query("correlation_id",correlation_id)

    def append_event(self, event):
        with self.locked():
            state = self.state()
            # Correctness reference implementation. A production archive locator
            # must meet the specified fan-out/latency budget before activation.
            for path in self.paths(state):
                with database(path) as db:
                    require(db.execute("SELECT 1 FROM orchestration_events WHERE event_id=?",
                                       (event.event_id,)).fetchone() is None, "EVENT_ALREADY_EXISTS")
            row = (event.event_id,event.schema_version,event.event_type,event.execution_id,event.correlation_id,
                   event.organization_id,event.principal_id,event.capability_name,event.stage,
                   json.dumps(dict(event.payload),sort_keys=True,separators=(",",":")),
                   event.occurred_at.astimezone(timezone.utc).isoformat())
            try:
                with database(self.root/"live.sqlite3",writable=True) as db: db.execute(INSERT,row)
            except sqlite3.IntegrityError as exc: raise RuntimeError("EVENT_ALREADY_EXISTS") from exc


class Migration:
    def __init__(self, workspace, *, fault=lambda _:None):
        self.w,self.fault = workspace,fault

    def cutover_or_rotate(self):
        w=self.w
        with w.locked(exclusive=True):
            state=w.state()
            before=w.root/"live.sqlite3"
            require_no_observed_handles(before)
            checkpoint(before)
            segment_id=uuid4().hex
            segment={"id":segment_id,"path":"pending/"+segment_id+".sqlite3","state":"pending"}
            after={**state,"mode":"segmented","generation":state["generation"]+1,
                   "segments":[*state["segments"],segment]}
            atomic(w.transaction,{"operation":"rotate","before":state,"after":after,"segment":segment})
            self.fault("intent")
            os.replace(before,w.path(segment["path"]));sync(w.root);sync(w.root/"pending")
            self.fault("renamed")
            create_database(before)
            self.fault("new_active")
            atomic(w.catalog,after)
            self.fault("published")
            self.recover_locked()

    def recover(self):
        with self.w.locked(exclusive=True): self.recover_locked()

    def recover_locked(self):
        w=self.w
        if not w.transaction.exists():return
        tx=json.loads(w.transaction.read_bytes())
        require(tx["operation"] in ("rotate","rollback"),"UNKNOWN_MIGRATION_OPERATION")
        if tx["operation"]=="rotate":
            live=w.root/"live.sqlite3"; pending=w.path(tx["segment"]["path"])
            if not pending.exists():
                require(w.state(pending_allowed=True)==tx["before"],"UNEXPECTED_CATALOG")
                checkpoint(live);os.replace(live,pending);sync(pending.parent);sync(w.root)
            if not live.exists():create_database(live)
            current=w.state(pending_allowed=True)
            require(current in (tx["before"],tx["after"]),"UNEXPECTED_CATALOG")
            if current==tx["before"]:atomic(w.catalog,tx["after"])
        else:
            live=w.root/"live.sqlite3"; old=w.path(tx["preserve_active"]); target=w.path(tx["target"])
            if not old.exists():
                checkpoint(live);os.replace(live,old);sync(old.parent);sync(w.root)
            if target.exists():os.replace(target,live);sync(w.root)
            require(live.exists(),"ROLLBACK_CANONICAL_FILE_MISSING")
            require(content_proof(live)==tx["proof"],"ROLLBACK_RECOVERY_CONTENT_MISMATCH")
            atomic(w.catalog,tx["after"])
        atomic(w.root/"evidence"/(uuid4().hex+".json"),{"status":"transaction_completed",**tx})
        w.transaction.unlink();sync(w.root)

    def seal_pending(self):
        """Copy/verify the closed data outside the writer gate, then publish."""
        w=self.w
        with w.locked():
            state=w.state(); pending=[s for s in state["segments"] if s["state"]=="pending"]
        for segment in pending:
            source=w.path(segment["path"])
            before=source.stat()
            target=w.root/"archive"/(segment["id"]+".sqlite3")
            temporary=target.with_suffix(".staging")
            if temporary.exists():temporary.unlink()
            if not target.exists():
                with database(source) as src, closing(sqlite3.connect(temporary)) as dst:
                    src.backup(dst)
                    # Standalone archives require no writable WAL/SHM directory.
                    require(dst.execute("PRAGMA journal_mode=DELETE").fetchone()[0]=="delete",
                            "ARCHIVE_STANDALONE_FORMAT_REQUIRED")
                temporary.chmod(0o600)
            candidate=target if target.exists() else temporary
            # Existing un-published output is an unknown copy outcome. Recover
            # it by real parity/readback, never overwrite it or assert success.
            original_proof=content_proof(source); copy_proof=content_proof(candidate)
            require(original_proof["events"]==copy_proof["events"] and
                    original_proof["content_sha256"]==copy_proof["content_sha256"],"ARCHIVE_CONTENT_MISMATCH")
            require((before.st_ino,before.st_size,before.st_mtime_ns)==
                    (source.stat().st_ino,source.stat().st_size,source.stat().st_mtime_ns),"CLOSED_SEGMENT_CHANGED")
            if candidate==temporary:
                with temporary.open("rb") as f: os.fsync(f.fileno())
                os.replace(temporary,target);sync(target.parent)
            target.chmod(0o400)
            self.fault("archive_verified_before_catalog")
            with w.locked(exclusive=True):
                current=w.state()
                require(segment in current["segments"],"ARCHIVE_CATALOG_CHANGED")
                sealed={**segment,"path":str(target.relative_to(w.root)),"state":"sealed","proof":copy_proof,
                        "before_image_path":segment["path"],
                        "before_image_sha256":original_proof["file_sha256"]}
                atomic(w.catalog,{**current,"generation":current["generation"]+1,
                    "segments":[sealed if s["id"]==segment["id"] else s for s in current["segments"]]})
            # Retain local before-images in preparation/rehearsal. Production
            # space reclamation has its own verified-custody acceptance gate.

    def secondary_copy(self, segment_id):
        """Synthetic second copy; this does NOT prove independent backup custody."""
        w=self.w
        with w.locked():
            state=w.state()
            segment=next(s for s in state["segments"] if s["id"]==segment_id)
            require(segment["state"]=="sealed","ARCHIVE_NOT_SEALED")
            source=w.path(segment["path"])
            require(digest(source)==segment["proof"]["file_sha256"],"ARCHIVE_CHANGED")
            destination=w.root/"secondary-copy"/(segment_id+".sqlite3")
            require(not os.path.lexists(destination),"SECONDARY_COPY_TARGET_EXISTS")
            with source.open("rb") as src, destination.open("xb") as dst:
                shutil.copyfileobj(src,dst);dst.flush();os.fsync(dst.fileno())
            destination.chmod(0o400);sync(destination.parent)
            require(digest(destination)==segment["proof"]["file_sha256"],"SECONDARY_COPY_MISMATCH")
            return {"scope":"synthetic_rehearsal_only","path":str(destination.relative_to(w.root)),
                    "sha256":digest(destination),"independent_backup_verified":False}

    def reclaim_synthetic_before_image(self, segment_id, copy):
        """Exercise guarded space reclamation on synthetic data only."""
        w=self.w
        require(copy.get("scope")=="synthetic_rehearsal_only","COPY_RECEIPT_REQUIRED")
        with w.locked(exclusive=True):
            state=w.state()
            segment=next(s for s in state["segments"] if s["id"]==segment_id)
            require(segment["state"]=="sealed","ARCHIVE_NOT_SEALED")
            expected=segment["proof"]["file_sha256"]
            require(copy["sha256"]==expected and digest(w.path(copy["path"]))==expected
                    and digest(w.path(segment["path"]))==expected,"VERIFIED_COPIES_REQUIRED")
            before=w.path(segment["before_image_path"])
            require(before.parent==w.root/"pending" and before!=w.root/"live.sqlite3",
                    "RECLAIM_SCOPE_DENIED")
            if before.exists():
                require(digest(before)==segment["before_image_sha256"],"BEFORE_IMAGE_CHANGED")
                before.unlink();sync(before.parent)
            updated={**segment,"synthetic_before_image_reclaimed":True}
            atomic(w.catalog,{**state,"generation":state["generation"]+1,
                "segments":[updated if s["id"]==segment_id else s for s in state["segments"]]})

    def prepare_rollback(self):
        """Build/fully verify older history while current writers can continue."""
        w=self.w
        target=w.root/"rollback"/(uuid4().hex+".sqlite3")
        with w.locked():
            state=w.state(); require(state["mode"]=="segmented","NOT_SEGMENTED")
            snapshot=w.root/"rollback"/(uuid4().hex+".snapshot")
            with database(w.root/"live.sqlite3") as src, closing(sqlite3.connect(snapshot)) as dst:src.backup(dst)
            snapshot.chmod(0o600)
            with database(snapshot) as db:
                watermark=db.execute("SELECT COALESCE(MAX(rowid),0) FROM orchestration_events").fetchone()[0]
            history=w.paths(state)[:-1]
        create_database(target)
        with closing(sqlite3.connect(target)) as dst, dst:
            for path in [*history,snapshot]:
                with database(path) as src:
                    for row in src.execute("SELECT "+SQL_COLUMNS+" FROM orchestration_events ORDER BY rowid"):
                        try:dst.execute(INSERT,tuple(row))
                        except sqlite3.IntegrityError as exc:raise RuntimeError("ROLLBACK_HISTORY_CONFLICT") from exc
        proof=content_proof(target)
        plan={"generation":state["generation"],"target":str(target.relative_to(w.root)),
              "watermark":watermark,"proof":proof}
        atomic(target.with_suffix(".json"),plan)
        return plan

    def finish_rollback(self,plan):
        w=self.w
        with w.locked(exclusive=True):
            state=w.state()
            require_no_observed_handles(w.root/"live.sqlite3")
            require(state["generation"]==plan["generation"],"ROLLBACK_REBUILD_REQUIRED")
            target=w.path(plan["target"])
            require(content_proof(target)==plan["proof"],"ROLLBACK_TARGET_CHANGED")
            with database(w.root/"live.sqlite3") as src, database(target,writable=True) as dst:
                for row in src.execute("SELECT "+SQL_COLUMNS+" FROM orchestration_events WHERE rowid>? ORDER BY rowid",
                                       (plan["watermark"],)):
                    try:dst.execute(INSERT,tuple(row))
                    except sqlite3.IntegrityError as exc:raise RuntimeError("ROLLBACK_TAIL_CONFLICT") from exc
            # Small synthetic final proof only. The production plan explicitly
            # prohibits a whole-history scan under the final writer pause.
            final_proof=content_proof(target)
            checkpoint(target)
            preserve="pending/rollback-preserved-"+uuid4().hex+".sqlite3"
            after={**state,"mode":"legacy","generation":state["generation"]+1,"segments":[]}
            atomic(w.transaction,{"operation":"rollback","before":state,"after":after,
                "target":plan["target"],"preserve_active":preserve,"proof":final_proof})
            self.fault("rollback_intent")
            os.replace(w.root/"live.sqlite3",w.path(preserve));sync(w.root)
            self.fault("rollback_preserved")
            os.replace(target,w.root/"live.sqlite3");sync(w.root)
            self.fault("rollback_swapped")
            atomic(w.catalog,after)
            self.fault("rollback_published")
            self.recover_locked()
            return final_proof


def rehearsal(root):
    w=Workspace.create(root); m=Migration(w)
    def event(identifier):
        return OrchestrationEvent(event_id=identifier,event_type="rehearsal.event",
            execution_id="cross-day-execution",correlation_id="rehearsal",
            organization_id="aot",principal_id="synthetic-only",
            capability_name="synthetic.audit",stage="recorded",payload={"synthetic":True})
    w.append_event(event("before"));m.cutover_or_rotate()
    w.append_event(event("after-cutover"));m.seal_pending()
    m.cutover_or_rotate();w.append_event(event("after-rollover"));m.seal_pending()
    plan=m.prepare_rollback();w.append_event(event("after-rollback-preparation"))
    proof=m.finish_rollback(plan)
    require({e.event_id for e in w.list_by_execution("cross-day-execution")}==
            {"before","after-cutover","after-rollover","after-rollback-preparation"},"END_TO_END_PARITY_FAILED")
    return {"status":"synthetic_rehearsal_passed","events_preserved":proof["events"],
            "production_data_accessed":False,"production_ready":False,"workspace":str(w.root)}




def rollover_reason(*, opened_at, now, active_bytes, target_bytes=1073741824,
                    ceiling_bytes=2147483648):
    """Proposed local-day and size rules; this returns a decision, no schedule."""
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    require(opened_at.tzinfo is not None and now.tzinfo is not None and now>=opened_at,
            "VALID_MONOTONIC_TIME_REQUIRED")
    require(0<=active_bytes and 0<target_bytes<ceiling_bytes,"CAPACITY_POLICY_INVALID")
    if active_bytes>=ceiling_bytes:return "admission_ceiling"
    if active_bytes>=target_bytes:return "size"
    local=now.astimezone(ZoneInfo("America/New_York"))
    boundary=local.replace(hour=0,minute=15,second=0,microsecond=0)
    if local<boundary:boundary-=timedelta(days=1)
    return "daily" if opened_at.astimezone(timezone.utc)<boundary.astimezone(timezone.utc)<=now.astimezone(timezone.utc) else None


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rehearse",type=Path,required=True,help="A new/empty private synthetic workspace")
    args=parser.parse_args()
    print(json.dumps(rehearsal(args.rehearse),sort_keys=True))
