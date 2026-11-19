#!/usr/bin/env python3
"""Exact one-candidate immutable root source staging for Stage E.

This is NOT an installer/authority issuer, root CLI or second release manager.
A separately authenticated signed-native bootstrap must FIRST verify the exact
Owner proof, protected Git/CI and hold original host+freeze locks. This helper
then seals only reviewed bytes at /opt/jason/releases/<candidate>. Future
Stage E root trust stager independently rehashes this root-owned source.

Production requires an independently installed root-owned pinned executable,
with a canonical reviewed source clone and no user-provided target paths.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import re
import stat
from typing import Any,Callable,Mapping

from tools import pmv4_e_exact_release_packet as packet

ENTRY=Path("/usr/local/lib/jason/pmv4-e-bootstrap/trusted/tools/pmv4_e_immutable_source_stage.py")
SOURCE=Path("/srv/jason/archive/engineering-artifacts/pmv4-e-owner-source-repo")
TARGET_PARENT=Path("/opt/jason/releases")
SHA40=re.compile(r"^[0-9a-f]{40}$")
DIGEST=re.compile(r"^[0-9a-f]{64}$")


class RootSourceStageDenied(PermissionError):
    pass


def need(ok:bool,why:str)->None:
    if not ok:
        raise RootSourceStageDenied("PMV4_E_ROOT_SOURCE_"+why)


def trusted_source_file(path:Path,expected:str)->bytes:
    need(type(expected) is str and DIGEST.fullmatch(expected) is not None,
         "UNREVIEWED_SOURCE_DIGEST")
    try:
        stat_before=path.lstat()
        need(not path.is_symlink()
             and stat.S_ISREG(stat_before.st_mode)
             and stat_before.st_nlink==1 and
             0<stat_before.st_size<1000000 and
             stat_before.st_mode&0o002==0,
             "ORIGINAL_GIT_FILE_NOT_REGULAR")
        contents=path.read_bytes()
        stat_after=path.lstat()
        need((stat_before.st_dev,stat_before.st_ino,
              stat_before.st_size,stat_before.st_mtime_ns)==(
              stat_after.st_dev,stat_after.st_ino,
              stat_after.st_size,stat_after.st_mtime_ns)
             and len(contents)==stat_before.st_size,
             "ORIGINAL_SOURCE_RACE")
        need(sha256(contents).hexdigest()==expected,
             "SOURCE_NOT_SIGNED_REVIEWED_BYTES")
        return contents
    except RootSourceStageDenied:
        raise
    except OSError as exc:
        raise RootSourceStageDenied(
            "PMV4_E_ROOT_SOURCE_BYTES_UNAVAILABLE") from exc


class ImmutableRootSourceStage:
    """Root-only one-shot exact sealed source staging; no service changes."""

    def __init__(
        self,*,source:Path=SOURCE,target_parent:Path=TARGET_PARENT,
        exact_owner_verified:Callable[[],bool],
        original_host_locked:Callable[[],bool],
        original_freeze_locked:Callable[[],bool],
        marker_absent:Callable[[],bool],
        replacement_inert:Callable[[],bool],
        production:bool=True,
    ):
        if production:
            here=Path(__file__)
            meta=here.lstat()
            need(os.geteuid()==0
                 and here==ENTRY and here.resolve()==ENTRY
                 and not here.is_symlink()
                 and stat.S_ISREG(meta.st_mode)
                 and meta.st_uid==meta.st_gid==0
                 and stat.S_IMODE(meta.st_mode)==0o444
                 and Path(source)==SOURCE
                 and Path(target_parent)==TARGET_PARENT,
                 "CANONICAL_SIGNED_ROOT_INSTALL_REQUIRED")
        for callback in (exact_owner_verified,original_host_locked,
                         original_freeze_locked,marker_absent,
                         replacement_inert):
            need(callable(callback),"NATIVE_SIGNED_CONTEXT_REQUIRED")
        self.source=Path(source)
        self.target_parent=Path(target_parent)
        self.exact_owner_verified=exact_owner_verified
        self.original_host_locked=original_host_locked
        self.original_freeze_locked=original_freeze_locked
        self.marker_absent=marker_absent
        self.replacement_inert=replacement_inert
        self.production=production

    def _guard(self)->None:
        need(self.exact_owner_verified() is True,
             "EXACT_AUTHENTICATED_OWNER_SIGNATURE_REQUIRED")
        need(self.original_host_locked() is True
             and self.original_freeze_locked() is True,
             "ORIGINAL_NATIVE_HOST_FREEZE_LOCKS_REQUIRED")
        need(self.marker_absent() is True
             and self.replacement_inert() is True,
             "CUTOVER_ALREADY_STARTED")
        root=self.target_parent.lstat()
        need(not self.target_parent.is_symlink()
             and stat.S_ISDIR(root.st_mode)
             and root.st_mode&0o022==0,
             "PROTECTED_RELEASE_PARENT_UNTRUSTED")
        if self.production:
            need(root.st_uid==root.st_gid==0,
                 "PROTECTED_RELEASE_PARENT_NOT_ROOT_OWNED")

    def _paths(self,candidate:str,hashes:Mapping[str,str]):
        need(type(candidate) is str and SHA40.fullmatch(candidate) is not None,
             "EXACT_SOURCE_SHA_REQUIRED")
        need(type(hashes) is dict and set(hashes)==set(packet.REVIEWED_PATHS)
             and all(type(v) is str and DIGEST.fullmatch(v) is not None
                     for v in hashes.values()),
             "EXACT_REVIEWED_FILE_INVENTORY_REQUIRED")
        return self.target_parent/candidate,self.target_parent/(
            "."+candidate+".pmv4-e-inert-source")

    def _bytes(self,hashes:Mapping[str,str])->dict[str,bytes]:
        need(self.source.is_dir() and not self.source.is_symlink(),
             "REVIEWED_REPO_NOT_TRUSTED")
        if self.production:
            info=self.source.lstat()
            need(info.st_uid==info.st_gid==1000
                 and stat.S_IMODE(info.st_mode)==0o700,
                 "REVIEWED_REPO_NOT_OWNER_PRIVATE")
        return {
            relative:trusted_source_file(self.source/relative,expected)
            for relative,expected in sorted(hashes.items())
        }

    def stage(self,*,candidate:str,
              exact_hashes:Mapping[str,str])->dict[str,Any]:
        self._guard()
        target,temp=self._paths(candidate,exact_hashes)
        need(not target.exists() and not target.is_symlink()
             and not temp.exists() and not temp.is_symlink(),
             "RELEASE_ALREADY_STAGED_OR_INTERRUPTED")
        all_bytes=self._bytes(exact_hashes)
        temp.mkdir(mode=0o700)
        if self.production:
            os.chown(temp,0,0)
        made={temp}
        for relative,body in sorted(all_bytes.items()):
            p=temp/relative
            p.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            parent=p.parent
            while parent!=temp:
                made.add(parent)
                parent=parent.parent
            fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|
                       getattr(os,"O_NOFOLLOW",0),0o600)
            with os.fdopen(fd,"wb") as writer:
                writer.write(body);writer.flush();os.fsync(writer.fileno())
            if self.production:
                os.chown(p,0,0)
            p.chmod(0o444)
        for directory in sorted(made,key=lambda d:len(d.parts),reverse=True):
            if self.production:
                os.chown(directory,0,0)
            directory.chmod(0o555)
        self._verify_tree(temp,exact_hashes)
        os.replace(temp,target)
        fd=os.open(self.target_parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
        self._verify_tree(target,exact_hashes)
        return {
            "status":"exact_immutable_candidate_source_staged_inert",
            "candidate_sha":candidate,
            "source_file_count":len(all_bytes),
            "file_set_sha256":sha256(packet.canonical(
                dict(sorted(exact_hashes.items())))).hexdigest(),
            "owner_authority_issued":False,
            "production_unit_changes":False,
            "runtime_mcp_restarts":0,
        }

    def _verify_tree(self,target:Path,hashes:Mapping[str,str])->None:
        info=target.lstat()
        need(stat.S_ISDIR(info.st_mode) and not target.is_symlink()
             and stat.S_IMODE(info.st_mode)==0o555,
             "INSTALLED_IMMUTABLE_RELEASE_NOT_SEALED")
        if self.production:
            need(info.st_uid==info.st_gid==0,
                 "ROOT_SOURCE_DIR_NOT_ROOT_OWNED")
        known=set()
        for path in target.rglob("*"):
            need(not path.is_symlink(),"IMMUTABLE_RELEASE_SYMLINK_DENIED")
            if path.is_file():
                name=path.relative_to(target).as_posix()
                need(name in hashes,"UNREVIEWED_SOURCE_FILE_INSTALLED")
                meta=path.lstat()
                need(stat.S_ISREG(meta.st_mode)
                     and stat.S_IMODE(meta.st_mode)==0o444
                     and (not self.production or
                          (meta.st_uid==0 and meta.st_gid==0)),
                     "RELEASE_FILE_IDENTITY_DRIFT")
                need(sha256(path.read_bytes()).hexdigest()==hashes[name],
                     "RELEASE_INSTALLED_FILE_DIGEST_CHANGED")
                known.add(name)
            else:
                meta=path.lstat()
                need(stat.S_ISDIR(meta.st_mode)
                     and stat.S_IMODE(meta.st_mode)==0o555
                     and (not self.production or meta.st_uid==meta.st_gid==0),
                     "RELEASE_DIRECTORY_UNTRUSTED")
        need(known==set(hashes),"IMMUTABLE_RELEASE_FILE_SET_INCOMPLETE")

    def verify(self,*,candidate:str,
               exact_hashes:Mapping[str,str])->dict[str,Any]:
        self._guard()
        target,_=self._paths(candidate,exact_hashes)
        self._verify_tree(target,exact_hashes)
        return {
            "status":"reviewed_root_source_readback_verified",
            "candidate_sha":candidate,
            "source_file_count":len(exact_hashes),
            "production_mutations":False,
        }

    def recover_inert(self,*,candidate:str,
                      exact_hashes:Mapping[str,str])->dict[str,Any]:
        """Only delete an exact sealed candidate, never current or foreign."""
        self._guard()
        target,temp=self._paths(candidate,exact_hashes)
        need(not temp.exists() and not temp.is_symlink(),
             "INTERRUPTED_UNSEALED_SOURCE_REQUIRES_SUPERVISED_RECOVERY")
        if not target.exists() and not target.is_symlink():
            return {"status":"already_absent","production_mutations":False}
        need(not Path("/opt/jason/current").resolve()==target
             if self.production else True,
             "RELEASE_IS_CURRENT_SOURCE")
        self._verify_tree(target,exact_hashes)
        for relative in sorted(exact_hashes,key=lambda x:(x.count("/"),x),
                               reverse=True):
            (target/relative).unlink()
        for item in sorted(target.rglob("*"),
                           key=lambda p:len(p.parts),reverse=True):
            need(item.is_dir() and not item.is_symlink(),
                 "RECOVERY_FOREIGN_OBJECT")
            item.rmdir()
        target.rmdir()
        return {
            "status":"exact_unused_immutable_source_removed",
            "candidate_sha":candidate,
            "removed_files":len(exact_hashes),
            "unit_changes":0,"runtime_mcp_restarts":0,
        }
