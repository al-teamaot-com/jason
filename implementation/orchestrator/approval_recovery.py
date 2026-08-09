"""Explicit recovery records for consumed approval continuations.

A consumed continuation is never silently released or replayed. Recovery is a
separate governed decision that records what an authorized operator determined
about the interrupted execution. A retry authorization, when used by a later
component, must carry a new recovery id and fresh JKD-001 authority context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
import json
import sqlite3
from threading import Lock
from typing import Protocol


class ApprovalRecoveryDisposition(str, Enum):
    CONFIRMED_COMPLETED = "confirmed_completed"
    CONFIRMED_NOT_EXECUTED = "confirmed_not_executed"
    ABANDONED = "abandoned"
    RETRY_AUTHORIZED = "retry_authorized"


@dataclass(frozen=True, slots=True)
class ApprovalRecoveryRecord:
    recovery_id: str
    approval_id: str
    organization_id: str
    request_id: str
    correlation_id: str
    capability: str
    decided_by: str
    disposition: ApprovalRecoveryDisposition
    reason: str
    decided_at: datetime
    evidence_references: tuple[str, ...] = ()
    fresh_authority_context_id: str | None = None

    def validate(self) -> None:
        for value in (
            self.recovery_id,
            self.approval_id,
            self.organization_id,
            self.request_id,
            self.correlation_id,
            self.capability,
            self.decided_by,
            self.reason,
        ):
            if not value.strip():
                raise ValueError("approval recovery identifiers and reason must be non-empty")
        if self.decided_at.tzinfo is None:
            raise ValueError("approval recovery timestamp must be timezone-aware")
        if self.disposition is ApprovalRecoveryDisposition.RETRY_AUTHORIZED:
            if self.fresh_authority_context_id is None or not self.fresh_authority_context_id.strip():
                raise PermissionError("retry authorization requires fresh JKD-001 authority context")
        elif self.fresh_authority_context_id is not None:
            raise ValueError("fresh authority context is only valid for retry authorization")
        if any(not ref.strip() for ref in self.evidence_references):
            raise ValueError("approval recovery evidence references must be non-empty")


class ApprovalRecoveryLedger(Protocol):
    def record(self, record: ApprovalRecoveryRecord) -> None: ...
    def get(self, recovery_id: str) -> ApprovalRecoveryRecord | None: ...


@dataclass
class InMemoryApprovalRecoveryLedger:
    _records: dict[str, ApprovalRecoveryRecord] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def record(self, record: ApprovalRecoveryRecord) -> None:
        record.validate()
        with self._lock:
            existing = self._records.get(record.recovery_id)
            if existing is not None:
                if existing == record:
                    return
                raise ValueError("conflicting approval recovery_id reuse is not permitted")
            self._records[record.recovery_id] = record

    def get(self, recovery_id: str) -> ApprovalRecoveryRecord | None:
        return self._records.get(recovery_id)


@dataclass(frozen=True, slots=True)
class SQLiteApprovalRecoveryLedger:
    database_path: str

    def initialize(self) -> None:
        path = Path(self.database_path)
        if path.parent != Path("."):
            path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS approval_recovery_records (
                    recovery_id TEXT PRIMARY KEY,
                    approval_id TEXT NOT NULL,
                    organization_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    capability TEXT NOT NULL,
                    decided_by TEXT NOT NULL,
                    disposition TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    decided_at TEXT NOT NULL,
                    evidence_references TEXT NOT NULL,
                    fresh_authority_context_id TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_approval_recovery_scope
                ON approval_recovery_records(organization_id, approval_id, decided_at);
                """
            )

    def record(self, record: ApprovalRecoveryRecord) -> None:
        record.validate()
        payload = self._values(record)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM approval_recovery_records WHERE recovery_id = ?",
                (record.recovery_id,),
            ).fetchone()
            if existing is not None:
                if self._row_to_record(existing) == record:
                    connection.rollback()
                    return
                connection.rollback()
                raise ValueError("conflicting approval recovery_id reuse is not permitted")
            try:
                connection.execute(
                    """
                    INSERT INTO approval_recovery_records (
                        recovery_id, approval_id, organization_id, request_id,
                        correlation_id, capability, decided_by, disposition, reason,
                        decided_at, evidence_references, fresh_authority_context_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    payload,
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise ValueError("conflicting approval recovery_id reuse is not permitted") from exc

    def get(self, recovery_id: str) -> ApprovalRecoveryRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM approval_recovery_records WHERE recovery_id = ?",
                (recovery_id,),
            ).fetchone()
        return None if row is None else self._row_to_record(row)

    @staticmethod
    def _values(record: ApprovalRecoveryRecord) -> tuple[object, ...]:
        return (
            record.recovery_id,
            record.approval_id,
            record.organization_id,
            record.request_id,
            record.correlation_id,
            record.capability,
            record.decided_by,
            record.disposition.value,
            record.reason,
            record.decided_at.astimezone(timezone.utc).isoformat(),
            json.dumps(record.evidence_references, separators=(",", ":")),
            record.fresh_authority_context_id,
        )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ApprovalRecoveryRecord:
        return ApprovalRecoveryRecord(
            recovery_id=row["recovery_id"],
            approval_id=row["approval_id"],
            organization_id=row["organization_id"],
            request_id=row["request_id"],
            correlation_id=row["correlation_id"],
            capability=row["capability"],
            decided_by=row["decided_by"],
            disposition=ApprovalRecoveryDisposition(row["disposition"]),
            reason=row["reason"],
            decided_at=datetime.fromisoformat(row["decided_at"]),
            evidence_references=tuple(json.loads(row["evidence_references"])),
            fresh_authority_context_id=row["fresh_authority_context_id"],
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection
