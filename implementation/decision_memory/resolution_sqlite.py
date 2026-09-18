from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Iterable

from .resolution_memory import (
    ResolutionCase,
    ResolutionCaseStatus,
    ResolutionOutcome,
    ResolutionSignature,
    ResolutionSourceReference,
    ResolutionStep,
    ResolutionStepKind,
)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS resolution_cases (
    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL UNIQUE,
    organization_id TEXT NOT NULL,
    client_id TEXT NOT NULL,
    signature_json TEXT NOT NULL,
    source_references_json TEXT NOT NULL,
    root_cause TEXT NOT NULL,
    final_resolution TEXT NOT NULL,
    outcome TEXT NOT NULL,
    status TEXT NOT NULL,
    technician_confirmed INTEGER NOT NULL,
    recorded_at TEXT NOT NULL,
    resolved_at TEXT NULL,
    owner TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_resolution_case_scope_time
ON resolution_cases(organization_id, client_id, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_resolution_case_scope_status
ON resolution_cases(organization_id, client_id, status);

CREATE TABLE IF NOT EXISTS resolution_steps (
    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    kind TEXT NOT NULL,
    action_key TEXT NOT NULL,
    action_summary TEXT NOT NULL,
    outcome TEXT NOT NULL,
    evidence_summary TEXT NOT NULL,
    read_only INTEGER NOT NULL,
    approval_required INTEGER NOT NULL,
    disruptive INTEGER NOT NULL,
    UNIQUE(case_id, step_id),
    UNIQUE(case_id, ordinal),
    FOREIGN KEY(case_id) REFERENCES resolution_cases(case_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_resolution_steps_case
ON resolution_steps(case_id, ordinal);

CREATE INDEX IF NOT EXISTS idx_resolution_steps_action
ON resolution_steps(action_key);
"""


@dataclass(frozen=True, slots=True)
class SQLiteResolutionMemoryStore:
    """Durable single-node resolution-memory store.

    Raw similar cases are always queried inside one organization/client boundary.
    Cross-client reuse belongs to separately approved pattern memory and is not
    implemented by this store.
    """

    database_path: str

    def initialize(self) -> None:
        path = Path(self.database_path)
        if path.parent != Path("."):
            path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    def add_case(self, case: ResolutionCase) -> None:
        case.validate()
        signature = case.signature.normalized()

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    INSERT INTO resolution_cases (
                        case_id, organization_id, client_id, signature_json,
                        source_references_json, root_cause, final_resolution,
                        outcome, status, technician_confirmed, recorded_at,
                        resolved_at, owner
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        case.case_id,
                        case.organization_id,
                        case.client_id,
                        json.dumps(
                            {
                                "category": signature.category,
                                "product": signature.product,
                                "device_role": signature.device_role,
                                "platform": signature.platform,
                                "product_version": signature.product_version,
                                "symptoms": list(signature.symptoms),
                                "attributes": dict(signature.attributes),
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        json.dumps(
                            [
                                {
                                    "source_type": ref.source_type,
                                    "source_id": ref.source_id,
                                    "correlation_id": ref.correlation_id,
                                }
                                for ref in case.source_references
                            ],
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        case.root_cause,
                        case.final_resolution,
                        case.outcome.value,
                        case.status.value,
                        1 if case.technician_confirmed else 0,
                        case.recorded_at.isoformat(),
                        case.resolved_at.isoformat() if case.resolved_at else None,
                        case.owner,
                    ),
                )

                for step in sorted(case.steps, key=lambda item: item.ordinal):
                    connection.execute(
                        """
                        INSERT INTO resolution_steps (
                            case_id, step_id, ordinal, kind, action_key,
                            action_summary, outcome, evidence_summary,
                            read_only, approval_required, disruptive
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            case.case_id,
                            step.step_id,
                            step.ordinal,
                            step.kind.value,
                            step.action_key,
                            step.action_summary,
                            step.outcome.value,
                            step.evidence_summary,
                            1 if step.read_only else 0,
                            1 if step.approval_required else 0,
                            1 if step.disruptive else 0,
                        ),
                    )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise ValueError("duplicate or conflicting resolution case") from exc
            except Exception:
                connection.rollback()
                raise

    def get_case(
        self,
        *,
        case_id: str,
        organization_id: str,
        client_id: str,
    ) -> ResolutionCase | None:
        self._validate_scope(organization_id, client_id)
        if not case_id.strip():
            raise ValueError("case_id must be non-empty")

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM resolution_cases
                WHERE case_id = ? AND organization_id = ? AND client_id = ?
                """,
                (case_id, organization_id, client_id),
            ).fetchone()
            if row is None:
                return None
            steps = connection.execute(
                """
                SELECT * FROM resolution_steps
                WHERE case_id = ? ORDER BY ordinal ASC
                """,
                (case_id,),
            ).fetchall()
        return self._from_rows(row, steps)

    def list_cases(
        self,
        *,
        organization_id: str,
        client_id: str,
        limit: int = 500,
    ) -> tuple[ResolutionCase, ...]:
        self._validate_scope(organization_id, client_id)
        if limit < 1 or limit > 5000:
            raise ValueError("limit must be between 1 and 5000")

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM resolution_cases
                WHERE organization_id = ? AND client_id = ?
                ORDER BY COALESCE(resolved_at, recorded_at) DESC
                LIMIT ?
                """,
                (organization_id, client_id, limit),
            ).fetchall()

            cases: list[ResolutionCase] = []
            for row in rows:
                steps = connection.execute(
                    """
                    SELECT * FROM resolution_steps
                    WHERE case_id = ? ORDER BY ordinal ASC
                    """,
                    (row["case_id"],),
                ).fetchall()
                cases.append(self._from_rows(row, steps))

        return tuple(cases)

    def count_cases(
        self,
        *,
        organization_id: str,
        client_id: str,
    ) -> int:
        self._validate_scope(organization_id, client_id)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM resolution_cases
                WHERE organization_id = ? AND client_id = ?
                """,
                (organization_id, client_id),
            ).fetchone()
        return int(row["count"])

    def count_cases_global(
        self,
        *,
        organization_id: str,
        client_id: str | None = None,
    ) -> int:
        if not organization_id.strip():
            raise ValueError("organization_id must be non-empty")
        with self._connect() as connection:
            if client_id:
                row = connection.execute(
                    "SELECT COUNT(*) AS count FROM resolution_cases WHERE organization_id = ? AND client_id = ?",
                    (organization_id, client_id),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT COUNT(*) AS count FROM resolution_cases WHERE organization_id = ?",
                    (organization_id,),
                ).fetchone()
        return int(row["count"])

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            timeout=10.0,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    @staticmethod
    def _validate_scope(organization_id: str, client_id: str) -> None:
        if not organization_id.strip() or not client_id.strip():
            raise ValueError("organization_id and client_id must be non-empty")

    @staticmethod
    def _from_rows(
        row: sqlite3.Row,
        step_rows: Iterable[sqlite3.Row],
    ) -> ResolutionCase:
        signature_data = json.loads(row["signature_json"])
        references_data = json.loads(row["source_references_json"])

        case = ResolutionCase(
            case_id=row["case_id"],
            organization_id=row["organization_id"],
            client_id=row["client_id"],
            signature=ResolutionSignature(
                category=signature_data["category"],
                product=signature_data["product"],
                device_role=signature_data["device_role"],
                platform=signature_data["platform"],
                product_version=signature_data.get("product_version", ""),
                symptoms=tuple(signature_data.get("symptoms", [])),
                attributes=dict(signature_data.get("attributes", {})),
            ),
            source_references=tuple(
                ResolutionSourceReference(
                    source_type=item["source_type"],
                    source_id=item["source_id"],
                    correlation_id=item.get("correlation_id"),
                )
                for item in references_data
            ),
            steps=tuple(
                ResolutionStep(
                    step_id=step["step_id"],
                    ordinal=int(step["ordinal"]),
                    kind=ResolutionStepKind(step["kind"]),
                    action_key=step["action_key"],
                    action_summary=step["action_summary"],
                    outcome=ResolutionOutcome(step["outcome"]),
                    evidence_summary=step["evidence_summary"],
                    read_only=bool(step["read_only"]),
                    approval_required=bool(step["approval_required"]),
                    disruptive=bool(step["disruptive"]),
                )
                for step in step_rows
            ),
            root_cause=row["root_cause"],
            final_resolution=row["final_resolution"],
            outcome=ResolutionOutcome(row["outcome"]),
            status=ResolutionCaseStatus(row["status"]),
            technician_confirmed=bool(row["technician_confirmed"]),
            recorded_at=datetime.fromisoformat(row["recorded_at"]),
            resolved_at=(
                datetime.fromisoformat(row["resolved_at"])
                if row["resolved_at"]
                else None
            ),
            owner=row["owner"],
        )
        case.validate()
        return case
