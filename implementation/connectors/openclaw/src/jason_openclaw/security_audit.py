from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Mapping


class SQLiteIngressSecurityAudit:
    """Durable security audit for events that occur before trusted orchestration context exists."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._connection = sqlite3.connect(str(self._path))
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS openclaw_ingress_security_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                request_id TEXT NOT NULL,
                correlation_id TEXT NOT NULL,
                machine_identity TEXT,
                payload TEXT NOT NULL,
                occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS ix_openclaw_ingress_correlation
                ON openclaw_ingress_security_events(correlation_id, id);
            """
        )
        self._connection.commit()
        os.chmod(self._path, 0o600)

    def append(self, event_type: str, payload: Mapping[str, Any]) -> None:
        safe_payload = self._sanitize(payload)
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO openclaw_ingress_security_events(
                    event_type, request_id, correlation_id, machine_identity, payload
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event_type,
                    str(safe_payload.get("request_id", "unknown")),
                    str(safe_payload.get("correlation_id", "unknown")),
                    (
                        str(safe_payload["machine_identity"])
                        if safe_payload.get("machine_identity") is not None
                        else None
                    ),
                    json.dumps(safe_payload, sort_keys=True, separators=(",", ":")),
                ),
            )

    def list_by_correlation(self, correlation_id: str) -> tuple[Mapping[str, Any], ...]:
        rows = self._connection.execute(
            """
            SELECT event_type, request_id, correlation_id, machine_identity, payload, occurred_at
            FROM openclaw_ingress_security_events
            WHERE correlation_id = ? ORDER BY id
            """,
            (correlation_id,),
        ).fetchall()
        return tuple(
            {
                "event_type": row["event_type"],
                "request_id": row["request_id"],
                "correlation_id": row["correlation_id"],
                "machine_identity": row["machine_identity"],
                "payload": json.loads(row["payload"]),
                "occurred_at": row["occurred_at"],
            }
            for row in rows
        )

    def close(self) -> None:
        self._connection.close()

    @classmethod
    def _sanitize(cls, payload: Mapping[str, Any]) -> dict[str, Any]:
        forbidden = {
            "signature",
            "authorization",
            "secret",
            "token",
            "api_key",
            "api_secret",
            "password",
            "private_key",
        }
        result: dict[str, Any] = {}
        for key, value in payload.items():
            normalized_key = str(key).lower()
            if normalized_key in forbidden:
                continue
            if isinstance(value, Mapping):
                result[str(key)] = cls._sanitize(value)
            elif isinstance(value, (str, int, float, bool)) or value is None:
                result[str(key)] = value
            else:
                result[str(key)] = str(value)
        return result
