from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4


_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    client_id TEXT NOT NULL,
    request_id TEXT,
    state TEXT NOT NULL,
    case_document TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_cases_client_created ON cases(client_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS ux_cases_correlation ON cases(correlation_id);

CREATE TABLE IF NOT EXISTS reasoning_results (
    result_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id),
    result_document TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outcomes (
    outcome_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES cases(case_id),
    outcome_document TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workflow_transitions (
    transition_id TEXT PRIMARY KEY,
    case_id TEXT,
    correlation_id TEXT NOT NULL,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    reason TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_transitions_correlation ON workflow_transitions(correlation_id, occurred_at);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    correlation_id TEXT,
    case_id TEXT,
    client_id TEXT,
    payload TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_audit_correlation ON audit_events(correlation_id, occurred_at);
CREATE INDEX IF NOT EXISTS ix_audit_client ON audit_events(client_id, occurred_at);
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class SQLitePilotStore:
    """Durable pilot store implementing memory and append-only audit providers.

    SQLite is intentionally used for the local/historical pilot. The canonical
    production target remains PostgreSQL; an equivalent DDL file lives under db/.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(path))
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(_SCHEMA)
        self._connection.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self._connection
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def record_case(self, case_package: dict[str, Any]) -> None:
        now = _utcnow()
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO cases(case_id, correlation_id, client_id, request_id, state, case_document, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(case_id) DO UPDATE SET
                    state=excluded.state,
                    case_document=excluded.case_document,
                    updated_at=excluded.updated_at
                """,
                (
                    case_package["case_id"],
                    case_package["correlation_id"],
                    case_package["client_id"],
                    case_package.get("request_id"),
                    case_package.get("state", "case_normalized"),
                    _json(case_package),
                    now,
                    now,
                ),
            )

    def record_result(self, reasoning_result: dict[str, Any]) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO reasoning_results(result_id, case_id, result_document, created_at) VALUES (?, ?, ?, ?)",
                (str(uuid4()), reasoning_result["case_id"], _json(reasoning_result), _utcnow()),
            )

    def record_outcome(self, outcome: dict[str, Any]) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO outcomes(outcome_id, case_id, outcome_document, created_at) VALUES (?, ?, ?, ?)",
                (outcome.get("outcome_id", str(uuid4())), outcome["case_id"], _json(outcome), _utcnow()),
            )

    def record_transition(
        self,
        *,
        correlation_id: str,
        from_state: str,
        to_state: str,
        reason: str,
        case_id: str | None = None,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO workflow_transitions(transition_id, case_id, correlation_id, from_state, to_state, reason, occurred_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid4()), case_id, correlation_id, from_state, to_state, reason, _utcnow()),
            )

    def append(self, event_type: str, payload: dict[str, Any]) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO audit_events(event_id, event_type, correlation_id, case_id, client_id, payload, occurred_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    event_type,
                    payload.get("correlation_id"),
                    payload.get("case_id"),
                    payload.get("client_id"),
                    _json(payload),
                    _utcnow(),
                ),
            )

    def get_case(self, case_id: str, *, client_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT case_document FROM cases WHERE case_id = ? AND client_id = ?",
            (case_id, client_id),
        ).fetchone()
        return None if row is None else json.loads(row["case_document"])

    def list_audit_events(self, correlation_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT event_type, payload, occurred_at FROM audit_events WHERE correlation_id = ? ORDER BY occurred_at, event_id",
            (correlation_id,),
        ).fetchall()
        return [
            {"event_type": row["event_type"], "payload": json.loads(row["payload"]), "occurred_at": row["occurred_at"]}
            for row in rows
        ]

    def list_transitions(self, correlation_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            """
            SELECT case_id, from_state, to_state, reason, occurred_at
            FROM workflow_transitions WHERE correlation_id = ? ORDER BY occurred_at, transition_id
            """,
            (correlation_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        self._connection.close()
