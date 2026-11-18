#!/usr/bin/env python3
"""Root-owned Stage E trust bundle staging under the existing native controller.

No CLI, approval issuance, standalone release manager or unit activation.
Called only after the native ComponentReleaseController has independently
verified signed exact Owner proof, opened a STARTED receipt, and acquired its
host/freeze locks. Trust installation is inert and must be recorded in its
durable rollback journal before retiring any legacy triggers.

Production location: /opt/jason/pmv4-e-trusted
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import re
import stat
from typing import Any, Callable, Mapping
from tools import pmv4_e_exact_release_packet as packet

TARGET=Path("/opt/jason/pmv4-e-trusted")
SHA40=re.compile(r"^[0-9a-f]{40}$")


class PMv4ERootTrustDenied(PermissionError):
    pass


def require(ok:bool,why:str)->None:
    if not ok:
        raise PMv4ERootTrustDenied("PMV4_E_ROOT_TRUST_"+why)


def canonical_regular(path:Path,*,root_only:bool)->bytes:
    """Read only one immutable regular root object, never follow symlinks."""
    try:
        x=path.lstat()
        require(stat.S_ISREG(x.st_mode) and not path.is_symlink()
                and x.st_nlink==1 and 0<x.st_size<=1_000_000
                and x.st_mode&0o022==0,
                "SOURCE_FILE_UNTRUSTED")
        if root_only:
            require(x.st_uid==0 and x.st_gid==0,
                    "SOURCE_FILE_NOT_ROOT_OWNED")
        raw=path.read_bytes()
        require(len(raw)==x.st_size,"SOURCE_CHANGED_DURING_COPY")
        return raw
    except OSError as exc:
        raise PMv4ERootTrustDenied(
            "PMV4_E_ROOT_TRUST_SOURCE_READ_UNAVAILABLE") from exc


class RootTrustStager:
    def __init__(self,*,source:Path,target:Path=TARGET,
                 native_signed_started:Callable[[],bool],
                 native_host_locked:Callable[[],bool],
                 native_freeze_locked:Callable[[],bool],
                 native_marker_absent:Callable[[],bool],
                 native_replacements_inert:Callable[[],bool],
                 production:bool=True):
        require(callable(native_signed_started)
                and callable(native_host_locked)
                and callable(native_freeze_locked)
                and callable(native_marker_absent)
                and callable(native_replacements_inert),
                "NATIVE_RELEASE_BOUNDARY_MISSING")
        if production:
            require(os.geteuid()==0 and target==TARGET,
                    "ROOT_ONLY_CANONICAL_DESTINATION")
        self.source=Path(source)
        self.target=Path(target)
        self.native_signed_started=native_signed_started
        self.native_host_locked=native_host_locked
        self.native_freeze_locked=native_freeze_locked
        self.native_marker_absent=native_marker_absent
        self.native_replacements_inert=native_replacements_inert
        self.production=production

    def _governed(self):
        require(self.native_signed_started() is True,
                "SIGNED_START_RECEIPT_MISSING")
        require(self.native_host_locked() is True,
                "HOST_LOCK_REQUIRED")
        require(self.native_freeze_locked() is True,
                "FREEZE_LOCK_REQUIRED")

    def _source(self,relative:str,expected_sha:str)->bytes:
        require(relative in packet.REVIEWED_PATHS,
                "EXTRA_SOURCE_OUTSIDE_APPROVED_SCOPE")
        need_path=self.source/relative
        require(not self.source.is_symlink()
                and self.source.is_dir(),"SOURCE_ROOT_NOT_A_DIRECTORY")
        if self.production:
            parent=self.source
            while parent!=Path("/"):
                x=parent.lstat()
                require(not parent.is_symlink() and
                        stat.S_ISDIR(x.st_mode) and x.st_uid==0 and
                        x.st_gid==0 and x.st_mode&0o022==0,
                        "SOURCE_PARENT_MUTABLE_OR_NOT_ROOT")
                parent=parent.parent
            for parent in need_path.parents:
                if parent==self.source:
                    break
                x=parent.lstat()
                require(not parent.is_symlink() and
                        stat.S_ISDIR(x.st_mode) and x.st_uid==0
                        and x.st_gid==0 and x.st_mode&0o022==0,
                        "SOURCE_SUBDIRECTORY_MUTABLE")
        raw=canonical_regular(need_path,root_only=self.production)
        require(sha256(raw).hexdigest()==expected_sha,
                "SOURCE_DIGEST_MISMATCH")
        return raw

    def stage(self,*,source_sha:str,
              exact_hashes:Mapping[str,str])->dict[str,Any]:
        self._governed()
        require(self.native_marker_absent() is True and
                self.native_replacements_inert() is True,
                "INERT_STAGE_PRECONDITION_FAILED")
        require(isinstance(source_sha,str) and SHA40.fullmatch(source_sha)
                is not None,"SOURCE_SHA_INVALID")
        require(isinstance(exact_hashes,Mapping)
                and set(exact_hashes)==set(packet.REVIEWED_PATHS),
                "EXACT_FILE_SET_REQUIRED")
        require(all(isinstance(v,str) and
                    re.fullmatch(r"[0-9a-f]{64}",v)
                    for v in exact_hashes.values()),
                "SOURCE_HASH_UNTRUSTED")
        require(not self.target.exists() and not self.target.is_symlink(),
                "TARGET_ALREADY_STAGED")
        parent=self.target.parent.lstat()
        require(stat.S_ISDIR(parent.st_mode) and
                not self.target.parent.is_symlink(),
                "TARGET_PARENT_UNTRUSTED")
        if self.production:
            require(parent.st_uid==0 and parent.st_gid==0
                    and parent.st_mode&0o022==0,
                    "ROOT_TARGET_PARENT_MUTABLE")
        # Pre-verify *every* source BEFORE writing any installed root bytes.
        verified={path:self._source(path,exact_hashes[path])
                  for path in packet.REVIEWED_PATHS}
        self.target.mkdir(mode=0o700)
        made_dirs={self.target}
        for relative,raw in sorted(verified.items()):
            p=self.target/relative
            p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            parent=p.parent
            while parent!=self.target:
                made_dirs.add(parent)
                parent=parent.parent
            fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|
                       getattr(os,"O_NOFOLLOW",0),0o600)
            try:
                offset=0
                while offset<len(raw):
                    written=os.write(fd,raw[offset:])
                    require(written>0,"STAGING_WRITE_INCOMPLETE")
                    offset+=written
                os.fsync(fd)
            finally:
                os.close(fd)
            if self.production:
                os.chown(p,0,0)
            os.chmod(p,0o444)
        for directory in sorted(made_dirs,
                                key=lambda p:len(p.parts),reverse=True):
            if self.production:
                os.chown(directory,0,0)
            directory.chmod(0o555)
        return self.verify(exact_hashes)

    def verify(self,exact_hashes:Mapping[str,str])->dict[str,Any]:
        self._governed()
        require(set(exact_hashes)==set(packet.REVIEWED_PATHS),
                "VERIFY_FILE_SET_CHANGED")
        require(self.target.is_dir() and not self.target.is_symlink(),
                "INSTALLED_ROOT_ABSENT")
        seen=set()
        for path in self.target.rglob("*"):
            require(not path.is_symlink(),"INSTALLED_SYMLINK_UNTRUSTED")
            x=path.lstat()
            if path.is_dir():
                require(stat.S_ISDIR(x.st_mode) and
                        stat.S_IMODE(x.st_mode)==0o555,
                        "INSTALLED_DIR_NOT_SEALED")
            elif path.is_file():
                relative=path.relative_to(self.target).as_posix()
                require(relative in exact_hashes and
                        stat.S_ISREG(x.st_mode) and x.st_nlink==1 and
                        stat.S_IMODE(x.st_mode)==0o444,
                        "UNREVIEWED_OR_MUTABLE_FILE")
                if self.production:
                    require(x.st_uid==0 and x.st_gid==0,
                            "INSTALLED_FILE_NOT_ROOT_OWNED")
                require(sha256(path.read_bytes()).hexdigest()
                        ==exact_hashes[relative],
                        "INSTALLED_FILE_DIGEST_CHANGED")
                seen.add(relative)
            else:
                raise PMv4ERootTrustDenied(
                    "PMV4_E_ROOT_TRUST_UNREVIEWED_OBJECT_TYPE")
        require(seen==set(exact_hashes),
                "INSTALLED_FILES_INCOMPLETE")
        return {
            "status":"reviewed_root_trust_bundle_sealed_no_unit_activation",
            "installed_file_count":len(seen),
            "production_services_changed":False,
            "owner_release_authorized":False,
        }

    def recover_inert_stage(self,exact_hashes:Mapping[str,str])->None:
        self._governed()
        require(self.native_marker_absent() is True and
                self.native_replacements_inert() is True,
                "LIVE_REPLACEMENT_RECOVERY_DENIED")
        require(set(exact_hashes)==set(packet.REVIEWED_PATHS),
                "RECOVERY_FILE_SCOPE_CHANGED")
        require(self.target.is_dir() and not self.target.is_symlink(),
                "RECOVERY_ROOT_ABSENT")
        # In-progress root staging must have no accepted marker or active
        # new dispatch. The native root controller verifies those facts.
        # A symlink, unknown path or altered byte denies destructive cleanup.
        files=sorted((p for p in self.target.rglob("*") if p.is_file()),
                     key=lambda p:len(p.parts),reverse=True)
        source={rel:self._source(rel,exact_hashes[rel])
                for rel in exact_hashes}
        seen=set()
        for p in self.target.rglob("*"):
            require(not p.is_symlink()
                    and (p.is_file() or p.is_dir()),
                    "RECOVERY_UNREVIEWED_OBJECT")
            if p.is_file():
                relative=p.relative_to(self.target).as_posix()
                require(relative in exact_hashes,
                        "RECOVERY_EXTRA_FILE")
                value=p.read_bytes()
                require(len(value)<=len(source[relative])
                        and source[relative].startswith(value)
                        and p.stat().st_mode&0o022==0,
                        "RECOVERY_FILE_DRIFT")
                seen.add(relative)
        directories=sorted(
            (p for p in self.target.rglob("*") if p.is_dir()),
            key=lambda p:len(p.parts))
        # Restore root write on only exact previously verified directories.
        self.target.chmod(0o700)
        for directory in directories:
            directory.chmod(0o700)
        for p in files:
            p.unlink()
        for directory in reversed(directories):
            directory.rmdir()
        self.target.rmdir()
