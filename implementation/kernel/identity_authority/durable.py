from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .contracts import (
    ApprovalRecord,
    AuthorityGrant,
    ExecutionContext,
    IdentityRecord,
    PermissionMode,
    AuthorityOutcome,
)


_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS identities (
  identity_id TEXT PRIMARY KEY,
  payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS authority_grants (
  grant_id TEXT PRIMARY KEY,
  subject_id TEXT NOT NULL,
  payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_authority_grants_subject
  ON authority_grants(subject_id);
CREATE TABLE IF NOT EXISTS approvals (
  approval_id TEXT PRIMARY KEY,
  payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS execution_contexts (
  context_id TEXT PRIMARY KEY,
  payload TEXT NOT NULL,
  revoked_at TEXT,
  revoked_reason TEXT
);
CREATE TABLE IF NOT EXISTS authority_audit (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  correlation_id TEXT NOT NULL,
  principal_id TEXT NOT NULL,
  organization_id TEXT NOT NULL,
  capability TEXT NOT NULL,
  outcome TEXT NOT NULL,
  reason_codes TEXT NOT NULL,
  occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def _encode(value: Any) -> str:
    def default(item: Any) -> Any:
        if isinstance(item, datetime):
            return item.isoformat()
        if hasattr(item, "value"):
            return item.value
        raise TypeError(type(item).__name__)
    return json.dumps(asdict(value), default=default, sort_keys=True, separators=(",", ":"))


def _dt(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


class SQLiteIdentityAuthorityStore:
    """Durable local pilot store for JKD-001 state and authority audit."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.path))
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(_SCHEMA)
        self.connection.commit()
        os.chmod(self.path, 0o600)

    def close(self) -> None:
        self.connection.close()

    def put_identity(self, record: IdentityRecord) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO identities(identity_id,payload) VALUES (?,?)",
                (record.identity_id, _encode(record)),
            )

    def get_identity(self, identity_id: str) -> IdentityRecord | None:
        row = self.connection.execute(
            "SELECT payload FROM identities WHERE identity_id=?", (identity_id,)
        ).fetchone()
        if row is None:
            return None
        p = json.loads(row["payload"])
        return IdentityRecord(**p)

    def put_grant(self, record: AuthorityGrant) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO authority_grants(grant_id,subject_id,payload) VALUES (?,?,?)",
                (record.grant_id, record.subject_id, _encode(record)),
            )

    def list_grants_for_subject(self, subject_id: str) -> tuple[AuthorityGrant, ...]:
        rows = self.connection.execute(
            "SELECT payload FROM authority_grants WHERE subject_id=? ORDER BY grant_id",
            (subject_id,),
        ).fetchall()
        result = []
        for row in rows:
            p = json.loads(row["payload"])
            p["permission"] = PermissionMode(p["permission"])
            p["effective_from"] = _dt(p.get("effective_from"))
            p["effective_until"] = _dt(p.get("effective_until"))
            result.append(AuthorityGrant(**p))
        return tuple(result)

    def put_approval(self, record: ApprovalRecord) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO approvals(approval_id,payload) VALUES (?,?)",
                (record.approval_id, _encode(record)),
            )

    def get_approval(self, approval_id: str) -> ApprovalRecord | None:
        row = self.connection.execute(
            "SELECT payload FROM approvals WHERE approval_id=?", (approval_id,)
        ).fetchone()
        if row is None:
            return None
        p = json.loads(row["payload"])
        p["decided_at"] = _dt(p.get("decided_at"))
        p["expires_at"] = _dt(p.get("expires_at"))
        return ApprovalRecord(**p)

    def put_context(self, context: ExecutionContext) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO execution_contexts(context_id,payload,revoked_at,revoked_reason) VALUES (?,?,NULL,NULL)",
                (context.context_id, _encode(context)),
            )

    def get_context(self, context_id: str) -> ExecutionContext | None:
        row = self.connection.execute(
            "SELECT payload FROM execution_contexts WHERE context_id=?", (context_id,)
        ).fetchone()
        if row is None:
            return None
        p = json.loads(row["payload"])
        p["requested_mode"] = PermissionMode(p["requested_mode"])
        p["maximum_mode"] = PermissionMode(p["maximum_mode"])
        p["outcome"] = AuthorityOutcome(p["outcome"])
        p["matched_grants"] = tuple(p["matched_grants"])
        p["issued_at"] = datetime.fromisoformat(p["issued_at"])
        p["expires_at"] = datetime.fromisoformat(p["expires_at"])
        return ExecutionContext(**p)

    def revoke_context(self, context_id: str, *, revoked_at: datetime, reason: str) -> bool:
        if revoked_at.tzinfo is None or not reason.strip():
            raise ValueError("revocation requires timezone-aware time and reason")
        with self.connection:
            cursor = self.connection.execute(
                "UPDATE execution_contexts SET revoked_at=?, revoked_reason=? WHERE context_id=? AND revoked_at IS NULL",
                (revoked_at.isoformat(), reason, context_id),
            )
        return cursor.rowcount == 1

    def context_revocation(self, context_id: str) -> tuple[datetime, str] | None:
        row = self.connection.execute(
            "SELECT revoked_at,revoked_reason FROM execution_contexts WHERE context_id=?",
            (context_id,),
        ).fetchone()
        if row is None or row["revoked_at"] is None:
            return None
        return datetime.fromisoformat(row["revoked_at"]), str(row["revoked_reason"])

    def append_authority_audit(
        self,
        *,
        event_type: str,
        correlation_id: str,
        principal_id: str,
        organization_id: str,
        capability: str,
        outcome: str,
        reason_codes: tuple[str, ...],
    ) -> None:
        with self.connection:
            self.connection.execute(
                """INSERT INTO authority_audit(event_type,correlation_id,principal_id,organization_id,capability,outcome,reason_codes)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    event_type, correlation_id, principal_id, organization_id,
                    capability, outcome, json.dumps(reason_codes),
                ),
            )
