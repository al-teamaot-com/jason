#!/usr/bin/env python3
"""Stage E current Ticket Core owner: read-only kernel + container identity proof.

No lock acquisition, provider call, container mutation or owner authority.
Production use requires a separately installed trusted root-only source pin.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any, Callable

LEDGER=Path("/var/lib/jason/ticket-core/autonomy-operational-work.sqlite3")
CONTAINER="jason-pmv4-ticket-core"
LOCKS=Path("/proc/locks")
PROC=Path("/proc")
LOCK_RE=re.compile(
    r"^\d+:\s+(FLOCK|POSIX|OFDLCK)\s+ADVISORY\s+"
    r"(READ|WRITE)\s+(-?\d+)\s+([0-9a-fA-F]+):"
    r"([0-9a-fA-F]+):(\d+)\s+\d+\s+(?:EOF|\d+)$"
)
ID_RE=re.compile(r"^[0-9a-f]{64}$")


class TicketOwnerReadbackDenied(PermissionError):
    pass


def require(ok:bool,why:str)->None:
    if not ok:
        raise TicketOwnerReadbackDenied("PMV4_E_TICKET_OWNER_"+why)


def lock_inode(path:Path)->os.stat_result:
    require(path.is_absolute() and not path.is_symlink()
            and not path.parent.is_symlink() and path.parent.is_dir(),
            "LOCK_PATH_UNTRUSTED")
    try:
        info=path.lstat()
    except OSError as exc:
        raise TicketOwnerReadbackDenied("PMV4_E_TICKET_OWNER_LOCK_ABSENT") from exc
    require(stat.S_ISREG(info.st_mode) and info.st_uid==1000
            and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1,
            "LOCK_FILE_UNTRUSTED")
    return info


def locks_for_inode(raw:str,meta:os.stat_result)->list[tuple[str,str,int]]:
    require(isinstance(raw,str) and len(raw)<2_000_000,
            "KERNEL_LOCK_LIST_UNAVAILABLE")
    result=[]
    for line in raw.splitlines():
        m=LOCK_RE.fullmatch(line.strip())
        if not m:
            # Unknown lock rows may belong to the target inode. Never
            # silently trust malformed rows that mention the exact inode.
            if re.search(r":%s\s" % re.escape(str(meta.st_ino)),line):
                raise TicketOwnerReadbackDenied("PMV4_E_TICKET_OWNER_LOCK_RECORD_UNKNOWN")
            continue
        typ,mode,pid,major,minor,inode=m.groups()
        if (int(major,16),int(minor,16),int(inode)) == (
            os.major(meta.st_dev),os.minor(meta.st_dev),meta.st_ino
        ):
            result.append((typ,mode,int(pid)))
    return result


def docker_state(*,runner:Callable[...,Any]=subprocess.run)->tuple[str,int]:
    fmt="{{.Id}}|{{.State.Pid}}|{{.State.Running}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}"
    p=runner(["/usr/bin/docker","inspect","--format",fmt,CONTAINER],
             capture_output=True,text=True,timeout=18,check=False)
    require(p.returncode==0 and len(p.stdout)<200 and "\n" not in p.stdout.strip(),
            "TICKET_CONTAINER_UNAVAILABLE")
    values=p.stdout.strip().split("|")
    require(len(values)==4 and ID_RE.fullmatch(values[0]) is not None
            and values[1].isdecimal() and 1<int(values[1])<2**31
            and values[2]=="true" and values[3]=="healthy",
            "TICKET_CONTAINER_NOT_HEALTHY")
    return values[0],int(values[1])


def owner_is_child_of_root(pid:int,container_pid:int, *,
                           proc:Path=PROC)->bool:
    require(1<pid<2**31 and 1<container_pid<2**31,
            "PID_UNTRUSTED")
    seen=set()
    for _ in range(64):
        if pid==container_pid:
            return True
        if pid<=1 or pid in seen:
            return False
        seen.add(pid)
        path=proc/str(pid)/"status"
        try:
            raw=path.read_text(encoding="utf-8")
        except OSError as exc:
            raise TicketOwnerReadbackDenied(
                "PMV4_E_TICKET_OWNER_PROCESS_RACE") from exc
        lines=[s for s in raw.splitlines() if s.startswith("PPid:")]
        require(len(lines)==1 and lines[0].split(":",1)[1].strip().isdecimal(),
                "PROCESS_PARENT_UNTRUSTED")
        pid=int(lines[0].split(":",1)[1].strip())
    return False


def inspect(*,runner:Callable[...,Any]=subprocess.run,
            lock_path:Path|None=None,locks_path:Path=LOCKS,
            proc_root:Path=PROC)->dict[str,Any]:
    require(os.geteuid()==0,"ROOT_ONLY")
    lock_path=lock_path or LEDGER.with_name(LEDGER.name+".owner.lock")
    meta=lock_inode(lock_path)
    try:
        prior=locks_path.read_text(encoding="ascii")
    except OSError as exc:
        raise TicketOwnerReadbackDenied("PMV4_E_TICKET_OWNER_LOCK_LIST_MISSING") from exc
    locks=locks_for_inode(prior,meta)
    require(len(locks)==1 and locks[0][0]=="FLOCK"
            and locks[0][1]=="WRITE" and locks[0][2]>1,
            "EXCLUSIVE_LOCK_OWNER_NOT_UNIQUE")
    owner_pid=locks[0][2]
    container_id,container_pid=docker_state(runner=runner)
    require(owner_is_child_of_root(owner_pid,container_pid,proc=proc_root),
            "LOCK_OWNER_NOT_EXTERNAL_TICKET_CORE")
    # Re-check the lock inode, kernel owner and Docker PID after the
    # parent-chain lookup: races must fail rather than grant stale proof.
    newer=lock_inode(lock_path)
    require((meta.st_dev,meta.st_ino)==(newer.st_dev,newer.st_ino),
            "LOCK_INODE_CHANGED")
    require(locks_for_inode(locks_path.read_text(encoding="ascii"),newer)==locks,
            "LOCK_OWNER_CHANGED")
    require(docker_state(runner=runner)==(container_id,container_pid),
            "CONTAINER_PID_CHANGED")
    return {
        "status":"live_external_ticket_core_exclusive_owner_verified",
        "unique_owner":True,
        "lock_owner_pid":owner_pid,
        "container_init_pid":container_pid,
        "container_id":container_id,
        "lock_inode":meta.st_ino,
        "exclusive_owner_count":1,
        "production_mutations":False,
        "owner_authority_issued":False,
    }
