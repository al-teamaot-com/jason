from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

TERMINAL_STATES = frozenset({"complete", "cancelled"})


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def digest_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Assignment:
    assignment_id: str
    source: str
    source_ref: str
    title: str
    priority: int
    work_type: str
    state: str
    runnable: bool
    blocked_reason: str | None
    scope_hash: str
    metadata: dict[str, Any]
    lease_owner: str | None
    lease_until: str | None
    attempt_count: int
    completion_percent: int


class PMV2Store:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=30000")
            yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS assignments (
                    assignment_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    title TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    work_type TEXT NOT NULL,
                    state TEXT NOT NULL,
                    runnable INTEGER NOT NULL CHECK (runnable IN (0,1)),
                    blocked_reason TEXT,
                    scope_hash TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    lease_owner TEXT,
                    lease_until TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    completion_percent INTEGER NOT NULL DEFAULT 0
                        CHECK (completion_percent BETWEEN 0 AND 100),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(source, source_ref)
                );
                CREATE INDEX IF NOT EXISTS idx_assignments_dispatch
                  ON assignments(runnable, state, priority, updated_at);
                CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    assignment_id TEXT,
                    kind TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(assignment_id) REFERENCES assignments(assignment_id)
                );
                CREATE INDEX IF NOT EXISTS idx_events_assignment
                  ON events(assignment_id, event_id);
                CREATE TABLE IF NOT EXISTS idempotency (
                    idempotency_key TEXT PRIMARY KEY,
                    assignment_id TEXT,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_digest TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(assignment_id) REFERENCES assignments(assignment_id)
                );
                CREATE TABLE IF NOT EXISTS component_health (
                    component TEXT PRIMARY KEY,
                    instance_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    checked_at TEXT NOT NULL,
                    details_json TEXT NOT NULL
                );
                """
            )

    @staticmethod
    def _row(row: sqlite3.Row) -> Assignment:
        return Assignment(
            assignment_id=row["assignment_id"],
            source=row["source"],
            source_ref=row["source_ref"],
            title=row["title"],
            priority=int(row["priority"]),
            work_type=row["work_type"],
            state=row["state"],
            runnable=bool(row["runnable"]),
            blocked_reason=row["blocked_reason"],
            scope_hash=row["scope_hash"],
            metadata=json.loads(row["metadata_json"]),
            lease_owner=row["lease_owner"],
            lease_until=row["lease_until"],
            attempt_count=int(row["attempt_count"]),
            completion_percent=int(row["completion_percent"]),
        )

    def upsert_assignment(self, *, assignment_id: str, source: str, source_ref: str,
                          title: str, priority: int, work_type: str, runnable: bool,
                          scope_hash: str, metadata: dict[str, Any],
                          blocked_reason: str | None = None) -> Assignment:
        stamp = utcnow()
        initial_state = "queued" if runnable else "proposal_only"
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            prior = conn.execute(
                "SELECT * FROM assignments WHERE source=? AND source_ref=?",
                (source, source_ref),
            ).fetchone()
            if prior is None:
                conn.execute(
                    """
                    INSERT INTO assignments(
                      assignment_id,source,source_ref,title,priority,work_type,state,
                      runnable,blocked_reason,scope_hash,metadata_json,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (assignment_id, source, source_ref, title, priority, work_type,
                     initial_state, int(runnable), blocked_reason, scope_hash,
                     canonical_json(metadata), stamp, stamp),
                )
                self._event_conn(conn, assignment_id, "assignment_discovered", {
                    "source": source, "source_ref": source_ref,
                    "runnable": runnable, "scope_hash": scope_hash,
                })
            else:
                old_scope = prior["scope_hash"]
                if old_scope != scope_hash and prior["state"] not in TERMINAL_STATES | {"proposal_only"}:
                    conn.execute(
                        """
                        UPDATE assignments
                        SET runnable=0,state='blocked',blocked_reason='source_scope_changed',
                            updated_at=?
                        WHERE assignment_id=?
                        """,
                        (stamp, prior["assignment_id"]),
                    )
                    self._event_conn(conn, prior["assignment_id"], "source_scope_changed", {
                        "old_scope_hash": old_scope, "new_scope_hash": scope_hash,
                    })
                elif prior["state"] in {"proposal_only", "queued"}:
                    conn.execute(
                        """
                        UPDATE assignments
                        SET title=?,priority=?,work_type=?,runnable=?,scope_hash=?,
                            metadata_json=?,blocked_reason=?,state=?,updated_at=?
                        WHERE assignment_id=?
                        """,
                        (title, priority, work_type, int(runnable), scope_hash,
                         canonical_json(metadata), blocked_reason,
                         "queued" if runnable else "proposal_only",
                         stamp, prior["assignment_id"]),
                    )
            row = conn.execute(
                "SELECT * FROM assignments WHERE source=? AND source_ref=?",
                (source, source_ref),
            ).fetchone()
            conn.execute("COMMIT")
        assert row is not None
        return self._row(row)

    def list_assignments(self, states: tuple[str, ...] | None = None) -> list[Assignment]:
        with self.connect() as conn:
            if states:
                marks = ",".join("?" for _ in states)
                rows = conn.execute(
                    f"SELECT * FROM assignments WHERE state IN ({marks}) ORDER BY priority,created_at",
                    states,
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM assignments ORDER BY priority,created_at"
                ).fetchall()
        return [self._row(row) for row in rows]

    def release_expired_leases(self) -> int:
        now = utcnow()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """
                SELECT assignment_id FROM assignments
                WHERE state='running' AND lease_until IS NOT NULL AND lease_until < ?
                """,
                (now,),
            ).fetchall()
            for row in rows:
                conn.execute(
                    """
                    UPDATE assignments
                    SET state='retry_ready',runnable=1,lease_owner=NULL,lease_until=NULL,
                        blocked_reason='worker_lease_expired',updated_at=?
                    WHERE assignment_id=?
                    """,
                    (now, row["assignment_id"]),
                )
                self._event_conn(conn, row["assignment_id"], "lease_recovered", {})
            conn.execute("COMMIT")
        return len(rows)

    def claim_next(self, *, instance_id: str, lease_seconds: int,
                   work_type: str | None = None) -> Assignment | None:
        stamp = datetime.now(timezone.utc)
        lease_until = (stamp + timedelta(seconds=lease_seconds)).isoformat(timespec="seconds")
        now = stamp.isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            params: list[Any] = []
            extra = ""
            if work_type:
                extra = " AND work_type=?"
                params.append(work_type)
            row = conn.execute(
                f"""
                SELECT * FROM assignments
                WHERE runnable=1 AND state IN ('queued','retry_ready') {extra}
                ORDER BY priority ASC, created_at ASC LIMIT 1
                """,
                params,
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None
            conn.execute(
                """
                UPDATE assignments
                SET state='running',lease_owner=?,lease_until=?,
                    attempt_count=attempt_count+1,blocked_reason=NULL,updated_at=?
                WHERE assignment_id=? AND state=?
                """,
                (instance_id, lease_until, now, row["assignment_id"], row["state"]),
            )
            self._event_conn(conn, row["assignment_id"], "assignment_claimed", {
                "instance_id": instance_id, "lease_until": lease_until,
            })
            row = conn.execute(
                "SELECT * FROM assignments WHERE assignment_id=?",
                (row["assignment_id"],),
            ).fetchone()
            conn.execute("COMMIT")
        assert row is not None
        return self._row(row)

    def update_state(self, assignment_id: str, *, state: str, runnable: bool,
                     completion_percent: int, reason: str | None = None,
                     payload: dict[str, Any] | None = None) -> None:
        if not 0 <= completion_percent <= 100:
            raise ValueError("completion_percent must be between 0 and 100")
        if state == "complete" and completion_percent != 100:
            raise ValueError("complete assignments must be 100 percent")
        stamp = utcnow()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                UPDATE assignments
                SET state=?,runnable=?,completion_percent=?,blocked_reason=?,
                    lease_owner=NULL,lease_until=NULL,updated_at=?
                WHERE assignment_id=?
                """,
                (state, int(runnable), completion_percent, reason, stamp, assignment_id),
            )
            self._event_conn(conn, assignment_id, "state_changed", {
                "state": state, "runnable": runnable,
                "completion_percent": completion_percent, "reason": reason,
                **(payload or {}),
            })
            conn.execute("COMMIT")

    def begin_idempotent_action(self, *, key: str, assignment_id: str, action: str) -> bool:
        stamp = utcnow()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT status FROM idempotency WHERE idempotency_key=?", (key,)
            ).fetchone()
            if existing is not None:
                conn.execute("COMMIT")
                return False
            conn.execute(
                """
                INSERT INTO idempotency(
                  idempotency_key,assignment_id,action,status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?)
                """,
                (key, assignment_id, action, "started", stamp, stamp),
            )
            conn.execute("COMMIT")
        return True

    def finish_idempotent_action(self, *, key: str, result: Any) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE idempotency
                SET status='complete',result_digest=?,updated_at=?
                WHERE idempotency_key=?
                """,
                (digest_json(result), utcnow(), key),
            )

    def record_health(self, *, component: str, instance_id: str,
                      status: str, details: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO component_health(component,instance_id,status,checked_at,details_json)
                VALUES(?,?,?,?,?)
                ON CONFLICT(component) DO UPDATE SET
                  instance_id=excluded.instance_id,status=excluded.status,
                  checked_at=excluded.checked_at,details_json=excluded.details_json
                """,
                (component, instance_id, status, utcnow(), canonical_json(details)),
            )

    def event(self, assignment_id: str | None, kind: str, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            self._event_conn(conn, assignment_id, kind, payload)

    @staticmethod
    def _event_conn(conn: sqlite3.Connection, assignment_id: str | None,
                    kind: str, payload: dict[str, Any]) -> None:
        conn.execute(
            "INSERT INTO events(assignment_id,kind,created_at,payload_json) VALUES(?,?,?,?)",
            (assignment_id, kind, utcnow(), canonical_json(payload)),
        )
