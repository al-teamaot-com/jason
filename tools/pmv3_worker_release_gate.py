#!/usr/bin/env python3
"""Fail-closed systemd ExecCondition for release/worker mutual exclusion.

Exit 0 permits a normal engineering start; exit 1 instructs systemd to skip
ExecStart without declaring a service failure. No protected file is modified.
"""
from __future__ import annotations

import fcntl
import os
import stat
from pathlib import Path

PRODUCTION_LOCK = Path('/var/lib/jason/openclaw/release-manager/production-transaction.lock')


def admission_allowed(path: Path = PRODUCTION_LOCK) -> bool:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0)
                     | getattr(os, 'O_NOFOLLOW', 0)
                     | getattr(os, 'O_CLOEXEC', 0))
    except OSError:
        return False
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_mode & 0o002):
            return False
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except OSError:
            return False
        try:
            return True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def main() -> int:
    return 0 if admission_allowed() else 1


if __name__ == '__main__':
    raise SystemExit(main())
