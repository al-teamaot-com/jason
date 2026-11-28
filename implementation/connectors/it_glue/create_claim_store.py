"""Durable single-dispatch IT Glue creation claim store.

Stores only opaque SHA-256 digests and attempt timestamps. An ambiguous POST
is never automatically retried; provider reconciliation is a distinct workflow.
"""
from __future__ import annotations

import os
import sqlite3
import stat
import time
from pathlib import Path


class SQLiteItGlueCreationClaimStore:
    def __init__(self, database_path: str | Path):
        self.path = Path(database_path)

    @staticmethod
    def _digest(value: str) -> bool:
        return (isinstance(value, str) and len(value) == 64
                and all(c in "0123456789abcdef" for c in value))

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # sqlite3.connect creates files with the process umask (often 0644).
        # With concurrent first writers, another worker could inspect the new
        # DB before chmod and spuriously deny it. Create a mode-0600 inode
        # atomically before any connection; never weaken an existing mode.
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        flags |= getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_CLOEXEC", 0)
        try:
            fd = os.open(self.path, flags, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        mode = os.lstat(self.path)
        if stat.S_ISLNK(mode.st_mode):
            raise PermissionError("IT_GLUE_CLAIM_PATH_SYMLINK")
        if (not stat.S_ISREG(mode.st_mode) or
                mode.st_uid != os.geteuid() or
                stat.S_IMODE(mode.st_mode) & 0o077):
            raise PermissionError("IT_GLUE_CLAIM_PERMISSIONS_UNSAFE")
        connection = sqlite3.connect(self.path, isolation_level=None, timeout=15)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS itglue_create_claims("
            "intent_sha256 TEXT PRIMARY KEY, payload_sha256 TEXT NOT NULL,"
            "claimed_at INTEGER NOT NULL, state TEXT NOT NULL "
            "CHECK (state IN ('claimed', 'verified', 'needs_reconciliation')))"
        )
        return connection

    def claim_once(self, *, key: str, payload_sha256: str) -> bool:
        if not self._digest(key) or not self._digest(payload_sha256):
            raise ValueError("IT_GLUE_CLAIM_DIGEST_INVALID")
        with self._connect() as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    "INSERT INTO itglue_create_claims"
                    "(intent_sha256,payload_sha256,claimed_at,state) "
                    "VALUES(?,?,?,'claimed')",
                    (key, payload_sha256, int(time.time())),
                )
                db.execute("COMMIT")
            except sqlite3.IntegrityError:
                db.execute("ROLLBACK")
                return False
        return True

    def mark_verified(self, *, key: str, payload_sha256: str) -> None:
        if not self._digest(key) or not self._digest(payload_sha256):
            raise ValueError("IT_GLUE_CLAIM_DIGEST_INVALID")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            outcome = db.execute(
                "UPDATE itglue_create_claims SET state='verified' "
                "WHERE intent_sha256=? AND payload_sha256=? "
                "AND state IN ('claimed','verified')",
                (key, payload_sha256),
            )
            if outcome.rowcount != 1:
                db.execute("ROLLBACK")
                raise PermissionError("IT_GLUE_CLAIM_VERIFICATION_MISMATCH")
            db.execute("COMMIT")

    def status(self, *, key: str) -> str | None:
        if not self._digest(key):
            raise ValueError("IT_GLUE_CLAIM_DIGEST_INVALID")
        with self._connect() as db:
            row = db.execute(
                "SELECT state FROM itglue_create_claims WHERE intent_sha256=?",
                (key,),
            ).fetchone()
        return row[0] if row else None
