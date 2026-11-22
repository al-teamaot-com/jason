#!/usr/bin/env python3
"""Read-only exact Stage C host consumers and reversible systemd projections.

Not a release issuer or live installer. An independent root Owner-signed
transaction must pin the installed unit fragments, check canonical SQLite
identity/quiescence, and authorize daemon-reload/restarts. Never modify a host
unit from a normal engineering worktree.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import stat
from typing import Mapping

SHARED = Path("/var/lib/jason/governed-ticket-shared")
TICKET = Path("/var/lib/jason/ticket-core")
LEGACY = Path("/var/lib/jason/openclaw")
FRAGMENTS = Path("infrastructure/showcase/systemd")
UNIT_DIRECTORY = Path("/etc/systemd/system")
DROPIN_NAME = "99-pmv4-c-canonical-state.conf"

DB_FILES: Mapping[str,str] = {
    "JASON_MODEL_USAGE_DB":"model-usage.sqlite3",
    "JASON_ORCHESTRATION_EVENTS_DB":"orchestration-events.sqlite3",
    "JASON_TEAMS_IDENTITY_BINDINGS_DB":"teams-identity-bindings.sqlite3",
    "JASON_REFLECTION_DB":"reflection.sqlite3",
    "JASON_RESOLUTION_MEMORY_DB":"resolution-memory.sqlite3",
}

SERVICE_ENV: Mapping[str,tuple[str,...]] = {
    "jason-usage-exporter.service":(
        "JASON_MODEL_USAGE_DB",
        "JASON_ORCHESTRATION_EVENTS_DB",
        "JASON_TEAMS_IDENTITY_BINDINGS_DB",
    ),
    "jason-usage-attribution-exporter.service":(
        "JASON_MODEL_USAGE_DB",
        "JASON_ORCHESTRATION_EVENTS_DB",
        "JASON_TEAMS_IDENTITY_BINDINGS_DB",
    ),
    "jason-security-control-exporter.service":(
        "JASON_ORCHESTRATION_EVENTS_DB",
    ),
    "jason-reflection-exporter.service":(
        "JASON_REFLECTION_DB",
    ),
    "jason-resolution-memory-exporter.service":(
        "JASON_RESOLUTION_MEMORY_DB",
    ),
}


class HostProjectionDenied(ValueError):
    pass


def need(condition:bool,reason:str)->None:
    if not condition:
        raise HostProjectionDenied(reason)


def exact_canonical_path(env_name:str)->Path:
    need(env_name in DB_FILES,"C_HOST_UNREVIEWED_DB_ENV")
    return SHARED/DB_FILES[env_name]


def render_dropin(unit:str)->bytes:
    need(unit in SERVICE_ENV,"C_HOST_UNREVIEWED_SYSTEMD_UNIT")
    names=SERVICE_ENV[unit]
    need(names and len(set(names))==len(names),"C_HOST_INVALID_UNIT_PROJECTION")
    paths=[exact_canonical_path(k) for k in names]
    lines=[
        "# PMv4 C; only exact canonical SQLite paths; Owner-signed release required.",
        "[Service]",
    ]
    lines.extend("Environment="+k+"="+str(p) for k,p in zip(names,paths))
    # Reset old ReadOnlyPaths so no stale, missing file remains in the
    # effective sandbox. This does not change ExecStart, credentials, ports,
    # service identity, network, Docker, or production release source.
    lines.append("ReadOnlyPaths=")
    lines.append("ReadOnlyPaths=/opt/jason/current "+" ".join(map(str,paths)))
    return ("\n".join(lines)+"\n").encode("ascii")


def unit_bindings(unit:str)->dict[str,Path]:
    need(unit in SERVICE_ENV,"C_HOST_UNREVIEWED_SYSTEMD_UNIT")
    return {key:exact_canonical_path(key) for key in SERVICE_ENV[unit]}


def verify_fragment_bytes(source:Path,installed:Path,*,require_root:bool)->str:
    """Fail closed before considering a systemd drop-in."""
    source=Path(source)
    installed=Path(installed)
    need(source.name in SERVICE_ENV and source.name==installed.name,
         "C_HOST_FOREIGN_SERVICE_FRAGMENT")
    need(source.is_file() and not source.is_symlink()
         and installed.is_file() and not installed.is_symlink(),
         "C_HOST_FRAGMENT_NOT_REGULAR")
    if require_root:
        meta=installed.lstat()
        need(stat.S_ISREG(meta.st_mode) and meta.st_uid==0
             and meta.st_nlink==1
             and not stat.S_IMODE(meta.st_mode)&0o022,
             "C_HOST_INSTALLED_FRAGMENT_UNTRUSTED")
        need(installed.parent==UNIT_DIRECTORY,
             "C_HOST_UNIT_DIRECTORY_CHANGED")
    expected=source.read_bytes()
    need(installed.read_bytes()==expected,
         "C_HOST_INSTALLED_FRAGMENT_DRIFT")
    for env,path in unit_bindings(source.name).items():
        old=LEGACY/DB_FILES[env]
        need(b"Environment="+env.encode()+b"="+str(old).encode() in expected,
             "C_HOST_SOURCE_NO_LONGER_LEGACY")
        need(path.name==old.name and path.parent==SHARED,
             "C_HOST_UNEXPECTED_CANONICAL_ROOT")
    return sha256(expected).hexdigest()


def assert_canonical_files(*,uid:int=1000)->dict[str,tuple[int,int]]:
    """Read-only canonical DB identity gate, never opens SQLite for writing."""
    result={}
    for env,name in DB_FILES.items():
        path=SHARED/name
        original=LEGACY/name
        need(not original.exists() and not original.is_symlink(),
             "C_HOST_SPLIT_BRAIN_LEGACY_DB:"+name)
        info=path.lstat()
        need(not path.is_symlink() and stat.S_ISREG(info.st_mode)
             and stat.S_IMODE(info.st_mode)==0o600
             and info.st_uid==uid and info.st_nlink==1,
             "C_HOST_CANONICAL_DB_UNTRUSTED:"+name)
        result[name]=(info.st_dev,info.st_ino)
    return result


def all_dropins()->dict[str,bytes]:
    return {unit:render_dropin(unit) for unit in sorted(SERVICE_ENV)}
