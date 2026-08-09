"""Replay guard for approval-authorized orchestration continuation.

The guard provides an atomic, tenant-bound consumption claim before the Central
Orchestrator is invoked. Once claimed, an approval continuation is never implicitly
replayed. If execution later fails or the process crashes, recovery must be explicit;
Jason fails closed rather than risking duplicate side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from threading import Lock
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ApprovalContinuationClaim:
    approval_id: str
    organization_id: str
    request_id: str
    correlation_id: str
    capability: str
    authority_context_id: str
    claimed_at: datetime

    def validate(self) -> None:
        for value in (
            self.approval_id,
            self.organization_id,
            self.request_id,
            self.correlation_id,
            self.capability,
            self.authority_context_id,
        ):
            if not value.strip():
                raise ValueError("approval continuation claim identifiers must be non-empty")
        if self.claimed_at.tzinfo is None:
            raise ValueError("approval continuation claim timestamp must be timezone-aware")


class ApprovalContinuationGuard(Protocol):
    def claim(self, claim: ApprovalContinuationClaim) -> None: ...


@dataclass
class InMemoryApprovalContinuationGuard:
    _claims: dict[str, ApprovalContinuationClaim] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def claim(self, claim: ApprovalContinuationClaim) -> None:
        claim.validate()
        with self._lock:
            existing = self._claims.get(claim.approval_id)
            if existing is not None:
                if existing.organization_id != claim.organization_id:
                    raise PermissionError("approval continuation tenant mismatch")
                raise PermissionError("approval continuation has already been consumed")
            self._claims[claim.approval_id] = claim


@dataclass(frozen=True, slots=True)
class SQLiteApprovalContinuationGuard:
    database_path: str

    def initialize(self) -> None:
        path = Path(self.database_path)
        if path.parent != Path("."):
            path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS approval_continuation_claims (
                    approval_id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    capability TEXT NOT NULL,
                    authority_context_id TEXT NOT NULL,
                    claimed_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_approval_continuation_org
                ON approval_continuation_claims(organization_id, claimed_at);
                """
            )

    def claim(self, claim: ApprovalContinuationClaim) -> None:
        claim.validate()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    "SELECT organization_id FROM approval_continuation_claims WHERE approval_id = ?",
                    (claim.approval_id,),
                ).fetchone()
                if existing is not None:
                    if existing["organization_id"] != claim.organization_id:
                        raise PermissionError("approval continuation tenant mismatch")
                    raise PermissionError("approval continuation has already been consumed")
                connection.execute(
                    """
                    INSERT INTO approval_continuation_claims (
                        approval_id, organization_id, request_id, correlation_id,
                        capability, authority_context_id, claimed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        claim.approval_id,
                        claim.organization_id,
                        claim.request_id,
                        claim.correlation_id,
                        claim.capability,
                        claim.authority_context_id,
                        claim.claimed_at.astimezone(timezone.utc).isoformat(),
                    ),
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise PermissionError("approval continuation has already been consumed") from exc
            except Exception:
                connection.rollback()
                raise

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection
