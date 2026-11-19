#!/usr/bin/env python3
"""Exact systemd surface for an installed Stage E native host callback.

No CLI, approval issuer, independent release engine, service restart, provider
access or production automation. Must be loaded only from immutable root-owned
Stage E trust by the already-signed ComponentReleaseController callback.
Systemd actions target exactly the six reviewed old/new timer/path triggers.
The native controller owns lock, signed receipt, staged before-image, policy
commit, error recovery and postflight authority.
"""
from __future__ import annotations
from hashlib import sha256
import os
from pathlib import Path
import stat
import subprocess
from typing import Any, Callable, Mapping
from tools import pmv4_e_replacement_unit_bundle as bundle
from tools import pmv4_e_scheduler_parity as parity

INSTALLED=Path("/opt/jason/pmv4-e-trusted/tools/pmv4_e_systemd_root_ops.py")
USER_UNIT_ROOT=Path("/home/al/.config/systemd/user")
SYSTEM_UNIT_ROOT=Path("/etc/systemd/system")
TRUSTED_UNITS=Path("/opt/jason/pmv4-e-trusted/infrastructure/pmv4-e-scheduler/systemd")
NEW_USER=frozenset(parity.USER_REPLACEMENT)
NEW_ROOT=frozenset(parity.ROOT_REPLACEMENT)
OLD_USER=frozenset(parity.USER_LEGACY)
OLD_ROOT=frozenset(parity.ROOT_LEGACY)
NEW_SERVICES=frozenset(
    n.replace(".timer",".service").replace(".path",".service")
    for n in NEW_USER | NEW_ROOT
)
NAME_ALLOWLIST=NEW_USER|NEW_ROOT|OLD_USER|OLD_ROOT
ROOT_CONTROL="/usr/bin/systemctl"
USER_CONTROL=(
    "/usr/sbin/runuser","-u","al","--","/usr/bin/env",
    "XDG_RUNTIME_DIR=/run/user/1000",
    "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus",
    "/usr/bin/systemctl","--user",
)


class StageESystemdDenied(PermissionError):
    pass


def need(ok:bool,why:str):
    if not ok:
        raise StageESystemdDenied("PMV4_E_SYSTEMD_"+why)


class ExactSystemdSurface:
    def __init__(self,*,runner:Callable[...,Any]=subprocess.run,
                 production:bool=True,
                 user_dir:Path=USER_UNIT_ROOT,
                 system_dir:Path=SYSTEM_UNIT_ROOT,
                 trusted_dir:Path=TRUSTED_UNITS):
        if production:
            here=Path(__file__)
            meta=here.lstat()
            need(os.geteuid()==0 and here.resolve()==INSTALLED
                 and not here.is_symlink()
                 and stat.S_ISREG(meta.st_mode)
                 and meta.st_uid==0 and meta.st_gid==0
                 and meta.st_mode&0o222==0,
                 "IMMUTABLE_INSTALLED_ROOT_REQUIRED")
            need(user_dir==USER_UNIT_ROOT and
                 system_dir==SYSTEM_UNIT_ROOT and
                 trusted_dir==TRUSTED_UNITS,
                 "NONCANONICAL_PRODUCTION_PATH")
        if production:
            for protected in (TRUSTED_UNITS, TRUSTED_UNITS.parent,
                              TRUSTED_UNITS.parent.parent,
                              TRUSTED_UNITS.parent.parent.parent):
                info=protected.lstat()
                need(stat.S_ISDIR(info.st_mode)
                     and not protected.is_symlink()
                     and info.st_uid==0 and info.st_gid==0
                     and info.st_mode&0o022==0,
                     "TRUSTED_SOURCE_DIRECTORY_MUTABLE")
        self.runner=runner
        self.production=production
        self.user_dir=Path(user_dir)
        self.system_dir=Path(system_dir)
        self.trusted_dir=Path(trusted_dir)

    def _call(self,*,user:bool,action:str,names:tuple[str,...]=())->str:
        need(action in {"is-active","is-enabled","disable","enable","stop",
                        "start","daemon-reload"},"UNREVIEWED_SYSTEMD_VERB")
        need(all(n in NAME_ALLOWLIST for n in names),
             "OUT_OF_SCOPE_UNIT")
        need(bool(names) or action=="daemon-reload",
             "EMPTY_UNIT_ACTION")
        prefix=list(USER_CONTROL) if user else [ROOT_CONTROL]
        argv=prefix+[action]+list(names)
        p=self.runner(argv,capture_output=True,text=True,
                      check=False,timeout=35)
        need(p.returncode==0 if action not in {"is-active","is-enabled"}
             else p.returncode in (0,1,3,4),
             "SYSTEMD_OPERATION_FAILED")
        return p.stdout.strip()

    def status(self,name:str,*,user:bool)->tuple[str,str]:
        valid=NEW_USER|OLD_USER if user else NEW_ROOT|OLD_ROOT
        need(name in valid,"OUT_OF_SCOPE_STATUS")
        active=self._call(user=user,action="is-active",names=(name,))
        enabled=self._call(user=user,action="is-enabled",names=(name,))
        need(active in {"active","inactive","failed"}
             and enabled in {"enabled","disabled","static","masked"},
             "SYSTEMD_STATE_UNKNOWN")
        return active,enabled

    def stage(self,approved_hashes:Mapping[str,str])->tuple[str,...]:
        """Copy only twelve exact reviewed unit files; new targets must be absent.

        Caller must have already stored durable root before-image under the
        existing signed STARTED receipt. No legacy triggers are disabled here.
        """
        expected={
            str(rel):data
            for rel,data in bundle.generate(base=self.trusted_dir.parents[2]).items()
        }
        # No silently accepted extra unit files or source path aliases.
        need(set(approved_hashes)==set(expected) and len(expected)==12,
             "EXACT_UNIT_HASH_SET_REQUIRED")
        created=[]
        for rel,body in sorted(expected.items()):
            need(sha256(body).hexdigest()==approved_hashes[rel],
                 "REVIEWED_UNIT_DIGEST_CHANGED")
            rel_path=Path(rel)
            need(rel_path.parts[:3]==("infrastructure","pmv4-e-scheduler","systemd"),
                 "UNIT_STAGE_PATH_CHANGED")
            side=rel_path.parts[-2]
            need(side in {"user","system"},"UNIT_SIDE_CHANGED")
            name=rel_path.name
            need(name in NEW_USER|NEW_ROOT|NEW_SERVICES,
                 "UNIT_NAME_NOT_APPROVED")
            target=(self.user_dir if side=="user" else self.system_dir)/name
            need(not target.exists() and not target.is_symlink(),
                 "TARGET_ALREADY_EXISTS")
            parent=target.parent.lstat()
            need(stat.S_ISDIR(parent.st_mode) and not target.parent.is_symlink(),
                 "TARGET_DIRECTORY_UNTRUSTED")
            if self.production:
                need(parent.st_uid in ((1000,) if side=="user" else (0,))
                     and parent.st_mode&0o022==0,
                     "TARGET_DIRECTORY_OWNER_UNTRUSTED")
            # O_EXCL and O_NOFOLLOW prevent replacement of an existing unit.
            fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|
                       getattr(os,"O_NOFOLLOW",0),0o644)
            try:
                offset=0
                while offset<len(body):
                    wrote=os.write(fd,body[offset:])
                    need(wrote>0,"UNIT_WRITE_INCOMPLETE")
                    offset+=wrote
                os.fsync(fd)
            finally:
                os.close(fd)
            if self.production:
                os.chown(target,0,0)
                os.chmod(target,0o644)
            created.append(str(target))
        self._call(user=True,action="daemon-reload")
        self._call(user=False,action="daemon-reload")
        return tuple(created)

    def unstage_exact(self,approved_hashes:Mapping[str,str])->None:
        """Recovery-only: remove only reviewed newly staged units by exact hash.

        This must follow root-marker revocation and disabled PMv4 triggers.
        Missing targets are accepted for interrupted partial staging; modified
        or symlink targets are denied and left for supervised recovery.
        """
        expected=bundle.generate(base=self.trusted_dir.parents[2])
        need(set(expected)==set(approved_hashes),"ROLLBACK_HASH_SET_INVALID")
        for rel,data in sorted(expected.items()):
            need(sha256(data).hexdigest()==approved_hashes[rel],
                 "ROLLBACK_REVIEWED_HASH_CHANGED")
            p=Path(rel)
            side=p.parts[-2]
            target=(self.user_dir if side=="user" else self.system_dir)/p.name
            if not target.exists() and not target.is_symlink():
                continue
            info=target.lstat()
            need(stat.S_ISREG(info.st_mode) and not target.is_symlink()
                 and info.st_nlink==1 and target.read_bytes()==data,
                 "ROLLBACK_UNIT_DRIFT")
            if self.production:
                need(info.st_uid==0 and info.st_gid==0,
                     "ROLLBACK_TARGET_NOT_ROOT_OWNED")
            target.unlink()
        self._call(user=True,action="daemon-reload")
        self._call(user=False,action="daemon-reload")

    def disable_legacy(self)->None:
        for user,units in ((True,OLD_USER),(False,OLD_ROOT)):
            for name in sorted(units):
                self._call(user=user,action="stop",names=(name,))
                self._call(user=user,action="disable",names=(name,))
                need(self.status(name,user=user)[0]!="active",
                     "OLD_TRIGGER_STILL_ACTIVE")

    def activate_replacement(self)->None:
        for user,units in ((True,NEW_USER),(False,NEW_ROOT)):
            for name in sorted(units):
                self._call(user=user,action="enable",names=(name,))
                self._call(user=user,action="start",names=(name,))
                need(self.status(name,user=user)==("active","enabled"),
                     "NEW_TRIGGER_NOT_ACTIVE")

    def restore_legacy(self)->None:
        for user,units in ((True,NEW_USER),(False,NEW_ROOT)):
            for name in sorted(units):
                self._call(user=user,action="stop",names=(name,))
                self._call(user=user,action="disable",names=(name,))
        for user,units in ((True,OLD_USER),(False,OLD_ROOT)):
            for name in sorted(units):
                self._call(user=user,action="enable",names=(name,))
                self._call(user=user,action="start",names=(name,))
                need(self.status(name,user=user)==("active","enabled"),
                     "ROLLBACK_LEGACY_NOT_ACTIVE")

    def verify_final(self,*,replacement:bool)->bool:
        groups=((NEW_USER,True),(NEW_ROOT,False)) if replacement else (
            (OLD_USER,True),(OLD_ROOT,False))
        banned=((OLD_USER,True),(OLD_ROOT,False)) if replacement else (
            (NEW_USER,True),(NEW_ROOT,False))
        for names,user in groups:
            for name in names:
                if self.status(name,user=user)!=("active","enabled"):
                    return False
        for names,user in banned:
            for name in names:
                if self.status(name,user=user)[0]=="active":
                    return False
        return True
