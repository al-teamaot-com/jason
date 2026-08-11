from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Protocol
from uuid import uuid4


_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS orchestration_events (
    event_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    event_type TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    capability_name TEXT NOT NULL,
    stage TEXT NOT NULL,
    payload TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_orchestration_execution
    ON orchestration_events(execution_id, occurred_at, event_id);
CREATE INDEX IF NOT EXISTS ix_orchestration_correlation
    ON orchestration_events(correlation_id, occurred_at, event_id);
"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class OrchestrationEvent:
    event_type: str
    execution_id: str
    correlation_id: str
    organization_id: str
    principal_id: str
    capability_name: str
    stage: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=_utcnow)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        required = {
            "event_id": self.event_id,
            "schema_version": self.schema_version,
            "event_type": self.event_type,
            "execution_id": self.execution_id,
            "correlation_id": self.correlation_id,
            "organization_id": self.organization_id,
            "principal_id": self.principal_id,
            "capability_name": self.capability_name,
            "stage": self.stage,
        }
        missing = sorted(
            name for name, value in required.items() if not value.strip()
        )
        if missing:
            raise ValueError(
                "Required orchestration event fields are empty: "
                + ", ".join(missing)
            )
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware.")
        normalized = json.loads(
            json.dumps(dict(self.payload), sort_keys=True, separators=(",", ":"))
        )
        object.__setattr__(self, "payload", MappingProxyType(normalized))


class OrchestrationEventStore(Protocol):
    def append_event(self, event: OrchestrationEvent) -> None: ...

    def get(self, event_id: str) -> OrchestrationEvent | None: ...

    def list_by_execution(self, execution_id: str) -> tuple[OrchestrationEvent, ...]: ...

    def list_by_correlation(self, correlation_id: str) -> tuple[OrchestrationEvent, ...]: ...

    def list_recent(self, *, limit: int = 100) -> tuple[OrchestrationEvent, ...]: ...


class SQLiteOrchestrationEventStore:
    """Append-only durable orchestration event store for the local pilot."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._path = path
        self._connection = sqlite3.connect(str(path))
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(_SCHEMA)
        self._connection.commit()
        if str(path) != ":memory:":
            os.chmod(Path(path), 0o600)

    def append(self, event_type: str, payload: Mapping[str, Any]) -> None:
        """Adapt the ORCH-001 audit sink to the canonical event contract."""
        event = OrchestrationEvent(
            event_type=event_type,
            execution_id=str(payload["execution_id"]),
            correlation_id=str(payload["correlation_id"]),
            organization_id=str(payload["organization_id"]),
            principal_id=str(payload["principal_id"]),
            capability_name=str(payload["capability_name"]),
            stage=str(payload["stage"]),
            payload=dict(payload),
        )
        self.append_event(event)

    def append_event(self, event: OrchestrationEvent) -> None:
        serialized = json.dumps(
            dict(event.payload), sort_keys=True, separators=(",", ":")
        )
        try:
            with self._connection:
                self._connection.execute(
                    """
                    INSERT INTO orchestration_events(
                        event_id, schema_version, event_type, execution_id,
                        correlation_id, organization_id, principal_id,
                        capability_name, stage, payload, occurred_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.schema_version,
                        event.event_type,
                        event.execution_id,
                        event.correlation_id,
                        event.organization_id,
                        event.principal_id,
                        event.capability_name,
                        event.stage,
                        serialized,
                        event.occurred_at.astimezone(timezone.utc).isoformat(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"Orchestration event already exists: {event.event_id}"
            ) from exc

    def get(self, event_id: str) -> OrchestrationEvent | None:
        row = self._connection.execute(
            "SELECT * FROM orchestration_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        return None if row is None else self._from_row(row)

    def list_by_execution(self, execution_id: str) -> tuple[OrchestrationEvent, ...]:
        rows = self._connection.execute(
            """
            SELECT * FROM orchestration_events
            WHERE execution_id = ?
            ORDER BY occurred_at, event_id
            """,
            (execution_id,),
        ).fetchall()
        return tuple(self._from_row(row) for row in rows)

    def list_by_correlation(self, correlation_id: str) -> tuple[OrchestrationEvent, ...]:
        rows = self._connection.execute(
            """
            SELECT * FROM orchestration_events
            WHERE correlation_id = ?
            ORDER BY occurred_at, event_id
            """,
            (correlation_id,),
        ).fetchall()
        return tuple(self._from_row(row) for row in rows)

    def list_recent(self, *, limit: int = 100) -> tuple[OrchestrationEvent, ...]:
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        rows = self._connection.execute(
            """
            SELECT * FROM orchestration_events
            ORDER BY occurred_at DESC, event_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return tuple(self._from_row(row) for row in rows)

    def close(self) -> None:
        self._connection.close()

    @staticmethod
    def _from_row(row: sqlite3.Row) -> OrchestrationEvent:
        return OrchestrationEvent(
            event_id=row["event_id"],
            schema_version=row["schema_version"],
            event_type=row["event_type"],
            execution_id=row["execution_id"],
            correlation_id=row["correlation_id"],
            organization_id=row["organization_id"],
            principal_id=row["principal_id"],
            capability_name=row["capability_name"],
            stage=row["stage"],
            payload=json.loads(row["payload"]),
            occurred_at=datetime.fromisoformat(row["occurred_at"]),
        )
