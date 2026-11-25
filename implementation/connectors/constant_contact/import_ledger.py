"""Durable one-time import claim ledger, independent of process lifetime.

The database contains only immutable digests and provider activity IDs, never
contact records or OAuth credentials. Unknown POST outcomes stay claimed and
require explicit reconciliation rather than automatic redispatch.
"""
from __future__ import annotations

import json
import os
import sqlite3
import stat
import time
from pathlib import Path

from .import_authorization import ImportAuthorizationError


class SQLiteImportActivityLedger:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _connect(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise ImportAuthorizationError("Import ledger path cannot be a symlink")
        if self.path.exists() and (
            not self.path.is_file() or stat.S_IMODE(self.path.stat().st_mode) & 0o077
        ):
            raise ImportAuthorizationError("Import ledger permissions unsafe")
        con = sqlite3.connect(self.path, isolation_level=None, timeout=15)
        os.chmod(self.path, 0o600)
        con.execute(
            "CREATE TABLE IF NOT EXISTS claims("
            "intent_digest TEXT PRIMARY KEY,"
            "claimed_at INTEGER NOT NULL,"
            "activity_id TEXT,"
            "state TEXT NOT NULL CHECK(state IN ('pending','dispatched')))"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS verifications("
            "intent_digest TEXT PRIMARY KEY, activity_id TEXT NOT NULL,"
            "verified_at INTEGER NOT NULL, result_json TEXT NOT NULL)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS terminal_failures("
            "intent_digest TEXT PRIMARY KEY, activity_id TEXT NOT NULL,"
            "failed_at INTEGER NOT NULL, reason TEXT NOT NULL)"
        )
        return con

    @staticmethod
    def _check_digest(digest: str) -> None:
        if not isinstance(digest, str) or len(digest) != 64 or any(
            c not in "0123456789abcdef" for c in digest
        ):
            raise ImportAuthorizationError("Invalid immutable import digest")

    def claim_once(self, *, intent_digest: str) -> None:
        self._check_digest(intent_digest)
        try:
            with self._connect() as con:
                con.execute("BEGIN IMMEDIATE")
                con.execute(
                    "INSERT INTO claims(intent_digest, claimed_at, state) VALUES (?, ?, 'pending')",
                    (intent_digest, int(time.time())),
                )
                con.execute("COMMIT")
        except sqlite3.IntegrityError:
            raise ImportAuthorizationError(
                "Import already claimed; require provider reconciliation"
            ) from None

    def record_dispatched(self, *, intent_digest: str, activity_id: str) -> None:
        self._check_digest(intent_digest)
        if not isinstance(activity_id, str) or len(activity_id) != 36:
            raise ImportAuthorizationError("Invalid import activity ID")
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            cursor = con.execute(
                "UPDATE claims SET activity_id = ?, state = 'dispatched' "
                "WHERE intent_digest = ? AND state = 'pending'",
                (activity_id, intent_digest),
            )
            if cursor.rowcount != 1:
                con.execute("ROLLBACK")
                raise ImportAuthorizationError("Import claim missing or already dispatched")
            con.execute("COMMIT")

    def read_claim(self, *, intent_digest: str) -> dict[str, object] | None:
        self._check_digest(intent_digest)
        with self._connect() as con:
            row = con.execute(
                "SELECT state, activity_id, claimed_at FROM claims WHERE intent_digest = ?",
                (intent_digest,),
            ).fetchone()
        if row is None:
            return None
        return {"state": row[0], "activity_id": row[1], "claimed_at": row[2]}


    def record_verified(self, *, intent_digest: str, activity_id: str,
                        item_results: tuple[dict[str, str], ...]) -> None:
        """Durably record only successful provider readback; no raw emails."""
        self._check_digest(intent_digest)
        if (not isinstance(activity_id, str) or len(activity_id) != 36
                or not 1 <= len(item_results) <= 25
                or any(set(row) != {"email_sha256", "status"}
                       or row.get("status") != "verified"
                       or not isinstance(row.get("email_sha256"), str)
                       or len(row["email_sha256"]) != 64 for row in item_results)):
            raise ImportAuthorizationError("Verified import evidence incomplete")
        evidence = json.dumps(
            list(item_results), sort_keys=True, separators=(",", ":")
        )
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT state,activity_id FROM claims WHERE intent_digest=?",
                (intent_digest,),
            ).fetchone()
            if row is None or row != ("dispatched", activity_id):
                raise ImportAuthorizationError("Import dispatch receipt missing or changed")
            prior = db.execute(
                "SELECT activity_id,result_json FROM verifications WHERE intent_digest=?",
                (intent_digest,),
            ).fetchone()
            if prior is not None:
                if prior != (activity_id, evidence):
                    raise ImportAuthorizationError("Import verification is immutable")
                db.execute("COMMIT")
                return
            db.execute(
                "INSERT INTO verifications VALUES (?,?,?,?)",
                (intent_digest, activity_id, int(time.time()), evidence),
            )
            db.execute("COMMIT")

    def read_verification(self, *, intent_digest: str) -> dict[str, object] | None:
        self._check_digest(intent_digest)
        with self._connect() as db:
            row = db.execute(
                "SELECT activity_id,verified_at,result_json FROM verifications "
                "WHERE intent_digest=?",
                (intent_digest,),
            ).fetchone()
        return ({
            "activity_id": row[0], "verified_at": row[1],
            "item_results": json.loads(row[2]),
        } if row else None)

    def record_provider_failure(self, *, intent_digest: str, activity_id: str) -> None:
        """Persist only a confirmed provider-reported terminal failure, never a timeout."""
        self._check_digest(intent_digest)
        if not isinstance(activity_id, str) or len(activity_id) != 36:
            raise ImportAuthorizationError("Invalid terminal failure receipt")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            claim = db.execute(
                "SELECT state,activity_id FROM claims WHERE intent_digest=?",
                (intent_digest,),
            ).fetchone()
            if claim != ("dispatched", activity_id):
                raise ImportAuthorizationError("Terminal failure has no dispatched activity")
            if db.execute(
                "SELECT 1 FROM verifications WHERE intent_digest=?", (intent_digest,),
            ).fetchone():
                raise ImportAuthorizationError("Verified import cannot become failed")
            existing = db.execute(
                "SELECT activity_id,reason FROM terminal_failures WHERE intent_digest=?",
                (intent_digest,),
            ).fetchone()
            if existing:
                if existing != (activity_id, "provider_activity_failed"):
                    raise ImportAuthorizationError("Terminal provider failure is immutable")
            else:
                db.execute(
                    "INSERT INTO terminal_failures VALUES (?,?,?,?)",
                    (intent_digest, activity_id, int(time.time()), "provider_activity_failed"),
                )
            db.execute("COMMIT")

    def read_provider_failure(self, *, intent_digest: str) -> dict[str, object] | None:
        self._check_digest(intent_digest)
        with self._connect() as db:
            row = db.execute(
                "SELECT activity_id,failed_at,reason FROM terminal_failures "
                "WHERE intent_digest=?", (intent_digest,),
            ).fetchone()
        return ({"activity_id": row[0], "failed_at": row[1], "reason": row[2]}
                if row else None)
