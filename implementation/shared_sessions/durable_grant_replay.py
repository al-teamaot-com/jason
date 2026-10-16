"""Durable, transactional one-use receipt store (offline engineering prototype).

The caller MUST authenticate cryptographic grants before using this store.
This store alone never grants permission, sends Teams approvals, or executes.
"""
from __future__ import annotations
from pathlib import Path
import re
import sqlite3

_HEX = re.compile(r'^[0-9a-f]{64}$')

class SqliteGrantReplayStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path == ':memory:':
            raise ValueError('persistent replay store requires on-disk database')
        with self._connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS grant_receipts (
                token_digest TEXT NOT NULL PRIMARY KEY,
                state TEXT NOT NULL CHECK(state IN ('used','revoked')),
                exp INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )''')

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.execute('PRAGMA busy_timeout=10000')
        return db

    @staticmethod
    def _validate(token_digest: str, exp: int, now: int) -> None:
        if type(token_digest) is not str or not _HEX.fullmatch(token_digest):
            raise ValueError('invalid signed token digest')
        if type(exp) is not int or type(now) is not int or exp <= 0 or now < 0:
            raise ValueError('invalid clock or expiry')

    def consume(self, *, token_digest: str, exp: int, now: int) -> bool:
        self._validate(token_digest,exp,now)
        if now >= exp:
            return False
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT state FROM grant_receipts WHERE token_digest=?',
                                  (token_digest,)).fetchone()
            if existing is not None:
                return False
            db.execute('INSERT INTO grant_receipts VALUES (?,?,?,?)',
                       (token_digest,'used',exp,now))
            return True

    def revoke(self, *, token_digest: str, exp: int, now: int) -> bool:
        self._validate(token_digest,exp,now)
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT state FROM grant_receipts WHERE token_digest=?',
                                  (token_digest,)).fetchone()
            if existing is not None:
                return existing[0] == 'revoked'
            db.execute('INSERT INTO grant_receipts VALUES (?,?,?,?)',
                       (token_digest,'revoked',exp,now))
            return True

    def status(self, token_digest: str) -> str | None:
        if type(token_digest) is not str or not _HEX.fullmatch(token_digest):
            raise ValueError('invalid digest')
        with self._connect() as db:
            row = db.execute('SELECT state FROM grant_receipts WHERE token_digest=?',
                             (token_digest,)).fetchone()
        return row[0] if row else None
