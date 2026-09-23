"""Governed retry execution for interrupted approval continuations.

A retry never reuses the original approval continuation. It consumes a separately
recorded RETRY_AUTHORIZED recovery decision, requires the request to carry the same
fresh JKD-001 authority context, atomically consumes the recovery authorization, and
routes execution only through the Central Orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from threading import Lock
from typing import Callable, Protocol
from uuid import uuid4

from .approval_audit import ApprovalAuditEvent, ApprovalAuditEventType, ApprovalAuditRecorder
from .approval_recovery import (
    ApprovalRecoveryDisposition,
    ApprovalRecoveryLedger,
)
from .contracts import OrchestrationRequest, OrchestrationResult


class OrchestratorExecutor(Protocol):
    def execute(self, request: OrchestrationRequest) -> OrchestrationResult: ...


@dataclass(frozen=True, slots=True)
class ApprovalRecoveryRetryClaim:
    recovery_id: str
    organization_id: str
    request_id: str
    correlation_id: str
    capability: str
    authority_context_id: str
    claimed_at: datetime

    def validate(self) -> None:
        for value in (
            self.recovery_id,
            self.organization_id,
            self.request_id,
            self.correlation_id,
            self.capability,
            self.authority_context_id,
        ):
            if not value.strip():
                raise ValueError("approval recovery retry claim identifiers must be non-empty")
        if self.claimed_at.tzinfo is None:
            raise ValueError("approval recovery retry claim timestamp must be timezone-aware")


class ApprovalRecoveryRetryGuard(Protocol):
    def claim(self, claim: ApprovalRecoveryRetryClaim) -> None: ...


@dataclass
class InMemoryApprovalRecoveryRetryGuard:
    _claims: dict[str, ApprovalRecoveryRetryClaim] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def claim(self, claim: ApprovalRecoveryRetryClaim) -> None:
        claim.validate()
        with self._lock:
            existing = self._claims.get(claim.recovery_id)
            if existing is not None:
                if existing.organization_id != claim.organization_id:
                    raise PermissionError("approval recovery retry tenant mismatch")
                raise PermissionError("approval recovery retry has already been consumed")
            self._claims[claim.recovery_id] = claim


@dataclass(frozen=True, slots=True)
class SQLiteApprovalRecoveryRetryGuard:
    """Durable one-time consumption boundary for recovery retry authorizations."""

    database_path: str

    def initialize(self) -> None:
        path = Path(self.database_path)
        if path.parent != Path("."):
            path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS approval_recovery_retry_claims (
                    recovery_id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    capability TEXT NOT NULL,
                    authority_context_id TEXT NOT NULL,
                    claimed_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_approval_recovery_retry_org
                ON approval_recovery_retry_claims(organization_id, claimed_at);
                """
            )

    def claim(self, claim: ApprovalRecoveryRetryClaim) -> None:
        claim.validate()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    "SELECT organization_id FROM approval_recovery_retry_claims "
                    "WHERE recovery_id = ?",
                    (claim.recovery_id,),
                ).fetchone()
                if existing is not None:
                    if existing["organization_id"] != claim.organization_id:
                        raise PermissionError("approval recovery retry tenant mismatch")
                    raise PermissionError("approval recovery retry has already been consumed")
                connection.execute(
                    """
                    INSERT INTO approval_recovery_retry_claims (
                        recovery_id, organization_id, request_id, correlation_id,
                        capability, authority_context_id, claimed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        claim.recovery_id,
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
                raise PermissionError(
                    "approval recovery retry has already been consumed"
                ) from exc
            except Exception:
                connection.rollback()
                raise

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection


@dataclass(frozen=True, slots=True)
class GovernedApprovalRecoveryRetryExecutor:
    recovery_ledger: ApprovalRecoveryLedger
    retry_guard: ApprovalRecoveryRetryGuard
    orchestrator: OrchestratorExecutor
    audit: ApprovalAuditRecorder
    event_id_factory: Callable[[], str] = lambda: str(uuid4())
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)

    def execute(
        self,
        *,
        recovery_id: str,
        request: OrchestrationRequest,
    ) -> OrchestrationResult:
        if not recovery_id.strip():
            raise ValueError("recovery_id must be non-empty")

        recovery = self.recovery_ledger.get(recovery_id)
        if recovery is None:
            raise PermissionError("approval recovery record was not found")
        if recovery.disposition is not ApprovalRecoveryDisposition.RETRY_AUTHORIZED:
            raise PermissionError("approval recovery is not authorized for retry")

        if (
            recovery.organization_id != request.organization_id
            or recovery.request_id != request.execution_id
            or recovery.correlation_id != request.correlation_id
            or recovery.capability != request.capability_name
        ):
            raise PermissionError("approval recovery retry scope mismatch")

        if not request.approval_present:
            raise PermissionError("approval recovery retry requires approval evidence")
        if not request.authority_allowed or not request.authority_context_id:
            raise PermissionError("approval recovery retry requires fresh JKD-001 authority")
        if request.authority_context_id != recovery.fresh_authority_context_id:
            raise PermissionError("fresh JKD-001 authority context mismatch")

        now = self._now()
        self.retry_guard.claim(
            ApprovalRecoveryRetryClaim(
                recovery_id=recovery.recovery_id,
                organization_id=request.organization_id,
                request_id=request.execution_id,
                correlation_id=request.correlation_id,
                capability=request.capability_name,
                authority_context_id=request.authority_context_id,
                claimed_at=now,
            )
        )

        # Claim is intentionally committed before orchestration. Any crash/failure
        # after this line requires a new recovery decision; this retry is never
        # silently released for another attempt.
        result = self.orchestrator.execute(request)
        self.audit.record(
            ApprovalAuditEvent(
                event_id=self.event_id_factory(),
                event_type=ApprovalAuditEventType.ORCHESTRATOR_RESUMED,
                occurred_at=self._now(),
                approval_id=recovery.approval_id,
                request_id=request.execution_id,
                correlation_id=request.correlation_id,
                organization_id=request.organization_id,
                client_id=request.client_id,
                actor_identity_id=request.principal_id,
                capability=request.capability_name,
                authority_context_id=request.authority_context_id,
                metadata={
                    "recovery_id": recovery.recovery_id,
                    "recovery_retry": "true",
                    "recovery_decided_by": recovery.decided_by,
                    "orchestration_status": result.status.value,
                    "orchestration_stage": result.stage.value,
                },
            )
        )
        return result

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            raise ValueError("approval recovery retry clock must be timezone-aware")
        return value.astimezone(timezone.utc)
