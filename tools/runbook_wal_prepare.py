#!/usr/bin/env python3
"""Prepare SQLite WAL sidecars using an explicitly read-only database handle."""
from __future__ import annotations
import ctypes
import os
from pathlib import Path
import stat

REGISTRY = Path("/var/lib/jason/openclaw/json-playbooks.sqlite3")
SQLITE_OPEN_READONLY = 1
SQLITE_FCNTL_PERSIST_WAL = 10


def trusted_file(path: Path) -> None:
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_nlink != 1 or info.st_mode & 0o077):
        raise RuntimeError("RUNBOOK_WAL_UNTRUSTED_FILE")


def prepare(path: Path) -> None:
    if not path.is_absolute() or path.parent.is_symlink():
        raise RuntimeError("RUNBOOK_WAL_UNTRUSTED_PATH")
    parent = path.parent.stat()
    if parent.st_uid != os.geteuid() or parent.st_mode & 0o022:
        raise RuntimeError("RUNBOOK_WAL_UNTRUSTED_DIRECTORY")
    trusted_file(path)
    sidecars = [Path(str(path) + suffix) for suffix in ("-wal", "-shm")]
    for sidecar in sidecars:
        if os.path.lexists(sidecar):
            trusted_file(sidecar)
    with path.open("rb") as f:
        header = f.read(100)
    if header[:16] != b"SQLite format 3\x00" or header[18:20] != b"\x02\x02":
        raise RuntimeError("RUNBOOK_WAL_MODE_REQUIRED")
    lib = ctypes.CDLL("libsqlite3.so.0")
    lib.sqlite3_open_v2.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p),
                                   ctypes.c_int, ctypes.c_char_p]
    lib.sqlite3_exec.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p,
                                 ctypes.c_void_p, ctypes.c_void_p]
    lib.sqlite3_file_control.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                                        ctypes.c_int, ctypes.c_void_p]
    lib.sqlite3_close.argtypes = [ctypes.c_void_p]
    db = ctypes.c_void_p()
    try:
        if lib.sqlite3_open_v2(os.fsencode(path), ctypes.byref(db), SQLITE_OPEN_READONLY, None):
            raise RuntimeError("RUNBOOK_WAL_OPEN_FAILED")
        flag = ctypes.c_int(1)
        if lib.sqlite3_file_control(db, b"main", SQLITE_FCNTL_PERSIST_WAL, ctypes.byref(flag)):
            raise RuntimeError("RUNBOOK_WAL_PERSIST_FAILED")
        if lib.sqlite3_exec(db, b"PRAGMA query_only=ON; SELECT count(*) FROM sqlite_master;",
                            None, None, None):
            raise RuntimeError("RUNBOOK_WAL_READ_FAILED")
    finally:
        if db.value and lib.sqlite3_close(db):
            raise RuntimeError("RUNBOOK_WAL_CLOSE_FAILED")
    for sidecar in sidecars:
        trusted_file(sidecar)


if __name__ == "__main__":
    os.umask(0o077)
    prepare(REGISTRY)
    print("RUNBOOK_WAL_PREPARE=PASS")
