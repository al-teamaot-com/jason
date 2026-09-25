"""Provider-neutral attention scheduling and autonomous work-capacity controls."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Iterable


class WorkState(str, Enum):
    AVAILABLE = "available"
    CANDIDATE = "candidate"
    ACTIVE = "active"
    WAITING = "waiting"
    APPROVAL_PENDING = "approval_pending"
    BLOCKED = "blocked"
    VERIFYING = "verifying"
    COMPLETE = "complete"
    ESCALATED = "escalated"


ACTIVE_SLOT_STATES = frozenset({WorkState.ACTIVE, WorkState.VERIFYING})


@dataclass(frozen=True)
class AutonomyConfig:
    max_active_work_items: int = 2

    def __post_init__(self) -> None:
        if self.max_active_work_items < 1:
            raise ValueError("max_active_work_items must be at least 1")


@dataclass(frozen=True)
class WorkItem:
    resource_id: str
    state: WorkState
    priority: int = 0
    owned_by_jason: bool = False
    urgent: bool = False
    playbook_id: str | None = None
    next_action: str | None = None
    next_check_at: datetime | None = None
    wake_on: str | None = None
    queue_reconciliation_required: bool = False
    reason: str = ""
    source_version: str | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class WorkLedger:
    """Small provider-neutral ledger. Durable storage is supplied by the runtime."""

    def __init__(self, items: Iterable[WorkItem] = ()) -> None:
        self._items = {item.resource_id: item for item in items}

    def upsert(self, item: WorkItem) -> None:
        self._items[item.resource_id] = item

    def get(self, resource_id: str) -> WorkItem | None:
        return self._items.get(resource_id)

    def items(self) -> tuple[WorkItem, ...]:
        return tuple(self._items.values())

    def active_count(self) -> int:
        return sum(item.state in ACTIVE_SLOT_STATES for item in self._items.values())

    def available_slots(self, config: AutonomyConfig) -> int:
        return max(0, config.max_active_work_items - self.active_count())

    def activate_next(self, config: AutonomyConfig, *, now: datetime | None = None) -> tuple[WorkItem, ...]:
        now = now or datetime.now(timezone.utc)
        slots = self.available_slots(config)
        if slots == 0:
            return ()

        candidates = [
            item for item in self._items.values()
            if item.state in {WorkState.AVAILABLE, WorkState.CANDIDATE}
        ]
        candidates.sort(
            key=lambda item: (
                -int(item.urgent),
                -int(item.owned_by_jason),
                -item.priority,
                item.updated_at,
                item.resource_id,
            )
        )
        activated = []
        for item in candidates[:slots]:
            active = replace(item, state=WorkState.ACTIVE, updated_at=now)
            self._items[item.resource_id] = active
            activated.append(active)
        return tuple(activated)


@dataclass
class QueueAttentionState:
    dirty: bool = False
    reasons: set[str] = field(default_factory=set)
    last_reconciled_at: datetime | None = None

    def mark_dirty(self, reason: str) -> None:
        self.dirty = True
        self.reasons.add(reason)

    def mark_reconciled(self, *, now: datetime | None = None) -> tuple[str, ...]:
        reasons = tuple(sorted(self.reasons))
        self.dirty = False
        self.reasons.clear()
        self.last_reconciled_at = now or datetime.now(timezone.utc)
        return reasons


@dataclass(frozen=True)
class ReconcileDecision:
    should_reconcile: bool
    reason: str


class AttentionScheduler:
    """Event-first queue attention with a staleness safety net."""

    def __init__(self, *, staleness_budget: timedelta = timedelta(minutes=30)) -> None:
        self.staleness_budget = staleness_budget

    def should_reconcile(
        self,
        attention: QueueAttentionState,
        *,
        capacity_available: bool,
        urgent_event: bool = False,
        explicitly_requested: bool = False,
        now: datetime | None = None,
    ) -> ReconcileDecision:
        now = now or datetime.now(timezone.utc)

        if explicitly_requested:
            return ReconcileDecision(True, "explicit_request")
        if urgent_event and attention.dirty:
            return ReconcileDecision(True, "urgent_event")
        if attention.dirty and capacity_available:
            return ReconcileDecision(True, "queue_dirty_capacity_available")
        if attention.last_reconciled_at is None:
            return ReconcileDecision(True, "startup_or_unknown_queue_state")
        if now - attention.last_reconciled_at >= self.staleness_budget:
            return ReconcileDecision(True, "staleness_budget_exceeded")
        return ReconcileDecision(False, "no_attention_required")


# Durable persistence intentionally lives outside JKD-009's append-only event store.
# The event store records why scheduling decisions occurred; this store owns current
# resumable work state.
import json
import os
import sqlite3
from pathlib import Path


class SQLiteWorkLedger(WorkLedger):
    """Durable provider-neutral work ledger for resumable autonomous work."""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS autonomous_work_items (
        resource_id TEXT PRIMARY KEY,
        state TEXT NOT NULL,
        priority INTEGER NOT NULL,
        owned_by_jason INTEGER NOT NULL DEFAULT 0,
        urgent INTEGER NOT NULL DEFAULT 0,
        playbook_id TEXT,
        next_action TEXT,
        next_check_at TEXT,
        wake_on TEXT,
        queue_reconciliation_required INTEGER NOT NULL,
        reason TEXT NOT NULL,
        source_version TEXT,
        updated_at TEXT NOT NULL
    );
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self.path), timeout=10.0, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.executescript(self._SCHEMA)
        columns = {
            str(row["name"])
            for row in self._connection.execute("PRAGMA table_info(autonomous_work_items)")
        }
        migrations = {
            "source_version": "TEXT",
            "owned_by_jason": "INTEGER NOT NULL DEFAULT 0",
            "urgent": "INTEGER NOT NULL DEFAULT 0",
        }
        for name, ddl in migrations.items():
            if name not in columns:
                self._connection.execute(
                    f"ALTER TABLE autonomous_work_items ADD COLUMN {name} {ddl}"
                )
        os.chmod(self.path, 0o600)
        super().__init__(self._load_items())

    def _load_items(self) -> tuple[WorkItem, ...]:
        rows = self._connection.execute(
            "SELECT * FROM autonomous_work_items ORDER BY updated_at, resource_id"
        ).fetchall()
        return tuple(self._row_to_item(row) for row in rows)

    def upsert(self, item: WorkItem) -> None:
        super().upsert(item)
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO autonomous_work_items(
                    resource_id, state, priority, owned_by_jason, urgent, playbook_id, next_action,
                    next_check_at, wake_on, queue_reconciliation_required,
                    reason, source_version, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(resource_id) DO UPDATE SET
                    state=excluded.state,
                    priority=excluded.priority,
                    owned_by_jason=excluded.owned_by_jason,
                    urgent=excluded.urgent,
                    playbook_id=excluded.playbook_id,
                    next_action=excluded.next_action,
                    next_check_at=excluded.next_check_at,
                    wake_on=excluded.wake_on,
                    queue_reconciliation_required=excluded.queue_reconciliation_required,
                    reason=excluded.reason,
                    source_version=excluded.source_version,
                    updated_at=excluded.updated_at
                """,
                self._item_values(item),
            )

    def activate_next(self, config: AutonomyConfig, *, now: datetime | None = None) -> tuple[WorkItem, ...]:
        activated = super().activate_next(config, now=now)
        for item in activated:
            self.upsert(item)
        return activated

    def close(self) -> None:
        self._connection.close()

    @staticmethod
    def _item_values(item: WorkItem) -> tuple[object, ...]:
        return (
            item.resource_id,
            item.state.value,
            item.priority,
            int(item.owned_by_jason),
            int(item.urgent),
            item.playbook_id,
            item.next_action,
            item.next_check_at.isoformat() if item.next_check_at else None,
            item.wake_on,
            int(item.queue_reconciliation_required),
            item.reason,
            item.source_version,
            item.updated_at.isoformat(),
        )

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> WorkItem:
        return WorkItem(
            resource_id=row["resource_id"],
            state=WorkState(row["state"]),
            priority=int(row["priority"]),
            owned_by_jason=bool(row["owned_by_jason"]),
            urgent=bool(row["urgent"]),
            playbook_id=row["playbook_id"],
            next_action=row["next_action"],
            next_check_at=datetime.fromisoformat(row["next_check_at"]) if row["next_check_at"] else None,
            wake_on=row["wake_on"],
            queue_reconciliation_required=bool(row["queue_reconciliation_required"]),
            reason=row["reason"],
            source_version=row["source_version"],
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
