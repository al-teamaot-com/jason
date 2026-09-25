"""Durable provider-neutral targeted wake/recheck scheduling.

Known work should be revisited directly instead of rediscovered through full
queue scans. Wakes may be time-based or event-armed. This module stores only the
bounded selector needed for a future governed read; execution authority remains
outside the scheduler.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


class WakeKind(str, Enum):
    TARGETED_READ = "targeted_read"
    QUEUE_RECONCILE = "queue_reconcile"


class WakeState(str, Enum):
    ARMED = "armed"
    PENDING = "pending"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass(frozen=True)
class TargetedWake:
    wake_id: str
    resource_id: str
    reason: str
    kind: WakeKind
    due_at: datetime | None = None
    wake_on: str | None = None
    capability_name: str | None = None
    arguments: Mapping[str, Any] = field(default_factory=dict)
    queue_reconciliation_required: bool = False
    max_attempts: int = 3

    def __post_init__(self) -> None:
        if not self.wake_id.strip():
            raise ValueError("wake_id must be non-empty")
        if not self.resource_id.strip():
            raise ValueError("resource_id must be non-empty")
        if not self.reason.strip():
            raise ValueError("reason must be non-empty")
        if (self.due_at is None) == (not self.wake_on):
            raise ValueError("exactly one of due_at or wake_on is required")
        if self.due_at is not None and self.due_at.tzinfo is None:
            raise ValueError("due_at must be timezone-aware")
        if not 1 <= self.max_attempts <= 10:
            raise ValueError("max_attempts must be between 1 and 10")
        if self.kind is WakeKind.TARGETED_READ and not str(self.capability_name or "").strip():
            raise ValueError("targeted reads require capability_name")
        if self.kind is WakeKind.QUEUE_RECONCILE and self.capability_name is not None:
            raise ValueError("queue reconciliation wake cannot carry a capability")


@dataclass(frozen=True)
class DueWake:
    wake: TargetedWake
    attempt_count: int


class SQLiteTargetedWakeStore:
    """Durable targeted wake queue with idempotent scheduling and bounded retry."""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS autonomy_targeted_wakes (
        wake_id TEXT PRIMARY KEY,
        resource_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        state TEXT NOT NULL,
        due_at TEXT,
        wake_on TEXT,
        attempt_count INTEGER NOT NULL,
        max_attempts INTEGER NOT NULL,
        payload TEXT NOT NULL,
        last_error TEXT,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_autonomy_targeted_wakes_due
      ON autonomy_targeted_wakes(state, due_at);
    CREATE INDEX IF NOT EXISTS ix_autonomy_targeted_wakes_event
      ON autonomy_targeted_wakes(state, wake_on, resource_id);
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self.path), timeout=10.0, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.executescript(self._SCHEMA)
        os.chmod(self.path, 0o600)

    def schedule(self, wake: TargetedWake) -> None:
        payload = self._encode(wake)
        state = WakeState.PENDING if wake.due_at is not None else WakeState.ARMED
        due_at = wake.due_at.isoformat() if wake.due_at else None
        now = datetime.now(timezone.utc).isoformat()
        with self._connection:
            existing = self._connection.execute(
                "SELECT payload FROM autonomy_targeted_wakes WHERE wake_id=?",
                (wake.wake_id,),
            ).fetchone()
            if existing is not None:
                if str(existing["payload"]) == payload:
                    return
                raise ValueError("wake_id cannot be reused with changed scope")
            self._connection.execute(
                """
                INSERT INTO autonomy_targeted_wakes(
                    wake_id,resource_id,kind,state,due_at,wake_on,
                    attempt_count,max_attempts,payload,last_error,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    wake.wake_id,
                    wake.resource_id,
                    wake.kind.value,
                    state.value,
                    due_at,
                    wake.wake_on,
                    0,
                    wake.max_attempts,
                    payload,
                    None,
                    now,
                ),
            )

    def signal(
        self,
        wake_on: str,
        *,
        resource_id: str | None = None,
        now: datetime | None = None,
    ) -> tuple[str, ...]:
        event = str(wake_on or "").strip()
        if not event:
            raise ValueError("wake_on must be non-empty")
        now = now or datetime.now(timezone.utc)
        sql = (
            "SELECT wake_id FROM autonomy_targeted_wakes "
            "WHERE state=? AND wake_on=?"
        )
        args: list[Any] = [WakeState.ARMED.value, event]
        if resource_id is not None:
            sql += " AND resource_id=?"
            args.append(str(resource_id))
        rows = self._connection.execute(sql, tuple(args)).fetchall()
        ids = tuple(str(row["wake_id"]) for row in rows)
        if not ids:
            return ()
        with self._connection:
            for wake_id in ids:
                self._connection.execute(
                    """
                    UPDATE autonomy_targeted_wakes
                    SET state=?,due_at=?,updated_at=?
                    WHERE wake_id=? AND state=?
                    """,
                    (
                        WakeState.PENDING.value,
                        now.isoformat(),
                        now.isoformat(),
                        wake_id,
                        WakeState.ARMED.value,
                    ),
                )
        return ids

    def due(
        self,
        *,
        now: datetime | None = None,
        limit: int = 20,
    ) -> tuple[DueWake, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        now = now or datetime.now(timezone.utc)
        rows = self._connection.execute(
            """
            SELECT payload,attempt_count
            FROM autonomy_targeted_wakes
            WHERE state=? AND due_at IS NOT NULL AND due_at<=?
            ORDER BY due_at,wake_id
            LIMIT ?
            """,
            (WakeState.PENDING.value, now.isoformat(), limit),
        ).fetchall()
        return tuple(
            DueWake(self._decode(str(row["payload"])), int(row["attempt_count"]))
            for row in rows
        )

    def complete(self, wake_id: str) -> None:
        self._transition(wake_id, WakeState.COMPLETE, None, None)

    def retry_or_fail(
        self,
        wake_id: str,
        *,
        error: str,
        next_due_at: datetime,
    ) -> WakeState:
        if next_due_at.tzinfo is None:
            raise ValueError("next_due_at must be timezone-aware")
        row = self._connection.execute(
            "SELECT attempt_count,max_attempts FROM autonomy_targeted_wakes WHERE wake_id=?",
            (wake_id,),
        ).fetchone()
        if row is None:
            raise KeyError(wake_id)
        attempts = int(row["attempt_count"]) + 1
        state = (
            WakeState.FAILED
            if attempts >= int(row["max_attempts"])
            else WakeState.PENDING
        )
        with self._connection:
            self._connection.execute(
                """
                UPDATE autonomy_targeted_wakes
                SET state=?,attempt_count=?,due_at=?,last_error=?,updated_at=?
                WHERE wake_id=?
                """,
                (
                    state.value,
                    attempts,
                    None if state is WakeState.FAILED else next_due_at.isoformat(),
                    str(error)[:500],
                    datetime.now(timezone.utc).isoformat(),
                    wake_id,
                ),
            )
        return state

    def state(self, wake_id: str) -> WakeState:
        row = self._connection.execute(
            "SELECT state FROM autonomy_targeted_wakes WHERE wake_id=?",
            (wake_id,),
        ).fetchone()
        if row is None:
            raise KeyError(wake_id)
        return WakeState(str(row["state"]))

    def close(self) -> None:
        self._connection.close()

    def _transition(
        self,
        wake_id: str,
        state: WakeState,
        due_at: datetime | None,
        error: str | None,
    ) -> None:
        with self._connection:
            result = self._connection.execute(
                """
                UPDATE autonomy_targeted_wakes
                SET state=?,due_at=?,last_error=?,updated_at=?
                WHERE wake_id=?
                """,
                (
                    state.value,
                    due_at.isoformat() if due_at else None,
                    error,
                    datetime.now(timezone.utc).isoformat(),
                    wake_id,
                ),
            )
        if result.rowcount != 1:
            raise KeyError(wake_id)

    @staticmethod
    def _encode(wake: TargetedWake) -> str:
        payload = {
            "wake_id": wake.wake_id,
            "resource_id": wake.resource_id,
            "reason": wake.reason,
            "kind": wake.kind.value,
            "due_at": wake.due_at.isoformat() if wake.due_at else None,
            "wake_on": wake.wake_on,
            "capability_name": wake.capability_name,
            "arguments": dict(wake.arguments),
            "queue_reconciliation_required": wake.queue_reconciliation_required,
            "max_attempts": wake.max_attempts,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _decode(payload: str) -> TargetedWake:
        raw = json.loads(payload)
        raw["kind"] = WakeKind(raw["kind"])
        raw["due_at"] = (
            datetime.fromisoformat(raw["due_at"])
            if raw.get("due_at")
            else None
        )
        return TargetedWake(**raw)
