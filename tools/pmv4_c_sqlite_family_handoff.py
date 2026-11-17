"""PMv4 Stage C: inode-preserving SQLite-family handoff, source-only library.

Not a CLI, root issuer, or release authorization. The caller MUST independently
verify a new Owner-signed exact cutover, production hold/freeze, writer
quiescence, matching service configuration, and a tested rollback before use.
Never run move() against live databases from an ordinary engineering session.
"""
from __future__ import annotations

from dataclasses import dataclass
import ctypes
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
from typing import Callable, Iterable

ALLOWED_SHARED = (
    "teams-identity-bindings.sqlite3", "orchestration-events.sqlite3",
    "governed-execution.sqlite3", "reflection.sqlite3",
    "resolution-memory.sqlite3",
)
ALLOWED_TICKET = (
    "autonomy-operational-work.sqlite3", "playbook-autonomy.sqlite3",
    "autonomy-targeted-wakes.sqlite3", "ticket-split.sqlite3",
)
SUFFIXES = ("", "-wal", "-shm", ".owner.lock")
MIN_UID = 1000


class HandoffDenied(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FileIdentity:
    name: str
    device: int
    inode: int
    size: int
    mode: int


@dataclass(frozen=True, slots=True)
class FamilyPlan:
    source: Path
    destination: Path
    kind: str
    uid: int
    entries: tuple[FileIdentity, ...]
    digest: str

    @property
    def bytes_not_copied(self) -> int:
        return sum(x.size for x in self.entries)


def _need(condition: bool, reason: str) -> None:
    if not condition:
        raise HandoffDenied(reason)


def _trusted_dir(path: Path, uid: int) -> os.stat_result:
    _need(path.is_absolute() and ".." not in path.parts,
          "C_SQLITE_NONABSOLUTE_ROOT")
    _need(path.resolve(strict=True) == path,
          "C_SQLITE_SYMLINKED_ROOT")
    st = path.lstat()
    _need(stat.S_ISDIR(st.st_mode) and st.st_uid == uid
          and stat.S_IMODE(st.st_mode) == 0o700,
          "C_SQLITE_UNTRUSTED_ROOT")
    return st


def _stat(path: Path, uid: int, *, required: bool) -> os.stat_result | None:
    try:
        st=path.lstat()
    except FileNotFoundError:
        if required:
            raise HandoffDenied("C_SQLITE_DB_MISSING:"+path.name)
        return None
    _need(not path.is_symlink() and stat.S_ISREG(st.st_mode)
          and st.st_uid==uid and st.st_nlink==1
          and stat.S_IMODE(st.st_mode)==0o600,
          "C_SQLITE_UNTRUSTED_FILE:"+path.name)
    return st


def _files_for_group(source: Path, names: tuple[str,...], uid: int
                     ) -> tuple[FileIdentity,...]:
    entries=[]
    for name in names:
        for suffix in SUFFIXES:
            file=source/(name+suffix)
            info=_stat(file,uid,required=(suffix==""))
            if info is None:
                continue
            entries.append(FileIdentity(
                name=file.name,device=info.st_dev,inode=info.st_ino,
                size=info.st_size,mode=stat.S_IMODE(info.st_mode)))
    return tuple(entries)


def _canon(value: object) -> bytes:
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False).encode("utf-8")


def _fingerprint(source:Path,dest:Path,kind:str,uid:int,
                 items:tuple[FileIdentity,...])->str:
    return hashlib.sha256(_canon({
        "source":str(source),"destination":str(dest),"kind":kind,"uid":uid,
        "files":[{
            "name":x.name,"device":x.device,"inode":x.inode,
            "size":x.size,"mode":x.mode
        } for x in items]
    })).hexdigest()


def inspect_quiescence(paths:Iterable[Path],
                       *, lsof:str="/usr/bin/lsof") -> None:
    """Nonzero lsof error fails closed; root host gate must also stop admission."""
    names=[str(x) for x in paths]
    _need(bool(names),"C_SQLITE_EMPTY_QUIESCENCE_SET")
    _need(Path(lsof).is_absolute(),"C_SQLITE_LSOF_NOT_PINNED")
    try:
        proc=subprocess.run(
            [lsof,"-w","-t","--",*names],capture_output=True,
            text=True,timeout=12,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise HandoffDenied("C_SQLITE_LSOF_UNAVAILABLE") from exc
    _need(proc.returncode in (0,1) and not proc.stderr.strip(),
          "C_SQLITE_LSOF_UNRELIABLE")
    _need(proc.returncode==1 and not proc.stdout.strip(),
          "C_SQLITE_ACTIVE_SQLITE_OWNER")


def preview(source:Path,destination:Path,*,kind:str,uid:int=MIN_UID,
            require_quiescence:bool=True) -> FamilyPlan:
    """Read-only plan. Never creates directories, opens SQLite or changes files."""
    src=Path(source);dst=Path(destination)
    names={"shared":ALLOWED_SHARED,"ticket":ALLOWED_TICKET}.get(kind)
    _need(names is not None,"C_SQLITE_UNKNOWN_GROUP")
    _need(src!=dst,"C_SQLITE_SAME_ROOT")
    src_stat=_trusted_dir(src,uid); dst_stat=_trusted_dir(dst,uid)
    _need(src_stat.st_dev==dst_stat.st_dev,
          "C_SQLITE_DIFFERENT_FILESYSTEM")
    entries=_files_for_group(src,names,uid)
    _need(all(x.device==src_stat.st_dev for x in entries),
          "C_SQLITE_DIFFERENT_SOURCE_DEVICE")
    for x in entries:
        target=dst/x.name
        _need(not target.exists() and not target.is_symlink(),
              "C_SQLITE_TARGET_NOT_EMPTY:"+x.name)
    if require_quiescence:
        inspect_quiescence(src/x.name for x in entries)
    return FamilyPlan(src,dst,kind,uid,entries,
                      _fingerprint(src,dst,kind,uid,entries))


def _rename_noreplace(source:Path,destination:Path)->None:
    """Linux atomic RENAME_NOREPLACE; no unsafe os.rename fallback."""
    library=ctypes.CDLL(None,use_errno=True)
    native=getattr(library,"renameat2",None)
    _need(native is not None,"C_SQLITE_RENAME_NOREPLACE_UNAVAILABLE")
    native.argtypes=(
        ctypes.c_int,ctypes.c_char_p,ctypes.c_int,
        ctypes.c_char_p,ctypes.c_uint,
    )
    native.restype=ctypes.c_int
    rc=native(-100,os.fsencode(source),-100,os.fsencode(destination),1)
    if rc!=0:
        error=ctypes.get_errno()
        raise OSError(error,os.strerror(error),
                      f"{source} -> {destination}")


def _fsync_dir(directory:Path)->None:
    fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


def _assert_original(plan:FamilyPlan)->None:
    for x in plan.entries:
        actual=_stat(plan.source/x.name,plan.uid,required=True)
        _need(actual is not None
              and (actual.st_dev,actual.st_ino,actual.st_size)==
                  (x.device,x.inode,x.size),
              "C_SQLITE_SOURCE_CHANGED:"+x.name)
        _need(not (plan.destination/x.name).exists(),
              "C_SQLITE_DESTINATION_CHANGED:"+x.name)


def _write_event(fd:int,index:int,previous:str,event:str,details:dict):
    obj={"index":index,"previous_sha256":previous,
         "event":event,"details":details}
    digest=hashlib.sha256(_canon(obj)).hexdigest()
    obj["hash"]=digest
    payload=_canon(obj)+b"\n"
    while payload:
        written=os.write(fd,payload)
        _need(written>0,"C_SQLITE_JOURNAL_SHORT_WRITE")
        payload=payload[written:]
    os.fsync(fd)
    return digest


def _journal_root(plan:FamilyPlan,journal:Path,owner_uid:int) -> None:
    _need(journal.is_absolute() and ".." not in journal.parts
          and journal.name=="pmv4-c-"+plan.digest+".jsonl"
          and journal.parent not in (plan.source,plan.destination),
          "C_SQLITE_JOURNAL_NOT_EXACT_ROOT")
    state=_trusted_dir(journal.parent,owner_uid)
    _need(state.st_dev==plan.source.stat().st_dev,
          "C_SQLITE_JOURNAL_DIFFERENT_FILESYSTEM")


def move_under_signed_root(
    plan:FamilyPlan, *, journal:Path,
    signed_host_fence:Callable[[],None],
    verify_all_producers_stopped:Callable[[],None],
    journal_owner_uid:int=0,
) -> dict:
    """Transactional same-FS rename with durable intent ledger.

    The callbacks MUST be supplied by the independent *root-authenticated*
    host-release procedure, not by this source library. No implicit approval.
    On interrupted rename, never infer rollback from an exception alone:
    reconcile the journal and actual file inodes under the same signed fence.
    """
    journal=Path(journal)
    _need(os.geteuid()==journal_owner_uid,
          "C_SQLITE_ROOT_AUDIT_AUTHORITY_REQUIRED")
    _journal_root(plan,journal,journal_owner_uid)
    _need(not journal.exists() and not journal.is_symlink(),
          "C_SQLITE_JOURNAL_ALREADY_PRESENT")
    signed_host_fence()
    verify_all_producers_stopped()
    refreshed=preview(plan.source,plan.destination,
                      kind=plan.kind,uid=plan.uid)
    _need(refreshed.digest==plan.digest,"C_SQLITE_PLAN_CHANGED")
    _assert_original(plan)
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC
    fd=os.open(journal,flags,0o600)
    _fsync_dir(journal.parent)
    count=0;previous="0"*64
    try:
        os.fchmod(fd,0o600)
        previous=_write_event(fd,count,previous,"begin",{
            "plan_sha256":plan.digest,"kind":plan.kind,
            "from":str(plan.source),"to":str(plan.destination),
            "files":[x.name for x in plan.entries]})
        count+=1
        for x in plan.entries:
            signed_host_fence()
            verify_all_producers_stopped()
            source=plan.source/x.name; target=plan.destination/x.name
            active=_stat(source,plan.uid,required=True)
            _need(active is not None and active.st_ino==x.inode
                  and active.st_dev==x.device
                  and active.st_size==x.size
                  and not target.exists(),
                  "C_SQLITE_INODE_CHANGED_BEFORE_MOVE:"+x.name)
            previous=_write_event(fd,count,previous,"intent",{
                "name":x.name,"inode":x.inode});count+=1
            _rename_noreplace(source,target)
            _fsync_dir(plan.source);_fsync_dir(plan.destination)
            landed=_stat(target,plan.uid,required=True)
            _need(landed is not None and landed.st_ino==x.inode
                  and landed.st_dev==x.device,
                  "C_SQLITE_INODE_CHANGED_AFTER_MOVE:"+x.name)
            previous=_write_event(fd,count,previous,"moved",{
                "name":x.name,"inode":x.inode});count+=1
        signed_host_fence()
        verify_all_producers_stopped()
        for x in plan.entries:
            landed=_stat(plan.destination/x.name,plan.uid,required=True)
            _need(landed is not None
                  and (landed.st_dev,landed.st_ino,landed.st_size)==
                      (x.device,x.inode,x.size)
                  and not (plan.source/x.name).exists(),
                  "C_SQLITE_FINAL_READBACK_CHANGED:"+x.name)
        previous=_write_event(fd,count,previous,"all_files_moved",{
            "count":len(plan.entries),"plan_sha256":plan.digest})
        return {"status":"files_moved_not_activated",
                "plan_sha256":plan.digest,"file_count":len(plan.entries),
                "bytes_not_copied":plan.bytes_not_copied,
                "journal":str(journal),"owner_approval_issued":False,
                "external_worker_activated":False}
    finally:
        os.close(fd)


def read_exact_journal(plan:FamilyPlan, journal:Path,
                       *, journal_uid:int|None=None) -> tuple[dict,...]:
    """Validate every root journal event before any resumption or rollback."""
    journal=Path(journal)
    _journal_root(plan,journal,os.geteuid() if journal_uid is None else journal_uid)
    _stat(journal,os.geteuid() if journal_uid is None else journal_uid,
          required=True)
    _need(journal.stat().st_size < 2_000_000,
          "C_SQLITE_UNBOUNDED_JOURNAL")
    rows=[];prior="0"*64
    try:
        raw_rows=journal.read_bytes().splitlines()
    except OSError as exc:
        raise HandoffDenied("C_SQLITE_JOURNAL_UNREADABLE") from exc
    for index,raw in enumerate(raw_rows):
        _need(0<len(raw)<10000,"C_SQLITE_JOURNAL_INVALID_ROW")
        try: item=json.loads(raw)
        except (json.JSONDecodeError,UnicodeDecodeError) as exc:
            raise HandoffDenied("C_SQLITE_JOURNAL_INVALID_JSON") from exc
        _need(isinstance(item,dict),"C_SQLITE_JOURNAL_NOT_OBJECT")
        signature=item.get("hash")
        serialized={key:value for key,value in item.items() if key!="hash"}
        _need(item.get("index")==index
              and item.get("previous_sha256")==prior
              and isinstance(signature,str)
              and hashlib.sha256(_canon(serialized)).hexdigest()==signature,
              "C_SQLITE_JOURNAL_CHAIN_INVALID")
        event=item.get("event")
        _need(event in {"begin","intent","moved","all_files_moved",
                        "rollback_intent","rolled_back","rollback_complete"},
              "C_SQLITE_JOURNAL_FOREIGN_EVENT")
        if index==0:
            details=item.get("details")
            _need(event=="begin" and isinstance(details,dict)
                  and details.get("plan_sha256")==plan.digest
                  and details.get("kind")==plan.kind
                  and details.get("from")==str(plan.source)
                  and details.get("to")==str(plan.destination)
                  and details.get("files")==[x.name for x in plan.entries],
                  "C_SQLITE_JOURNAL_PLAN_MISMATCH")
        elif event in {"intent","moved","rollback_intent","rolled_back"}:
            details=item.get("details")
            _need(isinstance(details,dict)
                  and any(x.name==details.get("name")
                          and x.inode==details.get("inode")
                          for x in plan.entries),
                  "C_SQLITE_JOURNAL_UNKNOWN_FILE")
        elif event in {"all_files_moved","rollback_complete"}:
            _need(item.get("details",{}).get("plan_sha256")==plan.digest,
                  "C_SQLITE_JOURNAL_PLAN_MISMATCH")
        rows.append(item)
        prior=signature
    _need(len(rows)>0,"C_SQLITE_EMPTY_JOURNAL")
    return tuple(rows)


def rollback_before_new_writer(
    plan:FamilyPlan, *, journal:Path,
    signed_host_fence:Callable[[],None],
    verify_no_new_writer_or_provider_action:Callable[[],None],
    journal_owner_uid:int=0,
) -> dict:
    """Only original inodes, under the same signed root fence, before activation.

    NEVER restore stale pre-cutover files after any new worker has committed
    work. The required root callback independently verifies no new writer,
    claim, notification or provider action was admitted after the move.
    """
    journal=Path(journal)
    _need(os.geteuid()==journal_owner_uid,
          "C_SQLITE_ROOT_AUDIT_AUTHORITY_REQUIRED")
    _journal_root(plan,journal,journal_owner_uid)
    signed_host_fence(); verify_no_new_writer_or_provider_action()
    _trusted_dir(plan.source,plan.uid)
    _trusted_dir(plan.destination,plan.uid)
    rows=read_exact_journal(plan,journal)
    _need(rows[-1]["event"]!="rollback_complete",
          "C_SQLITE_ROLLBACK_ALREADY_CLOSED")
    present=[]
    for x in plan.entries:
        source=plan.source/x.name;dest=plan.destination/x.name
        old=_stat(source,plan.uid,required=False)
        new=_stat(dest,plan.uid,required=False)
        _need((old is None)!=(new is None),
              "C_SQLITE_INCONSISTENT_RECOVERY:"+x.name)
        active=old if old is not None else new
        _need(active is not None and
              (active.st_dev,active.st_ino,active.st_size)==
                (x.device,x.inode,x.size),
              "C_SQLITE_RECOVERY_INODE_CHANGED:"+x.name)
        present.append(source if old is not None else dest)
    inspect_quiescence(present)
    fd=os.open(journal,os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW|os.O_CLOEXEC)
    previous=rows[-1]["hash"]; count=len(rows)
    try:
        for x in reversed(plan.entries):
            signed_host_fence();verify_no_new_writer_or_provider_action()
            source=plan.source/x.name;dest=plan.destination/x.name
            if source.exists():
                _need(not dest.exists(),"C_SQLITE_RECOVERY_DUPLICATE")
                continue
            actual=_stat(dest,plan.uid,required=True)
            _need(actual is not None
                  and (actual.st_dev,actual.st_ino,actual.st_size)==
                      (x.device,x.inode,x.size),
                  "C_SQLITE_RECOVERY_INODE_CHANGED:"+x.name)
            previous=_write_event(fd,count,previous,"rollback_intent",{
                "name":x.name,"inode":x.inode});count+=1
            _rename_noreplace(dest,source)
            _fsync_dir(plan.source);_fsync_dir(plan.destination)
            check=_stat(source,plan.uid,required=True)
            _need(check is not None and check.st_ino==x.inode,
                  "C_SQLITE_ROLLBACK_INODE_MISMATCH")
            previous=_write_event(fd,count,previous,"rolled_back",{
                "name":x.name,"inode":x.inode});count+=1
        previous=_write_event(fd,count,previous,"rollback_complete",{
            "plan_sha256":plan.digest})
    finally:
        os.close(fd)
    return {
        "status":"original_inodes_restored_without_new_writer",
        "file_count":len(plan.entries),"plan_sha256":plan.digest,
        "owner_approval_issued":False,"external_worker_activated":False,
    }
