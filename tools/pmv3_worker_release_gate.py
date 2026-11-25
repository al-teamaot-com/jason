#!/usr/bin/env python3
"""Fail-closed systemd ExecCondition for release/worker mutual exclusion.

The legacy/default check is instantaneous. The system-managed engineering
worker alone opts into bounded contention retry. An unavailable or untrusted
lock, owner pause, or exhausted budget still denies work. No protected file
is modified and no shared lock is held across engineering execution.
"""
from __future__ import annotations

import argparse
import fcntl
import os
import stat
import time
from pathlib import Path

PRODUCTION_LOCK = Path('/var/lib/jason/openclaw/release-manager/production-transaction.lock')
OWNER_PAUSE = Path('/var/lib/jason/openclaw/support-repair/pmv3-engineering-owner-pause.json')
RETRY_SECONDS = 20.0
INITIAL_BACKOFF_SECONDS = 0.25
MAX_BACKOFF_SECONDS = 2.0


def pause_clear(path: Path | None) -> bool:
    if path is None:
        return True
    try:
        path.lstat()
    except FileNotFoundError:
        return True
    except OSError:
        pass
    return False


def probe(path: Path, pause_path: Path | None = None) -> str:
    if not pause_clear(pause_path):
        return 'paused'
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0)
                     | getattr(os, 'O_NOFOLLOW', 0)
                     | getattr(os, 'O_CLOEXEC', 0))
    except OSError:
        return 'unavailable'
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_mode & 0o002):
            return 'untrusted'
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return 'busy'
        except OSError:
            return 'unavailable'
        # Never accept an inode that was unlinked or replaced during the probe.
        current = path.lstat()
        if ((current.st_dev, current.st_ino) != (info.st_dev, info.st_ino)
                or not stat.S_ISREG(current.st_mode)
                or current.st_uid != os.getuid() or current.st_mode & 0o002):
            return 'untrusted'
        return 'allowed' if pause_clear(pause_path) else 'paused'
    except OSError:
        return 'unavailable'
    finally:
        os.close(fd)


def admission_status(path: Path = PRODUCTION_LOCK, *, retry_seconds: float = 0.0,
                     pause_path: Path | None = None) -> str:
    # Only the explicitly configured bounded engineering policy can wait.
    if not 0 <= retry_seconds <= RETRY_SECONDS:
        raise ValueError('invalid release-gate retry budget')
    deadline = time.monotonic() + retry_seconds
    delay = INITIAL_BACKOFF_SECONDS
    result = probe(path, pause_path)
    while result == 'busy':
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(delay, remaining))
        if time.monotonic() >= deadline:
            break
        result = probe(path, pause_path)
        delay = min(delay * 2, MAX_BACKOFF_SECONDS)
    return result


def admission_allowed(path: Path = PRODUCTION_LOCK, *, retry_seconds: float = 0.0,
                      pause_path: Path | None = None) -> bool:
    return admission_status(path, retry_seconds=retry_seconds,
                            pause_path=pause_path) == 'allowed'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--retry-contention', action='store_true',
                        help='bounded engineering contention retry with owner pause recheck')
    args = parser.parse_args()
    start = time.monotonic()
    result = admission_status(
        retry_seconds=RETRY_SECONDS if args.retry_contention else 0.0,
        pause_path=OWNER_PAUSE if args.retry_contention else None,
    )
    print('PMV3_RELEASE_GATE status=' + result
          + ' elapsed_ms=' + str(round((time.monotonic() - start) * 1000)),
          flush=True)
    return 0 if result == 'allowed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
