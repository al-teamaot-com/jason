"""Source-only policy for a separately governed SQLite WAL health-sandbox repair.

This module ONLY renders and validates intended unit overlay bytes. It never
installs a drop-in, restarts a unit, resets a breaker, or consumes approval.
Root admission and isolated systemd acceptance are separate mandatory steps.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

ACTIVE = Path("/var/lib/jason/governed-ticket-shared/orchestration-events.sqlite3")
ROOT = ACTIVE.parent
DROPIN_NAME = "96-audit-journal-wal-health.conf"
UNITS = (
    "jason-openclaw-authority-health.service",
    "jason-openclaw-authority-full-integrity.service",
)
SIBLING_DBS = (
    "governed-execution.sqlite3",
    "model-usage.sqlite3",
    "reflection.sqlite3",
    "resolution-memory.sqlite3",
    "teams-identity-bindings.sqlite3",
)
NON_DB_ENTRY = "journal-work"


class SandboxPolicyError(RuntimeError):
    pass


def reviewed_inventory(directory: Path = ROOT, *, writer_uid: int = 1000) -> dict:
    """Fail closed if a newly encountered file could gain write access.

    This is a point-in-time preflight only. The production root executor must
    revalidate it inside the same protected transaction before installation.
    """
    info = directory.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != writer_uid
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise SandboxPolicyError("UNTRUSTED_JOURNAL_DIRECTORY")
    expected = {ACTIVE.name, *SIBLING_DBS, NON_DB_ENTRY}
    optional = {name + suffix
                for name in (ACTIVE.name, *SIBLING_DBS)
                for suffix in ("-wal", "-shm")}
    found = {p.name for p in directory.iterdir()}
    if not expected.issubset(found) or not found.issubset(expected | optional):
        raise SandboxPolicyError("UNKNOWN_JOURNAL_DIRECTORY_ENTRY")
    for name in (ACTIVE.name, *SIBLING_DBS):
        row = (directory / name).lstat()
        if (not stat.S_ISREG(row.st_mode) or row.st_uid != writer_uid
                or stat.S_IMODE(row.st_mode) != 0o600 or row.st_nlink != 1):
            raise SandboxPolicyError("UNTRUSTED_JOURNAL_DB_IDENTITY")
    special = (directory / NON_DB_ENTRY).lstat()
    if not stat.S_ISDIR(special.st_mode) or special.st_mode & 0o002:
        raise SandboxPolicyError("UNTRUSTED_JOURNAL_WORK_DIRECTORY")
    for name in found & optional:
        row = (directory / name).lstat()
        if (not stat.S_ISREG(row.st_mode) or row.st_uid != writer_uid
                or stat.S_IMODE(row.st_mode) != 0o600 or row.st_nlink != 1):
            raise SandboxPolicyError("UNTRUSTED_JOURNAL_AUX_IDENTITY")
    return {
        "active": str(directory / ACTIVE.name),
        "reviewed_entries": sorted(found),
        "writer_uid": writer_uid,
        "no_unknown_entries": True,
    }


def render_dropins() -> dict[str, bytes]:
    """Render only two owner-reviewable unit overlays; no live-system effects.

    SQLite requires creation of -wal/-shm on a clean WAL database. An optional
    file-only ReadWritePaths=-...-shm is insufficient when the file is absent.
    The directory exception is broader: keep all currently known DATA files
    read-only and prevent access to the internal journal work directory.
    This residual directory-creation ability requires explicit security review,
    an exact root inventory recheck, and real isolated systemd sandbox proof.
    """
    paths = [str(ACTIVE), "-" + str(ACTIVE) + "-wal"]
    for name in SIBLING_DBS:
        item = str(ROOT / name)
        paths.extend((item, "-" + item + "-wal", "-" + item + "-shm"))
    payload = (
        "[Service]\n"
        "# Temporary WAL auxiliary creation exception; existing DB files remain RO.\n"
        "ReadWritePaths=" + str(ROOT) + "\n"
        "ReadOnlyPaths=" + " ".join(paths) + "\n"
        "InaccessiblePaths=-" + str(ROOT / NON_DB_ENTRY) + "\n"
    ).encode("ascii")
    return {unit: payload for unit in UNITS}


if __name__ == "__main__":
    raise SystemExit("Source-only sandbox policy; root installation requires separate exact approval")
