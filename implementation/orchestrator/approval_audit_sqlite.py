"""Durable SQLite sink for immutable approval audit events.

This implementation is intended for a single Jason deployment node or other
single-writer durable runtime. It uses SQLite transactions to preserve append-only
semantics and fail closed on duplicate IDs, tenant mismatch, or chain races.
Distributed/multi-writer deployments should implement the same sink contract on a
transactional shared database rather than sharing a SQLite file over network storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import sqlite3

from connectors.src.jason_connectors.approval_requests import ApprovalEvidenceReference

from .approval_audit import ApprovalAuditEvent, ApprovalAuditEventType


_SCHEMA = """
CREATE TABLE IF NOT EXISTS approval_audit_events (
    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    approval_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    client_id TEXT NULL,
    actor_identity_id TEXT NULL,
    capability TEXT NOT NULL,
    channel TEXT NULL,
    channel_reference_id TEXT NULL,
    authority_context_id TEXT NULL,
    reason_code TEXT NULL,
    evidence_json TEXT NOT NULL,
    previous_event_hash TEXT NULL,
    event_hash TEXT NOT NULL UNIQUE,
    metadata_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_approval_audit_approval_sequence
ON approval_audit_events(approval_id, sequence_id);
CREATE INDEX IF NOT EXISTS idx_approval_audit_org_sequence
ON approval_audit_events(organization_id, sequence_id);
"""


@dataclass(frozen=True, slots=True)
class SQLiteApprovalAuditSink:
    database_path: str

    def initialize(self) -> None:
        path = Path(self.database_path)
        if path.parent != Path("."):
            path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    def last_for_approval(
        self,
        approval_id: str,
        organization_id: str | None = None,
    ) -> ApprovalAuditEvent | None:
        if not approval_id.strip():
            raise ValueError("approval_id must be non-empty")
        query = """
            SELECT * FROM approval_audit_events
            WHERE approval_id = ?
        """
        params: list[str] = [approval_id]
        if organization_id is not None:
            if not organization_id.strip():
                raise ValueError("organization_id must be non-empty when provided")
            query += " AND organization_id = ?"
            params.append(organization_id)
        query += " ORDER BY sequence_id DESC LIMIT 1"
        with self._connect() as connection:
            row = connection.execute(query, tuple(params)).fetchone()
        return self._from_row(row) if row is not None else None

    def append(self, event: ApprovalAuditEvent) -> None:
        event.validate()
        if not event.event_hash or event.event_hash != event.calculated_hash():
            raise ValueError("approval audit event hash is missing or invalid")

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing_scope = connection.execute(
                    """
                    SELECT organization_id FROM approval_audit_events
                    WHERE approval_id = ?
                    ORDER BY sequence_id ASC LIMIT 1
                    """,
                    (event.approval_id,),
                ).fetchone()
                if existing_scope is not None and existing_scope["organization_id"] != event.organization_id:
                    raise PermissionError("approval audit tenant mismatch")

                previous = connection.execute(
                    """
                    SELECT event_hash FROM approval_audit_events
                    WHERE approval_id = ? AND organization_id = ?
                    ORDER BY sequence_id DESC LIMIT 1
                    """,
                    (event.approval_id, event.organization_id),
                ).fetchone()
                expected_previous = previous["event_hash"] if previous is not None else None
                if event.previous_event_hash != expected_previous:
                    raise ValueError("approval audit append chain mismatch")

                connection.execute(
                    """
                    INSERT INTO approval_audit_events (
                        event_id, event_type, occurred_at, approval_id, request_id,
                        correlation_id, organization_id, client_id, actor_identity_id,
                        capability, channel, channel_reference_id, authority_context_id,
                        reason_code, evidence_json, previous_event_hash, event_hash,
                        metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.event_type.value,
                        event.occurred_at.isoformat(),
                        event.approval_id,
                        event.request_id,
                        event.correlation_id,
                        event.organization_id,
                        event.client_id,
                        event.actor_identity_id,
                        event.capability,
                        event.channel,
                        event.channel_reference_id,
                        event.authority_context_id,
                        event.reason_code,
                        json.dumps(
                            [
                                {
                                    "artifact_id": ref.artifact_id,
                                    "organization_id": ref.organization_id,
                                    "content_sha256": ref.content_sha256,
                                }
                                for ref in event.evidence_references
                            ],
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        event.previous_event_hash,
                        event.event_hash,
                        json.dumps(dict(event.metadata), sort_keys=True, separators=(",", ":")),
                    ),
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise ValueError("duplicate or conflicting approval audit event") from exc
            except Exception:
                connection.rollback()
                raise

    def list_for_approval(self, *, approval_id: str, organization_id: str) -> tuple[ApprovalAuditEvent, ...]:
        if not approval_id.strip() or not organization_id.strip():
            raise ValueError("approval_id and organization_id must be non-empty")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM approval_audit_events
                WHERE approval_id = ? AND organization_id = ?
                ORDER BY sequence_id ASC
                """,
                (approval_id, organization_id),
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    @staticmethod
    def _from_row(row: sqlite3.Row) -> ApprovalAuditEvent:
        evidence = tuple(
            ApprovalEvidenceReference(
                artifact_id=item["artifact_id"],
                organization_id=item["organization_id"],
                content_sha256=item["content_sha256"],
            )
            for item in json.loads(row["evidence_json"])
        )
        return ApprovalAuditEvent(
            event_id=row["event_id"],
            event_type=ApprovalAuditEventType(row["event_type"]),
            occurred_at=datetime.fromisoformat(row["occurred_at"]),
            approval_id=row["approval_id"],
            request_id=row["request_id"],
            correlation_id=row["correlation_id"],
            organization_id=row["organization_id"],
            client_id=row["client_id"],
            actor_identity_id=row["actor_identity_id"],
            capability=row["capability"],
            channel=row["channel"],
            channel_reference_id=row["channel_reference_id"],
            authority_context_id=row["authority_context_id"],
            reason_code=row["reason_code"],
            evidence_references=evidence,
            previous_event_hash=row["previous_event_hash"],
            event_hash=row["event_hash"],
            metadata=json.loads(row["metadata_json"]),
        )
