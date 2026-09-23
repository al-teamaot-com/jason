from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

from .contracts import (
    CandidateLifecycle,
    ImprovementCandidate,
    ImprovementCandidateDraft,
    ReflectionRecord,
    ReflectionSignalKind,
)


_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS reflection_records (
    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id TEXT NOT NULL UNIQUE,
    schema_version TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    client_id TEXT NULL,
    capability_name TEXT NOT NULL,
    provider_id TEXT NULL,
    outcome TEXT NOT NULL,
    normalized_intent TEXT NOT NULL,
    selector_strategy TEXT NOT NULL,
    requested_result_scope TEXT NOT NULL,
    result_count INTEGER NULL,
    candidate_count INTEGER NULL,
    provider_call_count INTEGER NOT NULL,
    pagination_count INTEGER NOT NULL,
    fallback_count INTEGER NOT NULL,
    evidence_item_count INTEGER NOT NULL,
    duration_ms REAL NULL,
    search_strategies_json TEXT NOT NULL,
    search_result_counts_json TEXT NOT NULL,
    warning_codes_json TEXT NOT NULL,
    user_correction_category TEXT NULL,
    observed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_reflection_correlation
ON reflection_records(organization_id, correlation_id, observed_at);

CREATE INDEX IF NOT EXISTS ix_reflection_capability
ON reflection_records(organization_id, capability_name, observed_at);

CREATE TABLE IF NOT EXISTS improvement_candidates (
    candidate_key TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    signal_kind TEXT NOT NULL,
    capability_name TEXT NOT NULL,
    provider_id TEXT NULL,
    title TEXT NOT NULL,
    proposal TEXT NOT NULL,
    rationale TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS improvement_candidate_sources (
    candidate_key TEXT NOT NULL,
    record_id TEXT NOT NULL,
    added_at TEXT NOT NULL,
    PRIMARY KEY(candidate_key, record_id),
    FOREIGN KEY(candidate_key) REFERENCES improvement_candidates(candidate_key) ON DELETE RESTRICT,
    FOREIGN KEY(record_id) REFERENCES reflection_records(record_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS improvement_candidate_events (
    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    candidate_key TEXT NOT NULL,
    state TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    FOREIGN KEY(candidate_key) REFERENCES improvement_candidates(candidate_key) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_candidate_events
ON improvement_candidate_events(candidate_key, sequence_id);
"""


_ALLOWED_TRANSITIONS = {
    CandidateLifecycle.OBSERVED: {
        CandidateLifecycle.PROPOSED,
        CandidateLifecycle.REJECTED,
    },
    CandidateLifecycle.PROPOSED: {
        CandidateLifecycle.TESTED,
        CandidateLifecycle.REJECTED,
    },
    CandidateLifecycle.TESTED: {
        CandidateLifecycle.APPROVED,
        CandidateLifecycle.REJECTED,
    },
    CandidateLifecycle.APPROVED: {
        CandidateLifecycle.PROMOTED,
        CandidateLifecycle.REJECTED,
    },
    CandidateLifecycle.PROMOTED: set(),
    CandidateLifecycle.REJECTED: set(),
}


class SQLiteReflectionStore:
    """Append-only reflection and candidate-lifecycle store.

    Reflection records and lifecycle events are never updated in place. Candidate
    metadata is immutable after first observation; repeated evidence adds source
    links rather than rewriting history.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._path = str(path)
        self._connection = sqlite3.connect(self._path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(_SCHEMA)
        self._connection.commit()
        if self._path != ":memory:":
            os.chmod(Path(self._path), 0o600)

    def append_record(self, record: ReflectionRecord) -> None:
        record.validate()
        try:
            with self._connection:
                self._connection.execute(
                    """
                    INSERT INTO reflection_records (
                        record_id, schema_version, execution_id, correlation_id,
                        organization_id, client_id, capability_name, provider_id,
                        outcome, normalized_intent, selector_strategy,
                        requested_result_scope, result_count, candidate_count,
                        provider_call_count, pagination_count, fallback_count,
                        evidence_item_count, duration_ms, search_strategies_json,
                        search_result_counts_json, warning_codes_json,
                        user_correction_category, observed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.record_id,
                        record.schema_version,
                        record.execution_id,
                        record.correlation_id,
                        record.organization_id,
                        record.client_id,
                        record.capability_name,
                        record.provider_id,
                        record.outcome,
                        record.normalized_intent,
                        record.selector_strategy,
                        record.requested_result_scope,
                        record.result_count,
                        record.candidate_count,
                        record.provider_call_count,
                        record.pagination_count,
                        record.fallback_count,
                        record.evidence_item_count,
                        record.duration_ms,
                        json.dumps(record.search_strategies),
                        json.dumps(record.search_result_counts),
                        json.dumps(record.warning_codes),
                        record.user_correction_category,
                        record.observed_at.astimezone(timezone.utc).isoformat(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"reflection record already exists: {record.record_id}") from exc

    def get_record(
        self,
        record_id: str,
        *,
        organization_id: str,
    ) -> ReflectionRecord | None:
        self._require_scope(organization_id)
        row = self._connection.execute(
            """
            SELECT * FROM reflection_records
            WHERE record_id = ? AND organization_id = ?
            """,
            (record_id, organization_id),
        ).fetchone()
        return None if row is None else self._record_from_row(row)

    def list_records(
        self,
        *,
        organization_id: str,
        client_id: str | None = None,
        limit: int = 500,
    ) -> tuple[ReflectionRecord, ...]:
        self._require_scope(organization_id)
        if limit < 1 or limit > 5000:
            raise ValueError("limit must be between 1 and 5000")
        if client_id is None:
            rows = self._connection.execute(
                """
                SELECT * FROM reflection_records
                WHERE organization_id = ?
                ORDER BY observed_at DESC, sequence_id DESC
                LIMIT ?
                """,
                (organization_id, limit),
            ).fetchall()
        else:
            if not client_id.strip():
                raise ValueError("client_id must be non-empty when provided")
            rows = self._connection.execute(
                """
                SELECT * FROM reflection_records
                WHERE organization_id = ? AND client_id = ?
                ORDER BY observed_at DESC, sequence_id DESC
                LIMIT ?
                """,
                (organization_id, client_id, limit),
            ).fetchall()
        return tuple(self._record_from_row(row) for row in rows)

    def observe_candidate(
        self,
        *,
        draft: ImprovementCandidateDraft,
        source_record: ReflectionRecord,
        actor_id: str = "system:reflection-detector",
    ) -> ImprovementCandidate:
        source_record.validate()
        draft.validate()
        if not actor_id.strip():
            raise ValueError("actor_id is required")
        key = draft.candidate_key(source_record.organization_id)
        now = datetime.now(timezone.utc).isoformat()

        with self._connection:
            existing = self._connection.execute(
                "SELECT * FROM improvement_candidates WHERE candidate_key = ?",
                (key,),
            ).fetchone()
            created = existing is None
            if created:
                self._connection.execute(
                    """
                    INSERT INTO improvement_candidates (
                        candidate_key, organization_id, signal_kind,
                        capability_name, provider_id, title, proposal,
                        rationale, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        key,
                        source_record.organization_id,
                        draft.signal_kind.value,
                        draft.capability_name,
                        draft.provider_id,
                        draft.title,
                        draft.proposal,
                        draft.rationale,
                        now,
                    ),
                )
                self._connection.execute(
                    """
                    INSERT INTO improvement_candidate_events (
                        event_id, candidate_key, state, actor_id, reason, occurred_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid4()),
                        key,
                        CandidateLifecycle.OBSERVED.value,
                        actor_id,
                        "deterministic reflection signal observed",
                        now,
                    ),
                )
            elif existing["organization_id"] != source_record.organization_id:
                raise PermissionError("candidate organization scope mismatch")

            source_exists = self._connection.execute(
                """
                SELECT 1 FROM reflection_records
                WHERE record_id = ? AND organization_id = ?
                """,
                (source_record.record_id, source_record.organization_id),
            ).fetchone()
            if source_exists is None:
                raise ValueError("source reflection record must be stored before candidate observation")

            self._connection.execute(
                """
                INSERT OR IGNORE INTO improvement_candidate_sources(
                    candidate_key, record_id, added_at
                ) VALUES (?, ?, ?)
                """,
                (key, source_record.record_id, now),
            )

        candidate = self.get_candidate(key, organization_id=source_record.organization_id)
        assert candidate is not None
        return candidate

    def transition_candidate(
        self,
        candidate_key: str,
        *,
        organization_id: str,
        new_state: CandidateLifecycle,
        actor_id: str,
        reason: str,
    ) -> ImprovementCandidate:
        self._require_scope(organization_id)
        if not actor_id.strip() or not reason.strip():
            raise ValueError("candidate transition requires actor_id and reason")
        candidate = self.get_candidate(candidate_key, organization_id=organization_id)
        if candidate is None:
            raise ValueError("candidate not found in organization scope")
        if new_state not in _ALLOWED_TRANSITIONS[candidate.state]:
            raise ValueError(
                f"invalid candidate transition: {candidate.state.value} -> {new_state.value}"
            )
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO improvement_candidate_events(
                    event_id, candidate_key, state, actor_id, reason, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    candidate_key,
                    new_state.value,
                    actor_id,
                    reason,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        updated = self.get_candidate(candidate_key, organization_id=organization_id)
        assert updated is not None
        return updated

    def get_candidate(
        self,
        candidate_key: str,
        *,
        organization_id: str,
    ) -> ImprovementCandidate | None:
        self._require_scope(organization_id)
        row = self._connection.execute(
            """
            SELECT * FROM improvement_candidates
            WHERE candidate_key = ? AND organization_id = ?
            """,
            (candidate_key, organization_id),
        ).fetchone()
        if row is None:
            return None
        event = self._connection.execute(
            """
            SELECT * FROM improvement_candidate_events
            WHERE candidate_key = ?
            ORDER BY sequence_id DESC LIMIT 1
            """,
            (candidate_key,),
        ).fetchone()
        if event is None:
            raise RuntimeError("candidate lifecycle history is missing")
        sources = self._connection.execute(
            """
            SELECT record_id FROM improvement_candidate_sources
            WHERE candidate_key = ?
            ORDER BY added_at, record_id
            """,
            (candidate_key,),
        ).fetchall()
        candidate = ImprovementCandidate(
            candidate_key=row["candidate_key"],
            organization_id=row["organization_id"],
            signal_kind=ReflectionSignalKind(row["signal_kind"]),
            capability_name=row["capability_name"],
            provider_id=row["provider_id"],
            title=row["title"],
            proposal=row["proposal"],
            rationale=row["rationale"],
            state=CandidateLifecycle(event["state"]),
            source_record_ids=tuple(item["record_id"] for item in sources),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
        candidate.validate()
        return candidate

    def close(self) -> None:
        self._connection.close()

    @staticmethod
    def _require_scope(organization_id: str) -> None:
        if not organization_id.strip():
            raise ValueError("organization_id is required")

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> ReflectionRecord:
        record = ReflectionRecord(
            record_id=row["record_id"],
            schema_version=row["schema_version"],
            execution_id=row["execution_id"],
            correlation_id=row["correlation_id"],
            organization_id=row["organization_id"],
            client_id=row["client_id"],
            capability_name=row["capability_name"],
            provider_id=row["provider_id"],
            outcome=row["outcome"],
            normalized_intent=row["normalized_intent"],
            selector_strategy=row["selector_strategy"],
            requested_result_scope=row["requested_result_scope"],
            result_count=row["result_count"],
            candidate_count=row["candidate_count"],
            provider_call_count=row["provider_call_count"],
            pagination_count=row["pagination_count"],
            fallback_count=row["fallback_count"],
            evidence_item_count=row["evidence_item_count"],
            duration_ms=row["duration_ms"],
            search_strategies=tuple(json.loads(row["search_strategies_json"])),
            search_result_counts=tuple(json.loads(row["search_result_counts_json"])),
            warning_codes=tuple(json.loads(row["warning_codes_json"])),
            user_correction_category=row["user_correction_category"],
            observed_at=datetime.fromisoformat(row["observed_at"]),
        )
        record.validate()
        return record
