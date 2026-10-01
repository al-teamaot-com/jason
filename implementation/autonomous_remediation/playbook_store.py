"""Durable hot-load registry for validated JSON playbooks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from .playbook_document import (
    PlaybookDocument,
    PlaybookValidationError,
    validate_playbook_document,
)


@dataclass(frozen=True, slots=True)
class StoredPlaybook:
    document: PlaybookDocument
    state: str
    created_by: str
    created_at: str
    activated_by: str | None = None
    activated_at: str | None = None


class SQLitePlaybookRegistry:
    """Versioned playbook data store.

    Definitions live in durable runtime data instead of the application image.
    Staging or activating a definition therefore does not require a Jason rebuild
    or process restart. Activation is a registry state transition only; it creates
    no execution authority.
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS json_playbooks (
        playbook_id TEXT NOT NULL,
        version TEXT NOT NULL,
        state TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        canonical_json TEXT NOT NULL,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        activated_by TEXT,
        activated_at TEXT,
        retired_at TEXT,
        PRIMARY KEY(playbook_id, version)
    );
    CREATE UNIQUE INDEX IF NOT EXISTS ux_json_playbook_active
      ON json_playbooks(playbook_id)
      WHERE state='active';
    CREATE TABLE IF NOT EXISTS json_playbook_registry_meta (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1),
        generation INTEGER NOT NULL
    );
    INSERT OR IGNORE INTO json_playbook_registry_meta(singleton,generation)
      VALUES(1,0);
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            str(self.path), timeout=10.0, isolation_level=None
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.executescript(self._SCHEMA)
        os.chmod(self.path, 0o600)

    def stage(
        self,
        payload: Mapping[str, Any],
        *,
        actor: str,
        known_capabilities: set[str] | frozenset[str] | None = None,
    ) -> StoredPlaybook:
        principal = str(actor or "").strip()
        if not principal:
            raise ValueError("PLAYBOOK_STAGE_ACTOR_REQUIRED")
        document = validate_playbook_document(
            payload,
            known_capabilities=known_capabilities,
        )
        existing = self._connection.execute(
            "SELECT * FROM json_playbooks WHERE playbook_id=? AND version=?",
            (document.playbook_id, document.version),
        ).fetchone()
        if existing is not None:
            if str(existing["fingerprint"]) != document.fingerprint:
                raise ValueError("PLAYBOOK_VERSION_IMMUTABLE")
            return self._row(existing)

        now = datetime.now(timezone.utc).isoformat()
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO json_playbooks(
                    playbook_id,version,state,fingerprint,canonical_json,
                    created_by,created_at,activated_by,activated_at,retired_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    document.playbook_id,
                    document.version,
                    "draft",
                    document.fingerprint,
                    document.canonical_json,
                    principal,
                    now,
                    None,
                    None,
                    None,
                ),
            )
            self._bump_generation()
        return self.get(document.playbook_id, document.version)

    def activate(
        self,
        playbook_id: str,
        version: str,
        *,
        actor: str,
        expected_fingerprint: str | None = None,
    ) -> StoredPlaybook:
        principal = str(actor or "").strip()
        if not principal:
            raise ValueError("PLAYBOOK_ACTIVATE_ACTOR_REQUIRED")
        current = self.get(playbook_id, version)
        if expected_fingerprint and current.document.fingerprint != expected_fingerprint:
            raise ValueError("PLAYBOOK_ACTIVATION_FINGERPRINT_MISMATCH")
        if current.state == "active":
            return current
        now = datetime.now(timezone.utc).isoformat()
        with self._connection:
            self._connection.execute(
                """
                UPDATE json_playbooks
                   SET state='retired', retired_at=?
                 WHERE playbook_id=? AND state='active'
                """,
                (now, current.document.playbook_id),
            )
            self._connection.execute(
                """
                UPDATE json_playbooks
                   SET state='active', activated_by=?, activated_at=?, retired_at=NULL
                 WHERE playbook_id=? AND version=?
                """,
                (
                    principal,
                    now,
                    current.document.playbook_id,
                    current.document.version,
                ),
            )
            self._bump_generation()
        return self.get(current.document.playbook_id, current.document.version)

    def retire(self, playbook_id: str, *, actor: str) -> bool:
        if not str(actor or "").strip():
            raise ValueError("PLAYBOOK_RETIRE_ACTOR_REQUIRED")
        now = datetime.now(timezone.utc).isoformat()
        with self._connection:
            cursor = self._connection.execute(
                """
                UPDATE json_playbooks
                   SET state='retired', retired_at=?
                 WHERE playbook_id=? AND state='active'
                """,
                (now, str(playbook_id).strip()),
            )
            changed = cursor.rowcount > 0
            if changed:
                self._bump_generation()
        return changed

    def get(self, playbook_id: str, version: str) -> StoredPlaybook:
        row = self._connection.execute(
            "SELECT * FROM json_playbooks WHERE playbook_id=? AND version=?",
            (str(playbook_id).strip(), str(version).strip()),
        ).fetchone()
        if row is None:
            raise KeyError("PLAYBOOK_VERSION_NOT_FOUND")
        return self._row(row)

    def active(self, playbook_id: str) -> StoredPlaybook | None:
        row = self._connection.execute(
            "SELECT * FROM json_playbooks WHERE playbook_id=? AND state='active'",
            (str(playbook_id).strip(),),
        ).fetchone()
        return None if row is None else self._row(row)

    def list_all(self) -> tuple[StoredPlaybook, ...]:
        rows = self._connection.execute(
            "SELECT * FROM json_playbooks ORDER BY playbook_id,version"
        ).fetchall()
        return tuple(self._row(row) for row in rows)

    def active_snapshot(self) -> tuple[int, tuple[StoredPlaybook, ...]]:
        rows = self._connection.execute(
            "SELECT * FROM json_playbooks WHERE state='active' ORDER BY playbook_id"
        ).fetchall()
        return self.generation(), tuple(self._row(row) for row in rows)

    def generation(self) -> int:
        row = self._connection.execute(
            "SELECT generation FROM json_playbook_registry_meta WHERE singleton=1"
        ).fetchone()
        return int(row["generation"])

    def close(self) -> None:
        self._connection.close()

    def _bump_generation(self) -> None:
        self._connection.execute(
            "UPDATE json_playbook_registry_meta SET generation=generation+1 WHERE singleton=1"
        )

    @staticmethod
    def _summary(row: sqlite3.Row) -> Mapping[str, Any]:
        return {
            "playbook_id": str(row["playbook_id"]),
            "version": str(row["version"]),
            "state": str(row["state"]),
            "fingerprint": str(row["fingerprint"]),
            "created_by": str(row["created_by"]),
            "created_at": str(row["created_at"]),
            "activated_by": (
                str(row["activated_by"]) if row["activated_by"] is not None else None
            ),
            "activated_at": (
                str(row["activated_at"]) if row["activated_at"] is not None else None
            ),
        }

    @classmethod
    def summary(cls, stored: StoredPlaybook) -> Mapping[str, Any]:
        return {
            "playbook_id": stored.document.playbook_id,
            "name": stored.document.name,
            "version": stored.document.version,
            "lifecycle": stored.document.lifecycle,
            "target_type": stored.document.target_type,
            "state": stored.state,
            "fingerprint": stored.document.fingerprint,
            "capabilities": list(stored.document.capabilities),
            "autonomy_activation": stored.document.autonomy_activation,
            "created_by": stored.created_by,
            "created_at": stored.created_at,
            "activated_by": stored.activated_by,
            "activated_at": stored.activated_at,
        }

    def _row(self, row: sqlite3.Row) -> StoredPlaybook:
        payload = json.loads(str(row["canonical_json"]))
        document = validate_playbook_document(payload)
        if document.fingerprint != str(row["fingerprint"]):
            raise RuntimeError("PLAYBOOK_REGISTRY_FINGERPRINT_CORRUPT")
        return StoredPlaybook(
            document=document,
            state=str(row["state"]),
            created_by=str(row["created_by"]),
            created_at=str(row["created_at"]),
            activated_by=(
                str(row["activated_by"]) if row["activated_by"] is not None else None
            ),
            activated_at=(
                str(row["activated_at"]) if row["activated_at"] is not None else None
            ),
        )
