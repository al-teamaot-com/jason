"""One-host, cross-container ownership of the canonical ticket worker ledger.

This lock protects *dispatch ownership* during a future governed migration.
It is independent of PM engineering/release locks and MUST be held for the
whole ticket-worker supervisor lifetime. The persistent lockfile is never
unlinked, which prevents competing processes from locking different inodes.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat
from typing import Iterator


class TicketWorkerOwnershipError(RuntimeError):
    """Ticket worker cannot safely claim the exclusive dispatch lifecycle."""


def ticket_worker_lock_path(work_db: Path) -> Path:
    path = Path(work_db)
    if not path.is_absolute() or ".." in path.parts or not path.name:
        raise TicketWorkerOwnershipError("TICKET_CORE_DB_PATH_UNTRUSTED")
    if path.is_symlink():
        raise TicketWorkerOwnershipError("TICKET_CORE_DB_SYMLINK")
    return path.with_name(path.name + ".owner.lock")


@contextmanager
def exclusive_ticket_worker_owner(work_db: Path) -> Iterator[Path]:
    """Hold one nonblocking kernel flock across the embedded/external split.

    Both eligible service modes must use the exact same mounted SQLite path.
    The source-only migration requires upgrading the embedded owner before
    external activation; the legacy production worker cannot be assumed to
    honor a lock introduced by this revision.
    """
    path = ticket_worker_lock_path(work_db)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise TicketWorkerOwnershipError("TICKET_CORE_LEDGER_DIRECTORY_MISSING")
    fd = None
    try:
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_CLOEXEC", 0)
        fd = os.open(path, flags, 0o600)
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise TicketWorkerOwnershipError("TICKET_CORE_LOCK_FILE_UNTRUSTED")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise TicketWorkerOwnershipError("TICKET_CORE_WORKER_ALREADY_OWNED") from exc
        yield path
    except OSError as exc:
        raise TicketWorkerOwnershipError("TICKET_CORE_LOCK_UNAVAILABLE") from exc
    finally:
        if fd is not None:
            # Never remove the path: unlinking would allow split-brain owners.
            os.close(fd)
