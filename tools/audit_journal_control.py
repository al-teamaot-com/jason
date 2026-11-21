"""Bounded Root maintenance for the orchestration journal.

Production entry requires installed immutable code and an exact Root adoption
receipt. SQLite work is delegated to the existing writer UID. This module does
not authenticate an Owner, grant approval or deploy consumer images by itself.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import fcntl
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys
import time
from uuid import uuid4

from orchestrator.segmented_journal import JournalProfile,fingerprint,read_control,need
from orchestrator import journal_sql

ENTRY=Path("/usr/local/lib/jason/audit-journal/trusted/tools/audit_journal_control.py")
POLICY=Path("/etc/jason-owner-release/audit-journal-v1.json")
PRIVATE=Path("/var/lib/jason-audit-journal/private")
OWNER="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
ACTION="ADOPT-EXACT-DAILY-AUDIT-JOURNAL"
FIXTURE="bounded-audit-journal-native-fixture-v1"


def canonical(value):return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()


def atomic(path,value,mode=0o444,owner=None):
    temporary=path.with_name("."+path.name+"."+uuid4().hex)
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    try:
        with os.fdopen(fd,"wb") as stream:
            if owner is not None:os.fchown(stream.fileno(),owner,owner)
            os.fchmod(stream.fileno(),mode);stream.write(canonical(value));stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path);sync(path.parent)
    finally:
        if temporary.exists():temporary.unlink()


def sync(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


def require_no_handles(path):
    """Production calls run as Root; any unreadable process denies completeness."""
    identity=path.stat();my_pid=str(os.getpid())
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():continue
        try:
            handles=list((proc/"fd").iterdir())
        except (FileNotFoundError,ProcessLookupError):continue
        except PermissionError:
            if os.geteuid()==0:raise RuntimeError("JOURNAL_PROCESS_INVENTORY_INCOMPLETE")
            continue
        for handle in handles:
            try:meta=handle.stat()
            except (FileNotFoundError,ProcessLookupError):continue
            except PermissionError:
                if os.geteuid()==0:raise RuntimeError("JOURNAL_PROCESS_HANDLE_NOT_VERIFIED")
                continue
            need((meta.st_dev,meta.st_ino)!=(identity.st_dev,identity.st_ino),
                 "JOURNAL_LEGACY_HANDLE_STILL_OPEN")


class JournalController:
    def __init__(self,profile,private,work,local_work,*,fixture=False,fault=lambda _:None):
        self.p,self.private,self.work,self.local_work=profile,Path(private),Path(work),Path(local_work)
        self.fixture,self.fault=fixture,fault
        self.intent=self.private/"transaction.json"
        self.rollback=self.private/"rollback.json"
        if fixture:
            need(profile.fixture and (self.private.parent/"fixture.json").is_file(),
                 "JOURNAL_FIXTURE_REQUIRED")
            need(json.loads((self.private.parent/"fixture.json").read_bytes())["format"]==FIXTURE,
                 "JOURNAL_FIXTURE_FORMAT")
            need(not str(self.private).startswith(("/var/lib/jason","/etc/jason","/opt/jason")),
                 "JOURNAL_FIXTURE_PRODUCTION_PATH_DENIED")
        else:
            need(os.geteuid()==0 and Path(__file__).resolve()==ENTRY and sys.flags.isolated==1,
                 "JOURNAL_INSTALLED_ISOLATED_ROOT_REQUIRED")
        for directory in (self.private,self.work,self.local_work):
            meta=directory.lstat()
            need(not directory.is_symlink() and stat.S_ISDIR(meta.st_mode)
                 and meta.st_uid==profile.custody_uid and not meta.st_mode&0o022,
                 "JOURNAL_CONTROLLER_DIRECTORY_IDENTITY")

    @contextmanager
    def serialized(self):
        fd=os.open(self.private/"maintenance.lock",os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:
            meta=os.fstat(fd)
            need(stat.S_ISREG(meta.st_mode) and meta.st_uid==self.p.custody_uid and meta.st_nlink==1,
                 "JOURNAL_MAINTENANCE_LOCK")
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);yield
        finally:os.close(fd)

    @contextmanager
    def handoff(self):
        with self.p.gate(exclusive=True,timeout=30):
            start=time.monotonic();self._handoff_deadline=start+30
            try:yield
            finally:
                elapsed=time.monotonic()-start
                self._handoff_deadline=None
                self._json(self.private/"last-handoff.json",{
                    "elapsed_seconds":round(elapsed,6),"budget_seconds":30,
                    "within_budget":elapsed<=30,"observed_at":datetime.now(timezone.utc).isoformat()},0o400)
                need(elapsed<=30,"JOURNAL_HANDOFF_BUDGET_EXCEEDED")

    def _json(self,path,value,mode=0o444):
        atomic(path,value,mode,self.p.custody_uid)

    def _catalog(self,value):self._json(self.p.control/"catalog.json",value)

    def _job(self,*,local=False):
        base=self.local_work if local else self.work
        path=base/uuid4().hex;path.mkdir(mode=0o700)
        os.chown(path,self.p.writer_uid,self.p.writer_uid);path.chmod(0o700)
        return path

    def _sql(self,operation,args,*,seconds=10800):
        deadline=getattr(self,"_handoff_deadline",None)
        if deadline is not None:
            seconds=min(seconds,deadline-time.monotonic()-0.1)
            need(seconds>0,"JOURNAL_HANDOFF_DEADLINE")
            if operation in ("proof","snapshot","merge_tail","tail_budget"):
                args={**args,"seconds":min(args.get("seconds",seconds),seconds)}
        if self.fixture and self.p.writer_uid==os.geteuid():
            return journal_sql.dispatch(operation,args)
        need(os.geteuid()==0 and self.p.writer_uid==1000,"JOURNAL_WRITER_IDENTITY")
        # Only fixed installed code and a finite operation execute as UID1000.
        loader='import runpy,sys;sys.path.insert(0,sys.argv[1]);p=sys.argv[2];sys.argv=[p,*sys.argv[3:]];runpy.run_path(p,run_name="__main__")'
        completed=subprocess.run(["/usr/sbin/runuser","-u","al","--","/usr/bin/python3","-I","-B",
            "-c",loader,str(ENTRY.parent.parent/"implementation"),str(ENTRY),"--sql-operation",
            operation,"--sql-arguments",canonical(args).decode()],capture_output=True,text=True,
            timeout=seconds,check=False)
        if self.fixture and completed.returncode!=0:
            raise RuntimeError("FIXTURE_SQL_"+operation+":"+completed.stderr)
        need(completed.returncode==0,"JOURNAL_WRITER_OPERATION_FAILED")
        return json.loads(completed.stdout)

    def _cleanup_job(self,job):
        need(job.parent in (self.work,self.local_work) and not job.is_symlink(),
             "JOURNAL_WORK_CLEANUP_SCOPE")
        # Unlink only immediate regular files or symlinks: never follow a link,
        # recurse, remove a directory owned by an unrelated task or touch history.
        for child in job.iterdir():
            meta=child.lstat()
            need(stat.S_ISREG(meta.st_mode) or stat.S_ISLNK(meta.st_mode),
                 "JOURNAL_WORK_CLEANUP_UNEXPECTED_DIRECTORY")
            child.unlink()
        job.rmdir();sync(job.parent)

    def claim_initial_cutover(self,intent):
        need(not self.fixture,"JOURNAL_INITIAL_CLAIM_PRODUCTION_ONLY")
        fd=os.open(self.private/"initial-cutover-claimed.json",
                   os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400)
        with os.fdopen(fd,"wb") as stream:
            stream.write(canonical({"action":ACTION,"claimed_at":datetime.now(timezone.utc).isoformat(),
                "adoption_sha256":journal_sql.file_hash(self.private/"adoption.json"),
                "transaction":intent}))
            stream.flush();os.fsync(stream.fileno())
        sync(self.private)

    def _new_active(self,epoch,reservations):
        job=self._job(local=True);target=job/"new.sqlite3"
        self._sql("create_active",{"target":str(target),"epoch":epoch,"reservations":reservations},seconds=30)
        return target

    def _move(self,source,target,uid,mode):
        source,target=Path(source),Path(target)
        need(source.parent.stat().st_dev==target.parent.stat().st_dev,"JOURNAL_ATOMIC_MOVE_DEVICE")
        fd=os.open(source,os.O_RDONLY|os.O_NOFOLLOW)
        try:
            before=os.fstat(fd)
            need(stat.S_ISREG(before.st_mode) and before.st_nlink==1,"JOURNAL_MOVE_SOURCE_IDENTITY")
            os.replace(source,target)
            after=target.lstat()
            need(not target.is_symlink() and (after.st_dev,after.st_ino)==(before.st_dev,before.st_ino),
                 "JOURNAL_MOVE_SOURCE_CHANGED")
            os.fchown(fd,uid,uid);os.fchmod(fd,mode);os.fsync(fd)
        finally:os.close(fd)
        sync(source.parent);sync(target.parent)
        return fingerprint(target.stat())

    def _record(self,path,state,proof=None):
        return {"id":path.stem,"file":path.name,"state":state,
                "fingerprint":fingerprint(path.stat()),"proof":proof,
                "closed_at":datetime.now(timezone.utc).isoformat()}

    def transition(self,*,initial=False):
        p=self.p
        with self.serialized(),self.handoff():
            before=p.catalog()
            need((before["mode"]=="legacy")==initial,"JOURNAL_TRANSITION_MODE")
            p.active_identity()
            require_no_handles(p.active)
            active=self._sql("state",{"path":str(p.active)},seconds=30)
            identifier=uuid4().hex;epoch=uuid4().hex
            pending=p.pending/(identifier+".sqlite3")
            target=self._new_active(epoch,active["reservations"])
            after={**before,"mode":"segmented_initializing" if initial else before["mode"],
                "generation":before["generation"]+1,"epoch":epoch,
                "opened_at":datetime.now(timezone.utc).isoformat()}
            intent={"operation":"transition","before":before,"after":after,
                "pending":pending.name,"target":str(target),"identifier":identifier,
                "source_identity":{"device":p.active.stat().st_dev,"inode":p.active.stat().st_ino},
                "target_identity":{"device":target.stat().st_dev,"inode":target.stat().st_ino}}
            if initial and not self.fixture:
                self.claim_initial_cutover(intent)
                self.fault("initial_claim")
            self._json(self.intent,intent,0o400)
            self._catalog({**before,"mode":"transition"})
            self.fault("transition_intent")
            self._sql("checkpoint",{"path":str(p.active)},seconds=30)
            fp=self._move(p.active,pending,p.custody_uid,0o444)
            self.fault("transition_preserved")
            self._move(target,p.active,p.writer_uid,0o600)
            self.fault("transition_new_active")
            after["segments"]=[*before["segments"],self._record(pending,"pending")]
            self._json(self.intent,{**intent,"after":after},0o400)
            self._catalog(after)
            self.fault("transition_published")
            self._finish_intent()
            return after

    def _finish_intent(self):
        value=read_control(self.intent,self.p.custody_uid,0o400)
        self._json(self.private/("receipt-"+uuid4().hex+".json"),
                   {"status":"verified",**value},0o400)
        if value["operation"]=="transition" and value["before"]["mode"]=="legacy":
            self._json(self.private/"initial-cutover-complete.json",
                       {"status":"completed","epoch":value["after"]["epoch"]},0o400)
        self.intent.unlink();sync(self.private)

    def recover(self):
        p=self.p
        with self.serialized(),self.handoff():
            if not self.intent.exists():
                claim=self.private/"initial-cutover-claimed.json"
                complete=self.private/"initial-cutover-complete.json"
                if not claim.exists() or complete.exists():return {"status":"no_pending_transition"}
                saved=read_control(claim,p.custody_uid,0o400)
                need(saved["adoption_sha256"]==journal_sql.file_hash(self.private/"adoption.json"),
                     "JOURNAL_INITIAL_ADOPTION_CHANGED")
                tx=saved["transaction"];catalog=p.catalog()
                need(catalog==tx["before"],"JOURNAL_INITIAL_CLAIM_STATE_CHANGED")
                meta=p.active.stat()
                need({"device":meta.st_dev,"inode":meta.st_ino}==tx["source_identity"],
                     "JOURNAL_INITIAL_CLAIM_SOURCE_CHANGED")
                self._json(self.intent,tx,0o400)
                self._catalog({**catalog,"mode":"transition"})
            tx=read_control(self.intent,p.custody_uid,0o400)
            if tx["operation"]=="transition":
                pending=p.pending/tx["pending"];target=Path(tx["target"])
                if not pending.exists():
                    p.active_identity();require_no_handles(p.active)
                    self._sql("checkpoint",{"path":str(p.active)},seconds=30)
                    self._move(p.active,pending,p.custody_uid,0o444)
                meta=pending.lstat()
                need(not pending.is_symlink() and stat.S_ISREG(meta.st_mode) and meta.st_nlink==1
                     and meta.st_uid==p.custody_uid and stat.S_IMODE(meta.st_mode)==0o444
                     and {"device":meta.st_dev,"inode":meta.st_ino}==tx["source_identity"],
                     "JOURNAL_RECOVERY_SOURCE_IDENTITY")
                if target.exists():
                    need(not p.active.exists(),"JOURNAL_RECOVERY_ACTIVE_COLLISION")
                    self._move(target,p.active,p.writer_uid,0o600)
                p.active_identity();meta=p.active.stat()
                need({"device":meta.st_dev,"inode":meta.st_ino}==tx["target_identity"],
                     "JOURNAL_RECOVERY_TARGET_IDENTITY")
                actual=self._sql("state",{"path":str(p.active)},seconds=30)
                need(actual["epoch"]==tx["after"]["epoch"],"JOURNAL_RECOVERY_EPOCH")
                after={**tx["after"],"segments":[*tx["before"]["segments"],self._record(pending,"pending")]}
                self._catalog(after);self._finish_intent()
                return {"status":"transition_recovered"}
            if tx["operation"]=="rollback":
                return self._recover_rollback(tx)
            raise RuntimeError("JOURNAL_UNKNOWN_INTENT")

    def _copy_identical(self,source,target,expected):
        need(not os.path.lexists(target),"JOURNAL_COPY_TARGET_PRESENT")
        fd=os.open(source,os.O_RDONLY|os.O_NOFOLLOW)
        out=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,"rb") as src,os.fdopen(out,"wb") as dst:
            os.fchown(dst.fileno(),self.p.writer_uid,self.p.writer_uid)
            os.fchmod(dst.fileno(),0o600)
            meta=os.fstat(src.fileno())
            need(stat.S_ISREG(meta.st_mode) and meta.st_nlink==1,"JOURNAL_COPY_SOURCE_IDENTITY")
            shutil.copyfileobj(src,dst,1024*1024);dst.flush();os.fsync(dst.fileno())
        need(journal_sql.file_hash(target)==expected,"JOURNAL_COPY_BYTES_MISMATCH")

    def seal_one(self,*,seconds=10800):
        p=self.p
        with self.serialized():
            with p.gate():
                catalog=p.catalog()
                pending=next((s for s in catalog["segments"] if s["state"]=="pending"),None)
                if pending is None:return {"status":"nothing_to_seal"}
                source=p.artifact(pending)
            # Expensive work is OUTSIDE the shared handoff gate.
            original=self._sql("proof",{"path":str(source),"seconds":seconds},seconds=seconds)
            p.artifact(pending)
            need(shutil.disk_usage(p.archives).free>source.stat().st_size*2+4563402752,
                 "JOURNAL_ARCHIVE_SPACE_RESERVE_REQUIRED")
            job=self._job();copy=job/(pending["id"]+".sqlite3")
            try:
                self._copy_identical(source,copy,original["file_sha256"])
                filters=self._sql("filters",{"source":str(copy),"directory":str(job),
                    "identifier":pending["id"],"events":original["events"]},seconds=seconds)
                # A byte-identical cold restore opens independently and checks schema/
                # indexed readability. Full integrity is reused only for these EXACT
                # bytes, linked to the real full source proof.
                restore=job/"restored.sqlite3"
                self._copy_identical(copy,restore,original["file_sha256"])
                restored_state=self._sql("state",{"path":str(restore)},seconds=30)
                validation=self._sql("validate_filters",{"source":str(copy),"directory":str(job),
                    "records":filters},seconds=seconds)
                target=p.archives/copy.name
                # Adopt before publication, then independently rehash under Root
                # custody. Long hashing is outside the exclusive handoff gate.
                if os.path.lexists(target):
                    meta=target.lstat()
                    need(not target.is_symlink() and stat.S_ISREG(meta.st_mode)
                         and meta.st_uid==p.custody_uid and meta.st_gid==p.custody_uid
                         and meta.st_nlink==1 and stat.S_IMODE(meta.st_mode)==0o444,
                         "JOURNAL_EXISTING_ARCHIVE_CUSTODY")
                else:self._move(copy,target,p.custody_uid,0o444)
                require_no_handles(target)
                need(journal_sql.file_hash(target)==original["file_sha256"],"JOURNAL_ARCHIVE_CONFLICT")
                published={}
                for key,item in filters.items():
                    raw=job/item["file"];final=p.archives/item["file"]
                    if not os.path.lexists(final):self._move(raw,final,p.custody_uid,0o444)
                    meta=final.lstat()
                    need(not final.is_symlink() and stat.S_ISREG(meta.st_mode) and meta.st_nlink==1
                         and meta.st_uid==p.custody_uid and meta.st_gid==p.custody_uid
                         and stat.S_IMODE(meta.st_mode)==0o444
                         and journal_sql.file_hash(final)==item["sha256"],"JOURNAL_FILTER_CONFLICT")
                    require_no_handles(final)
                    published[key]={**item,"fingerprint":fingerprint(meta)}
                with p.gate(exclusive=True):
                    current=p.catalog()
                    need(pending in current["segments"],"JOURNAL_SEAL_GENERATION_CHANGED")
                    p.artifact(pending)
                    sealed={**pending,"state":"sealed","file":target.name,"fingerprint":fingerprint(target.stat()),
                        "filters":published,"proof":{**original,"full_verified_at":datetime.now(timezone.utc).isoformat(),
                        "restore_verified":True,"restore_basis":"identical_bytes_to_full_verified_source",
                        "filters_validated":validation,"source_before_image":pending["file"],
                        "source_before_fingerprint":pending["fingerprint"]}}
                    after={**current,"generation":current["generation"]+1,"segments":[
                        sealed if r["id"]==pending["id"] else r for r in current["segments"]]}
                    if all(r["state"]=="sealed" for r in after["segments"]):after["mode"]="segmented"
                    self._catalog(after)
                    self._json(self.private/("seal-"+pending["id"]+".json"),
                        {"status":"verified","segment":sealed,"restored_state":restored_state,
                         "off_host_backup_claimed":False},0o400)
                return {"status":"sealed","segment_id":pending["id"],"events":original["events"]}
            finally:
                self._cleanup_job(job)

    def reclaim(self,identifier):
        p=self.p
        with self.serialized():
            with p.gate():
                catalog=p.catalog()
                segment=next(r for r in catalog["segments"] if r["id"]==identifier)
                need(segment["state"]=="sealed" and segment["proof"].get("restore_verified") is True,
                     "JOURNAL_RECLAIM_PROOF_REQUIRED")
                artifact=p.artifact(segment)
                plan=read_control(self.rollback,p.custody_uid,0o400)
                need(plan["covered_segments"].get(identifier)==segment["fingerprint"]
                     and plan["proof"]["integrity"]=="ok","JOURNAL_RECLAIM_ROLLBACK_PROOF_REQUIRED")
            need(journal_sql.file_hash(artifact)==segment["proof"]["file_sha256"],"JOURNAL_RECLAIM_HASH")
            need(self.fixture or artifact.stat().st_dev!=p.active.parent.stat().st_dev,
                 "JOURNAL_ARCHIVE_MUST_BE_SEPARATE_FILESYSTEM")
            with p.gate(exclusive=True):
                need(p.catalog()["generation"]==catalog["generation"],"JOURNAL_RECLAIM_GENERATION_CHANGED")
                p.artifact(segment)
                before=p.pending/segment["proof"]["source_before_image"]
                if before.exists():
                    need(fingerprint(before.stat())==segment["proof"]["source_before_fingerprint"],
                         "JOURNAL_BEFORE_IMAGE_CHANGED")
                    require_no_handles(before)
                    need(before!=p.active,"JOURNAL_RECLAIM_ACTIVE_DENIED")
                    before.unlink();sync(before.parent)
                self._json(self.private/("reclaim-"+identifier+".json"),
                    {"status":"redundant_source_copy_reclaimed_or_reused_for_verified_rollback",
                     "segment_id":identifier,"all_events_retained":True,"off_host_backup_claimed":False},0o400)

    def prepare_rollback(self):
        p=self.p
        with self.serialized():
            with p.gate():
                catalog=p.catalog()
                need(catalog["mode"] in ("segmented","segmented_initializing"),"JOURNAL_ROLLBACK_MODE")
                paths=[str(p.artifact(record)) for record in catalog["segments"]]
                job=self._job();snapshot=job/"active.snapshot.sqlite3"
                state=self._sql("snapshot",{"source":str(p.active),"target":str(snapshot)},seconds=60)
            # A sealed, redundant local legacy before-image is an exact rollback
            # seed. Reuse it only after independent archive routing/restore proof.
            # This avoids allocating a second 44GB file on the small system disk.
            local=self._job(local=True);target=local/"legacy.prepared.sqlite3"
            seed=None
            if catalog["segments"]:
                first=catalog["segments"][0]
                if first["state"]=="sealed" and first["proof"].get("restore_verified") is True:
                    candidate=p.pending/first["proof"]["source_before_image"]
                    if candidate.exists():
                        need(fingerprint(candidate.stat())==first["proof"]["source_before_fingerprint"],
                             "JOURNAL_ROLLBACK_SEED_CHANGED")
                        require_no_handles(candidate)
                        need(candidate.stat().st_dev==local.stat().st_dev,"JOURNAL_ROLLBACK_SEED_DEVICE")
                        seed=candidate
            required=snapshot.stat().st_size+sum(Path(path).stat().st_size for path in paths[(1 if seed else 0):])
            need(shutil.disk_usage(local).free>required*2+268435456,"JOURNAL_ROLLBACK_LOCAL_SPACE_REQUIRED")
            self._json(self.private/"rollback-preparation.json",
                {"seed":str(seed) if seed else None,"target":str(target),"catalog":catalog},0o400)
            if seed is not None:
                self._move(seed,target,p.writer_uid,0o600)
                proof=self._sql("append_sources",{"paths":[*paths[1:],str(snapshot)],"target":str(target)})
            else:
                proof=self._sql("rebuild",{"paths":[*paths,str(snapshot)],"target":str(target)})
            # Parent is Root owned, so UID1000 cannot replace the adopted target.
            adopted=self.local_work/(uuid4().hex+".rollback.sqlite3")
            self._move(target,adopted,p.custody_uid,0o444)
            require_no_handles(adopted)
            need(journal_sql.file_hash(adopted)==proof["file_sha256"],"JOURNAL_ROLLBACK_PROOF_CHANGED")
            plan={"generation":catalog["generation"],"epoch":catalog["epoch"],
                "watermark":state["watermark"],"target":str(adopted),"proof":proof,
                "target_fingerprint":fingerprint(adopted.stat()),
                "covered_segments":{r["id"]:r["fingerprint"] for r in catalog["segments"]},
                "catalog":catalog,"prepared_at":datetime.now(timezone.utc).isoformat()}
            self._json(self.rollback,plan,0o400)
            return {"status":"rollback_prepared","events":proof["events"]}

    def finish_rollback(self):
        p=self.p
        with self.serialized(),self.handoff():
            before=p.catalog();plan=read_control(self.rollback,p.custody_uid,0o400)
            need(before["generation"]==plan["generation"] and before["epoch"]==plan["epoch"],
                 "JOURNAL_ROLLBACK_REBUILD_REQUIRED")
            require_no_handles(p.active)
            target=Path(plan["target"]);meta=target.lstat()
            need(not target.is_symlink() and meta.st_uid==p.custody_uid
                 and stat.S_IMODE(meta.st_mode)==0o444
                 and fingerprint(meta)==plan["target_fingerprint"],"JOURNAL_ROLLBACK_TARGET_CHANGED")
            self._sql("tail_budget",{"source":str(p.active),"watermark":plan["watermark"]},seconds=10)
            write_job=self._job(local=True)
            tx={"operation":"rollback","before":before,
                "plan":{**plan,"target":str(write_job/"legacy.prepared.sqlite3")},
                "sealed_target":str(target),
                "target_identity":{"device":meta.st_dev,"inode":meta.st_ino},
                "preserved":uuid4().hex+".sqlite3","source_epoch":before["epoch"]}
            self._json(self.intent,tx,0o400);self._catalog({**before,"mode":"transition"})
            self.fault("rollback_intent")
            return self._recover_rollback(tx)

    def _recover_rollback(self,tx):
        p=self.p;plan=tx["plan"];preserve=p.pending/tx["preserved"]
        if not preserve.exists():
            target=Path(plan["target"]);sealed=Path(tx["sealed_target"])
            need(sealed.parent==self.local_work and target.parent.parent==self.local_work
                 and not target.is_symlink(),"JOURNAL_ROLLBACK_TARGET_SCOPE")
            if sealed.exists():
                need(not target.exists(),"JOURNAL_ROLLBACK_TARGET_COLLISION")
                self._move(sealed,target,p.writer_uid,0o600)
            meta=target.lstat()
            need(not target.is_symlink() and meta.st_nlink==1 and meta.st_uid==p.writer_uid
                 and {"device":meta.st_dev,"inode":meta.st_ino}==tx["target_identity"],
                 "JOURNAL_ROLLBACK_TARGET_IDENTITY")
            result=self._sql("merge_tail",{"source":str(p.active),"target":plan["target"],
                "watermark":plan["watermark"],"maximum_rows":100000,"maximum_bytes":134217728,"seconds":20},
                seconds=30)
            self._sql("checkpoint",{"path":str(p.active)},seconds=30)
            self._move(p.active,preserve,p.custody_uid,0o444)
            self.fault("rollback_preserved")
        target=Path(plan["target"])
        if target.exists():
            self._sql("checkpoint",{"path":str(target)},seconds=30)
            # Large rollback files are built on archive storage, then staged to
            # a same-device destination before the final pause by the release
            # wrapper. Never perform a cross-device pseudo-atomic rename.
            need(target.parent.stat().st_dev==p.active.parent.stat().st_dev,
                 "JOURNAL_ROLLBACK_LOCAL_STAGE_REQUIRED")
            self._move(target,p.active,p.writer_uid,0o600)
            self.fault("rollback_swapped")
        p.active_identity();meta=p.active.stat()
        need({"device":meta.st_dev,"inode":meta.st_ino}==tx["target_identity"],
             "JOURNAL_ROLLBACK_PUBLISHED_IDENTITY")
        after={**tx["before"],"mode":"legacy","generation":tx["before"]["generation"]+1,"segments":[]}
        self._catalog(after)
        self.fault("rollback_published")
        self._finish_intent()
        return {"status":"rollback_published_pending_native_verification"}

    def scrub_one(self,*,now=None,seconds=10800):
        now=now or datetime.now(timezone.utc);p=self.p
        with self.serialized():
            with p.gate():
                catalog=p.catalog()
                records=[r for r in catalog["segments"] if r["state"]=="sealed"]
                if not records:return {"status":"no_history"}
                record=min(records,key=lambda r:r["proof"].get("last_scrub_at",r["proof"]["full_verified_at"]))
                due=datetime.fromisoformat(record["proof"].get("last_scrub_at",record["proof"]["full_verified_at"]))
                if now-due<timedelta(days=28):return {"status":"scrub_not_due"}
                path=p.artifact(record)
            proof=self._sql("proof",{"path":str(path),"seconds":seconds},seconds=seconds)
            need(all(proof[k]==record["proof"][k] for k in
                     ("integrity","events","content_sha256","file_sha256")),"JOURNAL_HISTORICAL_SCRUB_MISMATCH")
            with p.gate(exclusive=True):
                current=p.catalog();need(record in current["segments"],"JOURNAL_SCRUB_GENERATION_CHANGED")
                p.artifact(record)
                refreshed={**record,"proof":{**record["proof"],"last_scrub_at":now.isoformat()}}
                self._catalog({**current,"generation":current["generation"]+1,
                    "segments":[refreshed if r["id"]==record["id"] else r for r in current["segments"]]})
                self._json(self.private/("scrub-"+uuid4().hex+".json"),
                    {"status":"full_historical_integrity_verified","segment_id":record["id"],
                     "proof":proof,"observed_at":now.isoformat()},0o400)
            return {"status":"scrubbed","segment_id":record["id"]}

    def maintain(self,*,now=None):
        from zoneinfo import ZoneInfo
        now=now or datetime.now(timezone.utc)
        if self.intent.exists():return self.recover()
        with self.p.gate():
            catalog=self.p.catalog()
            need(catalog["mode"]!="legacy","JOURNAL_INITIAL_CUTOVER_REQUIRES_EXACT_RELEASE")
            pending=any(r["state"]=="pending" for r in catalog["segments"])
            opened=datetime.fromisoformat(catalog["opened_at"])
            local=now.astimezone(ZoneInfo("America/New_York"))
            boundary=local.replace(hour=0,minute=15,second=0,microsecond=0)
            if local<boundary:boundary-=timedelta(days=1)
            due=opened<boundary or self.p.active_bytes()>=self.p.target_bytes
        if pending:return self.seal_one()
        if due:return self.transition()
        return self.scrub_one(now=now)

    def status(self):
        with self.p.gate():
            value=self.p.catalog()
            return {"mode":value["mode"],"generation":value["generation"],
                "active_bytes":self.p.active_bytes(),"pending":sum(s["state"]=="pending" for s in value["segments"]),
                "sealed":sum(s["state"]=="sealed" for s in value["segments"]),
                "off_host_backup_claimed":False}


def root_controller():
    need(os.geteuid()==0 and sys.flags.isolated==1 and Path(__file__).resolve()==ENTRY,
         "JOURNAL_INSTALLED_ISOLATED_ROOT_REQUIRED")
    policy=read_control(POLICY,0,0o600)
    receipt=read_control(PRIVATE/"adoption.json",0,0o400)
    need(receipt.get("action")==ACTION and receipt.get("owner_oid")==OWNER
         and receipt.get("independently_verified_entra_owner") is True
         and receipt.get("policy_sha256")==sha256(canonical(policy)).hexdigest()
         and receipt.get("maintenance_policy_adopted") is True,"JOURNAL_ROOT_ADOPTION_REQUIRED")
    need(policy.get("schema_version")=="1.0" and policy.get("enabled") is True
         and policy.get("maintenance_operations")==["rotate","seal","scrub","recover"],
         "JOURNAL_ROOT_MAINTENANCE_POLICY")
    expected_names={"tools/audit_journal_control.py",
        "implementation/orchestrator/event_store.py","implementation/orchestrator/segmented_journal.py",
        "implementation/orchestrator/journal_sql.py","implementation/orchestrator/journal_health.py"}
    need(set(policy["trusted_source_sha256"])==expected_names,"JOURNAL_TRUSTED_SOURCE_CLOSURE")
    for name,expected in policy["trusted_source_sha256"].items():
        path=ENTRY.parent.parent/name;meta=path.lstat()
        need(not path.is_symlink() and stat.S_ISREG(meta.st_mode) and meta.st_uid==0 and meta.st_gid==0
             and stat.S_IMODE(meta.st_mode)==0o444 and meta.st_nlink==1
             and journal_sql.file_hash(path)==expected,"JOURNAL_TRUSTED_SOURCE_CHANGED")
    p=JournalProfile.load()
    need(sha256((p.control/"profile.json").read_bytes()).hexdigest()==policy["profile_sha256"]
         and p.active==Path("/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3")
         and p.archives==Path("/srv/jason/archive/governed-audit/orchestration")
         and p.pending==Path("/var/lib/jason-audit-journal/pending")
         and policy["work"]=="/srv/jason/archive/governed-audit/work"
         and policy["local_work"]=="/var/lib/jason/governed-ticket-shared/journal-work",
         "JOURNAL_FIXED_STORAGE_SCOPE")
    return JournalController(p,PRIVATE,policy["work"],policy["local_work"])


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--operation",choices=("status","cutover","rotate","recover","seal","reclaim",
                                               "prepare-rollback","finish-rollback","maintain","scrub"))
    parser.add_argument("--segment-id")
    parser.add_argument("--sql-operation")
    parser.add_argument("--sql-arguments")
    args=parser.parse_args()
    if args.sql_operation:
        need(os.geteuid()==1000 and sys.flags.isolated==1 and Path(__file__).resolve()==ENTRY,
             "JOURNAL_FIXED_WRITER_HELPER_REQUIRED")
        print(json.dumps(journal_sql.dispatch(args.sql_operation,json.loads(args.sql_arguments))))
        return
    controller=root_controller()
    if args.operation=="status":result=controller.status()
    elif args.operation=="cutover":result=controller.transition(initial=True)
    elif args.operation=="rotate":result=controller.transition()
    elif args.operation=="recover":result=controller.recover()
    elif args.operation=="seal":result=controller.seal_one()
    elif args.operation=="reclaim":
        need(args.segment_id is not None and len(args.segment_id)==32
             and all(c in "0123456789abcdef" for c in args.segment_id),"JOURNAL_SEGMENT_ID")
        controller.reclaim(args.segment_id);result={"status":"source_copy_reclaimed"}
    elif args.operation=="maintain":result=controller.maintain()
    elif args.operation=="scrub":result=controller.scrub_one()
    elif args.operation=="prepare-rollback":result=controller.prepare_rollback()
    elif args.operation=="finish-rollback":result=controller.finish_rollback()
    else:raise PermissionError("JOURNAL_OPERATION_REQUIRED")
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    try:main()
    except Exception as exc:raise SystemExit("DENIED:"+type(exc).__name__+":"+str(exc).split(":")[0][:160])
