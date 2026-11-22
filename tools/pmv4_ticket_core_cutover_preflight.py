#!/usr/bin/env python3
"""Read-only production migration admission for PMv4's separately owned Ticket Core.

The embedded worker and future external worker must reference one canonical
SQLite DB and one unlinked-never lock inode on the same filesystem. The
existing broad /var/lib/jason/openclaw mount MUST NOT be given to the new
independent service. This checker neither migrates data nor stops a worker.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from typing import Any, Mapping, Sequence

OLD_LEDGER = Path("/var/lib/jason/openclaw/autonomy-operational-work.sqlite3")
NEW_LEDGER = Path("/var/lib/jason/ticket-core/autonomy-operational-work.sqlite3")
LEGACY_STATE = Path("/var/lib/jason/openclaw")
DEDICATED_STATE = Path("/var/lib/jason/ticket-core")
DEFAULT_EXPECTED_UID = 1000


class CoreCutoverDenied(RuntimeError):
    pass


@dataclass(frozen=True)
class FileIdentity:
    path: str
    device: int
    inode: int
    uid: int
    mode: int


def identity(path: Path, *, uid: int = DEFAULT_EXPECTED_UID) -> FileIdentity:
    path = Path(path)
    if (not path.is_absolute() or ".." in path.parts or path.is_symlink()
        or path.parent.is_symlink()):
        raise CoreCutoverDenied("CORE_DATA_PATH_UNTRUSTED")
    try:
        info = path.stat()
    except OSError as exc:
        raise CoreCutoverDenied("CORE_DATA_PATH_UNAVAILABLE") from exc
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
        or info.st_uid != uid or stat.S_IMODE(info.st_mode) != 0o600):
        raise CoreCutoverDenied("CORE_DATA_INODE_UNTRUSTED")
    return FileIdentity(str(path),info.st_dev,info.st_ino,info.st_uid,
                        stat.S_IMODE(info.st_mode))


def check_same_canonical_files(
    embedded_ledger: Path, external_ledger: Path, *, uid: int = DEFAULT_EXPECTED_UID
) -> dict[str,bool]:
    """Both paths must literally resolve to the same mounted ledger and lock inode."""
    e = identity(embedded_ledger,uid=uid)
    x = identity(external_ledger,uid=uid)
    elock = identity(embedded_ledger.with_name(embedded_ledger.name+".owner.lock"),uid=uid)
    xlock = identity(external_ledger.with_name(external_ledger.name+".owner.lock"),uid=uid)
    if (e.device,e.inode) != (x.device,x.inode):
        raise CoreCutoverDenied("CORE_LEDGER_INODE_DIFFERENT")
    if (elock.device,elock.inode) != (xlock.device,xlock.inode):
        raise CoreCutoverDenied("CORE_LOCK_INODE_DIFFERENT")
    if e.device != elock.device or x.device != xlock.device:
        raise CoreCutoverDenied("CORE_LEDGER_LOCK_FILESYSTEM_DIFFERENT")
    return {"same_ledger_inode":True,"same_lock_inode":True,
            "same_filesystem":True}


def validate_future_mounts(mounts: Sequence[Mapping[str,Any]],
                           *, dedicated_state: Path=DEDICATED_STATE) -> bool:
    """Fail on broad state/production credentials and any writable mount not reviewed.

    This is a narrow data-continuity attestor, not authority to grant provider
    secrets. Exact provider credential projection requires a separate approval.
    """
    if not isinstance(mounts,(list,tuple)):
        raise CoreCutoverDenied("CORE_MOUNTS_UNVERIFIED")
    expected = str(dedicated_state)
    found = 0
    for entry in mounts:
        if not isinstance(entry,Mapping):
            raise CoreCutoverDenied("CORE_MOUNT_NOT_OBJECT")
        dest = entry.get("Destination")
        src = entry.get("Source")
        if (not isinstance(dest,str) or not dest.startswith("/")
            or not isinstance(src,str) or not src.startswith("/")
            or ".." in Path(dest).parts or ".." in Path(src).parts
            or type(entry.get("RW")) is not bool):
            raise CoreCutoverDenied("CORE_MOUNT_PATH_UNTRUSTED")
        psrc,pdest = Path(src),Path(dest)
        if (src == str(LEGACY_STATE)
            or LEGACY_STATE in psrc.parents
            or dest == str(LEGACY_STATE)
            or LEGACY_STATE in pdest.parents
            or "/run/jason-secrets" in src
            or "/run/jason-secrets" in dest
            or "/var/run/docker.sock" in (src,dest)):
            raise CoreCutoverDenied("CORE_SHARED_STATE_OR_SECRETS_PROJECTION")
        if psrc == dedicated_state and pdest == dedicated_state:
            if entry.get("Type") != "bind" or entry["RW"] is not True:
                raise CoreCutoverDenied("CORE_DEDICATED_LEDGER_NOT_RW_BIND")
            found += 1
        else:
            # Even read-only credential mounts require an exact independent
            # signed provider projection. This is data/ownership acceptance,
            # not a shortcut to granting secrets to an external worker.
            raise CoreCutoverDenied("CORE_UNREVIEWED_MOUNT")
    if found != 1:
        raise CoreCutoverDenied("CORE_DEDICATED_LEDGER_MOUNT_REQUIRED")
    return True


def read_scan_evidence(db: Path, *, max_rows: int=3) -> dict[str,Any]:
    """Read only aggregate cycle totals, never tickets, titles, notes or credentials."""
    if not isinstance(max_rows,int) or not 2 <= max_rows <= 10:
        raise CoreCutoverDenied("CORE_SCAN_BUDGET_INVALID")
    if db.is_symlink() or not db.is_file():
        raise CoreCutoverDenied("CORE_LEDGER_NOT_READABLE")
    try:
        conn = sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=3)
        try:
            conn.execute("PRAGMA query_only=ON")
            rows = conn.execute(
                "SELECT scanned_at,provider_items,duplicate_items,evaluated "
                "FROM autonomy_ticket_scan_cycle ORDER BY scanned_at DESC LIMIT ?",
                (max_rows,)
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise CoreCutoverDenied("CORE_DURABLE_SCAN_READ_FAILED") from exc
    if (len(rows)<2 or any(not isinstance(t,str) or not t
        or type(count) is not int or count<=0
        or type(duplicate) is not int or duplicate!=0
        or type(evaluated) is not int or evaluated<=0
        for t,count,duplicate,evaluated in rows)
        or len({r[0] for r in rows})!=len(rows)):
        raise CoreCutoverDenied("CORE_SCAN_CONTINUITY_NOT_PROVEN")
    return {"cycle_count":len(rows),"distinct_cycle_count":len(rows),
            "duplicate_items":0,"minimum_evaluated":min(r[3] for r in rows),
            "customer_data_included":False}


def observe_legacy_baseline() -> dict[str,Any]:
    """Production observation only. The broad legacy DB location is a NO-GO for C."""
    ledger = identity(OLD_LEDGER)
    lock = identity(OLD_LEDGER.with_name(OLD_LEDGER.name+".owner.lock"))
    return {
        "status":"read_only_baseline_verified",
        "phase":"C-before",
        "ledger_owner_uid":ledger.uid,
        "owner_lock_owner_uid":lock.uid,
        "ledger_and_lock_same_filesystem":ledger.device==lock.device,
        "scan_evidence":read_scan_evidence(OLD_LEDGER),
        "external_cutover_authorized":False,
        "external_cutover_ready":False,
        "blocker":"dedicated_data_and_credential_projection_not_governed_or_installed",
        "production_mutations":False,
    }


if __name__ == "__main__":
    print(json.dumps(observe_legacy_baseline(),sort_keys=True))
