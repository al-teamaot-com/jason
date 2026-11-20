#!/usr/bin/env python3
"""Exact native Stage E code/policy before-image, switch and verified rollback.

Library only. The existing signed native release controller owns the Owner
signature, host/freeze locks, STARTED receipt and stage steps. This module
may be invoked ONLY by the root-owned Stage E callback after those gates.
No sudo, CLI, arbitrary paths, owner issuer, service control, provider calls,
container restarts, source-ref rewriting or new release engine.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from typing import Any,Callable,Mapping

from tools import pmv4_e_scheduler_parity as parity
from tools import pmv4_e_exact_release_packet as packet

ENTRY=Path("/opt/jason/pmv4-e-trusted/tools/pmv4_e_exact_code_transaction.py")
SNAPSHOT_ROOT=Path("/var/lib/jason/independent-component-release/stage-e-code-before")
SOURCE_ROOT=Path("/opt/jason/pmv4-e-trusted")
SHA40=re.compile(r"^[0-9a-f]{40}$")
HASH=re.compile(r"^[0-9a-f]{64}$")
WATCHDOG="tools/jason_self_heal_watchdog.py"
MANAGER="tools/release_manager_host_runner.py"
RECONCILER="tools/release_host_reconcile_worker.py"
POLICY="config/production-desired-state.json"
FILES=(WATCHDOG,MANAGER)
DEFAULT_TARGETS={
    WATCHDOG:Path("/home/al/.local/lib/jason/jason_self_heal_watchdog.py"),
    MANAGER:Path("/home/al/.local/lib/jason/release_manager_host_runner.py"),
    POLICY:Path("/etc/jason/release-readback-recovery/production-desired-state.json"),
}
DEFAULT_IDENTITIES={
    WATCHDOG:(1000,1000,0o700),
    MANAGER:(1000,1000,0o755),
    POLICY:(0,0,0o600),
}
EXPECTED_BEFORE={
    WATCHDOG:"6e1619012e1cbc30de0819b3f07320e75e933ed4c2643acdabdb94fca6d33fcf",
    MANAGER:"7208832ecb575d549721788f196f85c7d6bd609794680fe099f6ff60401626a9",
    POLICY:packet.EXPECTED_PRIOR_ROOT_POLICY,
}
OBJECTS=frozenset(DEFAULT_TARGETS)


class StageECodeTransactionDenied(PermissionError):
    pass


def need(ok:bool,reason:str)->None:
    if not ok:
        raise StageECodeTransactionDenied("PMV4_E_CODE_SWITCH_"+reason)


def digest(data:bytes)->str:
    return sha256(data).hexdigest()


def read_exact(path:Path, *, maximum:int=1_000_000)->bytes:
    try:
        meta=path.lstat()
        need(not path.is_symlink() and stat.S_ISREG(meta.st_mode)
             and meta.st_nlink==1 and 0<meta.st_size<=maximum
             and meta.st_mode&0o022==0,
             "FILE_MUTABLE_OR_UNTRUSTED")
        raw=path.read_bytes()
        need(len(raw)==meta.st_size,"FILE_CHANGED_DURING_READ")
        return raw
    except StageECodeTransactionDenied:
        raise
    except OSError as exc:
        raise StageECodeTransactionDenied(
            "PMV4_E_CODE_SWITCH_FILE_UNAVAILABLE") from exc


def safe_json(data:bytes)->dict[str,Any]:
    try:
        obj=json.loads(data)
        need(type(obj) is dict,"JSON_NOT_OBJECT")
        return obj
    except (ValueError,TypeError,UnicodeDecodeError) as exc:
        raise StageECodeTransactionDenied(
            "PMV4_E_CODE_SWITCH_JSON_INVALID") from exc


def atomic_exact(target:Path,body:bytes,*,mode:int,uid:int,gid:int)->None:
    """Replace one allowlisted verified file, preserving trusted identity."""
    before=target.lstat()
    need(not target.is_symlink() and stat.S_ISREG(before.st_mode)
         and before.st_nlink==1 and before.st_uid==uid
         and before.st_gid==gid
         and stat.S_IMODE(before.st_mode)==mode,
         "TARGET_FILE_IDENTITY_CHANGED")
    tmp=target.with_name("."+target.name+".pmv4-e-next")
    need(not tmp.exists() and not tmp.is_symlink(),
         "EXACT_TEMP_PATH_CONFLICT")
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|
               getattr(os,"O_NOFOLLOW",0),0o600)
    try:
        with os.fdopen(fd,"wb") as out:
            out.write(body)
            out.flush()
            os.fsync(out.fileno())
        os.chown(tmp,uid,gid)
        os.chmod(tmp,mode)
        need(tmp.read_bytes()==body,"TEMP_FILE_READBACK_CHANGED")
        os.replace(tmp,target)
        folder_fd=os.open(target.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(folder_fd)
        finally:os.close(folder_fd)
        need(read_exact(target)==body,"INSTALLED_CODE_READBACK_CHANGED")
    except BaseException:
        # Never remove a foreign file at the exact temp path.
        raise


class StageECodeTransaction:
    def __init__(self,*,source_root:Path=SOURCE_ROOT,
                 before_root:Path=SNAPSHOT_ROOT,
                 targets:Mapping[str,Path]|None=None,
                 identities:Mapping[str,tuple[int,int,int]]|None=None,
                 prior_sha256:Mapping[str,str]|None=None,
                 signed_started:Callable[[],bool],
                 shared_host_lock:Callable[[],bool],
                 freeze_lock:Callable[[],bool],
                 replacement_marker_absent:Callable[[],bool],
                 production:bool=True):
        if production:
            here=Path(__file__)
            info=here.lstat()
            need(os.geteuid()==0 and here==ENTRY
                 and here.resolve()==ENTRY and not here.is_symlink()
                 and stat.S_ISREG(info.st_mode)
                 and info.st_uid==info.st_gid==0
                 and stat.S_IMODE(info.st_mode)==0o444
                 and Path(source_root)==SOURCE_ROOT
                 and Path(before_root)==SNAPSHOT_ROOT
                 and targets is None and identities is None
                 and prior_sha256 is None,
                 "PRODUCTION_ROOT_SOURCE_NOT_IMMUTABLE")
        self.source_root=Path(source_root)
        self.before_root=Path(before_root)
        self.targets=dict(targets or DEFAULT_TARGETS)
        self.identities=dict(identities or DEFAULT_IDENTITIES)
        self.prior_sha256=dict(prior_sha256 or EXPECTED_BEFORE)
        need(set(self.targets)==set(self.identities)==
             set(self.prior_sha256)==OBJECTS,
             "FILE_SCOPE_NOT_EXACT")
        need(all(callable(fn) for fn in
                 (signed_started,shared_host_lock,freeze_lock,
                  replacement_marker_absent)),
             "RELEASE_CALLBACKS_MISSING")
        self.signed_started=signed_started
        self.shared_host_lock=shared_host_lock
        self.freeze_lock=freeze_lock
        self.replacement_marker_absent=replacement_marker_absent
        self.production=production

    def _guard(self)->None:
        need(self.signed_started() is True,
             "ORIGINAL_NATIVE_STARTED_RECEIPT_REQUIRED")
        need(self.shared_host_lock() is True and self.freeze_lock() is True,
             "NATIVE_SHARED_LOCKS_REQUIRED")
        need(self.replacement_marker_absent() is True,
             "LIVE_MARKER_ALREADY_ACCEPTED")

    def _snapshot_path(self,candidate:str)->Path:
        need(type(candidate) is str and SHA40.fullmatch(candidate) is not None,
             "CANDIDATE_SHA_INVALID")
        return self.before_root/candidate

    def _reviewed_candidate(self,scope:Mapping[str,Any])->dict[str,bytes]:
        self._guard()
        need(type(scope) is dict
             and scope.get("action")==packet.ACTION
             and scope.get("expected_prior_root_policy_sha256")==
                 packet.EXPECTED_PRIOR_ROOT_POLICY
             and scope.get("expected_freeze_sha256")==packet.EXPECTED_FREEZE,
             "EXACT_SIGNED_SCOPE_REQUIRED")
        hashes=scope.get("exact_replacement_files_sha256")
        need(type(hashes) is dict and
             set(hashes)==set(packet.REVIEWED_PATHS),
             "SOURCE_REVIEWED_HASH_SET_CHANGED")
        bodies={}
        for name in FILES:
            expected=hashes.get(name)
            need(type(expected) is str and HASH.fullmatch(expected) is not None,
                 "REVIEWED_SOURCE_DIGEST_ABSENT")
            raw=read_exact(self.source_root/name)
            need(digest(raw)==expected,
                 "REVIEWED_SOURCE_BYTES_CHANGED")
            bodies[name]=raw
        # The repository policy is a SOURCE scope proof, never the bytes
        # permitted to overwrite a separately root-controlled policy.
        # In production those two inputs can legitimately differ in
        # protected container allowances. Derive the minimal reviewed
        # six-unit delta from the ACTUAL exact root-owned old policy.
        source_policy=safe_json(read_exact(self.source_root/POLICY))
        source_plan=parity.plan_exact_unit_delta(source_policy)
        need(source_plan["candidate_policy_sha256"]==
             scope["source_candidate_policy_sha256"],
             "REVIEWED_POLICY_DIGEST_MISMATCH")
        root_prior=read_exact(self.targets[POLICY])
        need(digest(root_prior)==self.prior_sha256[POLICY],
             "ORIGINAL_ROOT_POLICY_BYTES_CHANGED")
        root_policy=safe_json(root_prior)
        root_plan=parity.plan_exact_unit_delta(root_policy)
        for field in ("retire_user_units","retire_system_units",
                      "add_user_units","add_system_units"):
            need(root_plan[field]==source_plan[field],
                 "ROOT_AND_REVIEWED_UNIT_DELTA_MISMATCH")
        allowed_changes=frozenset({
            "required_user_units","required_system_units",
            "allowed_user_units","allowed_system_units",
        })
        before=root_plan["candidate_policy"]
        need(set(before)==set(root_policy)
             and all(before[k]==root_policy[k]
                     for k in root_policy if k not in allowed_changes),
             "UNREVIEWED_ROOT_POLICY_FIELDS_CHANGED")
        bodies[POLICY]=parity.canon(before)
        return bodies

    def prepare(self,*,candidate:str,scope:Mapping[str,Any])->dict[str,Any]:
        """Root-durable before-image must be written before first code change."""
        self._guard()
        need(scope.get("candidate_sha")==candidate,
             "SIGNED_CANDIDATE_SCOPE_MISMATCH")
        proposed=self._reviewed_candidate(scope)
        target=self._snapshot_path(candidate)
        need(not target.exists() and not target.is_symlink(),
             "BEFORE_IMAGE_ALREADY_EXISTS")
        prior={}
        for relative in sorted(OBJECTS):
            path=self.targets[relative]
            raw=read_exact(path)
            meta=path.lstat()
            need((meta.st_uid,meta.st_gid,stat.S_IMODE(meta.st_mode))==
                 self.identities[relative],
                 "INSTALLED_FILE_IDENTITY_DRIFT")
            need(digest(raw)==self.prior_sha256[relative],
                 "EXACT_OLD_FILE_HASH_CHANGED")
            prior[relative]=raw
        parent=self.before_root.lstat()
        need(not self.before_root.is_symlink()
             and stat.S_ISDIR(parent.st_mode)
             and parent.st_mode&0o022==0,
             "ROOT_BEFORE_PARENT_UNTRUSTED")
        if self.production:
            need(parent.st_uid==parent.st_gid==0
                 and stat.S_IMODE(parent.st_mode)==0o700,
                 "ROOT_BEFORE_PARENT_NOT_PRIVATE")
        target.mkdir(mode=0o700)
        for i,(name,raw) in enumerate(sorted(prior.items())):
            p=target/("before-"+str(i)+".data")
            fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|
                       getattr(os,"O_NOFOLLOW",0),0o400)
            with os.fdopen(fd,"wb") as writer:
                writer.write(raw);writer.flush();os.fsync(writer.fileno())
        record={
            "schema_version":"1.0","action":packet.ACTION,
            "candidate_sha":candidate,"scope_sha256":digest(packet.canonical(scope)),
            "filenames":sorted(OBJECTS),
            "prior_sha256":self.prior_sha256,
            "candidate_sha256":{k:digest(v) for k,v in proposed.items()},
            "identities":{k:list(self.identities[k]) for k in OBJECTS},
            "complete":True,"code_mutations":False,
        }
        p=target/"manifest.json"
        fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|
                   getattr(os,"O_NOFOLLOW",0),0o400)
        with os.fdopen(fd,"wb") as out:
            out.write(packet.canonical(record))
            out.flush();os.fsync(out.fileno())
        os.chmod(target,0o500)
        need(self._read_before(candidate,scope)[0]==record,
             "DURABLE_BEFORE_READBACK_FAILED")
        return {"status":"signed_native_code_before_image_ready",
                "candidate_sha":candidate,"scope_sha256":record["scope_sha256"],
                "files":len(OBJECTS),"code_mutations":False}

    def _read_before(self,candidate:str,scope:Mapping[str,Any]):
        path=self._snapshot_path(candidate)
        meta=path.lstat()
        need(not path.is_symlink() and stat.S_ISDIR(meta.st_mode)
             and stat.S_IMODE(meta.st_mode)==0o500,
             "BEFORE_IMAGE_NOT_SEALED")
        record=safe_json(read_exact(path/"manifest.json"))
        need(set(record)=={
             "schema_version","action","candidate_sha","scope_sha256",
             "filenames","prior_sha256","candidate_sha256","identities",
             "complete","code_mutations"}
             and record["schema_version"]=="1.0"
             and record["action"]==packet.ACTION
             and record["candidate_sha"]==candidate
             and record["scope_sha256"]==digest(packet.canonical(scope))
             and record["complete"] is True
             and record["code_mutations"] is False
             and record["filenames"]==sorted(OBJECTS)
             and record["prior_sha256"]==self.prior_sha256,
             "BEFORE_IMAGE_MANIFEST_CHANGED")
        contents={}
        for i,name in enumerate(sorted(OBJECTS)):
            raw=read_exact(path/("before-"+str(i)+".data"))
            need(digest(raw)==record["prior_sha256"][name],
                 "BEFORE_IMAGE_FILE_DRIFT")
            contents[name]=raw
        need({p.name for p in path.iterdir()}==
             {"manifest.json"}|{"before-"+str(i)+".data" for i in range(len(OBJECTS))},
             "BEFORE_IMAGE_UNREVIEWED_OBJECT")
        return record,contents

    def apply(self,*,candidate:str,scope:Mapping[str,Any])->dict[str,Any]:
        self._guard()
        record,_=self._read_before(candidate,scope)
        proposed=self._reviewed_candidate(scope)
        need({k:digest(v) for k,v in proposed.items()}==
             record["candidate_sha256"],
             "CANDIDATE_CODE_DRIFT")
        for name in sorted(OBJECTS):
            raw=read_exact(self.targets[name])
            need(digest(raw) in {record["prior_sha256"][name],
                                record["candidate_sha256"][name]},
                 "PRE_APPLY_TARGET_DRIFT")
        for name in sorted(OBJECTS):
            path=self.targets[name]
            uid,gid,mode=self.identities[name]
            if digest(read_exact(path))!=record["candidate_sha256"][name]:
                atomic_exact(path,proposed[name],mode=mode,uid=uid,gid=gid)
        return self.verify(candidate=candidate,scope=scope)

    def verify(self,*,candidate:str,scope:Mapping[str,Any])->dict[str,Any]:
        self._guard()
        record,_=self._read_before(candidate,scope)
        for name in OBJECTS:
            path=self.targets[name]
            raw=read_exact(path)
            metadata=path.lstat()
            need(digest(raw)==record["candidate_sha256"][name]
                 and (metadata.st_uid,metadata.st_gid,
                      stat.S_IMODE(metadata.st_mode))==
                      self.identities[name],
                 "INSTALLED_CODE_NOT_EXACT")
        return {"status":"native_reviewed_controlplane_bytes_installed",
                "candidate_sha":candidate,"files":len(OBJECTS),
                "source_scope_sha256":record["scope_sha256"],
                "service_restarts":0,"provider_calls":0}

    def restore(self,*,candidate:str,scope:Mapping[str,Any])->dict[str,Any]:
        """Only exact prior/approved-candidate bytes may be restored."""
        self._guard()
        record,original=self._read_before(candidate,scope)
        for name in OBJECTS:
            actual=digest(read_exact(self.targets[name]))
            need(actual in {record["candidate_sha256"][name],
                            record["prior_sha256"][name]},
                 "ROLLBACK_UNKNOWN_INSTALLED_FILE")
        for name in sorted(OBJECTS):
            path=self.targets[name]
            uid,gid,mode=self.identities[name]
            if digest(read_exact(path))!=record["prior_sha256"][name]:
                atomic_exact(path,original[name],mode=mode,uid=uid,gid=gid)
        for name in OBJECTS:
            need(digest(read_exact(self.targets[name]))==
                 record["prior_sha256"][name],
                 "ORIGINAL_CODE_ROLLBACK_INCOMPLETE")
        return {"status":"native_original_controlplane_bytes_restored",
                "candidate_sha":candidate,"files":len(OBJECTS),
                "systemd_actions":0,"service_restarts":0}
