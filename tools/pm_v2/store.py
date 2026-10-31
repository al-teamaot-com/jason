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
                    next_eligible_at TEXT,
                    paused_from_state TEXT,
                    paused_from_runnable INTEGER,
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
                CREATE TABLE IF NOT EXISTS validation_checks (
                    assignment_id TEXT NOT NULL,
                    check_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    checked_at TEXT NOT NULL,
                    PRIMARY KEY(assignment_id, check_name),
                    FOREIGN KEY(assignment_id) REFERENCES assignments(assignment_id)
                );
                CREATE TABLE IF NOT EXISTS nodes (
                    node_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    capabilities_json TEXT NOT NULL,
                    capacity_json TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS component_runs (
                    component TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    state TEXT NOT NULL,
                    next_due_at TEXT,
                    lease_owner TEXT,
                    lease_until TEXT,
                    consecutive_failures INTEGER NOT NULL DEFAULT 0,
                    last_return_code INTEGER,
                    last_started_at TEXT,
                    last_finished_at TEXT,
                    updated_at TEXT NOT NULL
                );
                """
            )
            columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(assignments)").fetchall()
            }
            if "next_eligible_at" not in columns:
                conn.execute("ALTER TABLE assignments ADD COLUMN next_eligible_at TEXT")
            if "paused_from_state" not in columns:
                conn.execute("ALTER TABLE assignments ADD COLUMN paused_from_state TEXT")
            if "paused_from_runnable" not in columns:
                conn.execute("ALTER TABLE assignments ADD COLUMN paused_from_runnable INTEGER")

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

    def get_assignment(self, assignment_id: str) -> Assignment | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM assignments WHERE assignment_id=?",
                (assignment_id,),
            ).fetchone()
        return self._row(row) if row is not None else None

    def apply_owner_control(
        self,
        *,
        assignment_id: str,
        action: str,
        principal_id: str,
        request_id: str,
        priority: int | None = None,
    ) -> dict[str, Any]:
        action = action.strip().casefold()
        if action not in {"priority", "pause", "resume", "cancel"}:
            raise ValueError("unsupported PM V2 control action")
        if not principal_id.strip() or not request_id.strip():
            raise ValueError("control principal and request ID are required")
        stamp = utcnow()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM assignments WHERE assignment_id=?",
                (assignment_id,),
            ).fetchone()
            if row is None:
                conn.execute("ROLLBACK")
                raise LookupError("PM_V2_ASSIGNMENT_NOT_FOUND")
            current = str(row["state"])
            if action == "priority":
                if type(priority) is not int or not 0 <= priority <= 99:
                    conn.execute("ROLLBACK")
                    raise ValueError("priority must be an integer from 0 to 99")
                if current in TERMINAL_STATES:
                    conn.execute("ROLLBACK")
                    raise ValueError("terminal assignment priority cannot change")
                conn.execute(
                    "UPDATE assignments SET priority=?,updated_at=? WHERE assignment_id=?",
                    (priority, stamp, assignment_id),
                )
                result_state = current
            elif action == "pause":
                if current in TERMINAL_STATES or current == "cancel_requested":
                    conn.execute("ROLLBACK")
                    raise ValueError("assignment cannot be paused in current state")
                if current in {"paused", "pause_requested"}:
                    result_state = current
                elif current == "running":
                    conn.execute(
                        """
                        UPDATE assignments
                        SET state='pause_requested',runnable=0,
                            paused_from_state='running',paused_from_runnable=0,
                            blocked_reason='owner_pause_requested',updated_at=?
                        WHERE assignment_id=?
                        """,
                        (stamp, assignment_id),
                    )
                    result_state = "pause_requested"
                else:
                    conn.execute(
                        """
                        UPDATE assignments
                        SET state='paused',runnable=0,paused_from_state=?,
                            paused_from_runnable=?,blocked_reason='paused_by_owner',
                            lease_owner=NULL,lease_until=NULL,updated_at=?
                        WHERE assignment_id=?
                        """,
                        (current, int(row["runnable"]), stamp, assignment_id),
                    )
                    result_state = "paused"
            elif action == "resume":
                if current != "paused":
                    conn.execute("ROLLBACK")
                    raise ValueError("only a paused assignment can be resumed")
                previous = str(row["paused_from_state"] or "queued")
                if previous in {"running", "pause_requested", "cancel_requested"}:
                    previous = "retry_ready"
                runnable = bool(row["paused_from_runnable"])
                if previous in {"queued", "retry_ready"}:
                    runnable = True
                conn.execute(
                    """
                    UPDATE assignments
                    SET state=?,runnable=?,paused_from_state=NULL,
                        paused_from_runnable=NULL,blocked_reason=NULL,
                        next_eligible_at=NULL,updated_at=?
                    WHERE assignment_id=?
                    """,
                    (previous, int(runnable), stamp, assignment_id),
                )
                result_state = previous
            else:
                if current in TERMINAL_STATES:
                    result_state = current
                elif current in {"running", "pause_requested"}:
                    conn.execute(
                        """
                        UPDATE assignments
                        SET state='cancel_requested',runnable=0,
                            blocked_reason='owner_cancel_requested',updated_at=?
                        WHERE assignment_id=?
                        """,
                        (stamp, assignment_id),
                    )
                    result_state = "cancel_requested"
                else:
                    conn.execute(
                        """
                        UPDATE assignments
                        SET state='cancelled',runnable=0,
                            lease_owner=NULL,lease_until=NULL,next_eligible_at=NULL,
                            blocked_reason='cancelled_by_owner',updated_at=?
                        WHERE assignment_id=?
                        """,
                        (stamp, assignment_id),
                    )
                    result_state = "cancelled"
            self._event_conn(conn, assignment_id, "owner_control_applied", {
                "action": action,
                "principal_id": principal_id,
                "request_id": request_id,
                "priority": priority,
                "result_state": result_state,
            })
            conn.execute("COMMIT")
        return {
            "assignment_id": assignment_id,
            "action": action,
            "state": result_state,
            "priority": priority,
        }

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
            params: list[Any] = [now]
            extra = ""
            if work_type:
                extra = " AND work_type=?"
                params.append(work_type)
            row = conn.execute(
                f"""
                SELECT * FROM assignments
                WHERE runnable=1 AND state IN ('queued','retry_ready')
                  AND (next_eligible_at IS NULL OR next_eligible_at <= ?) {extra}
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
                SET state='running',lease_owner=?,lease_until=?,next_eligible_at=NULL,
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
                     payload: dict[str, Any] | None = None,
                     next_eligible_at: str | None = None) -> None:
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
                    lease_owner=NULL,lease_until=NULL,next_eligible_at=?,updated_at=?
                WHERE assignment_id=?
                """,
                (state, int(runnable), completion_percent, reason,
                 next_eligible_at, stamp, assignment_id),
            )
            self._event_conn(conn, assignment_id, "state_changed", {
                "state": state, "runnable": runnable,
                "completion_percent": completion_percent, "reason": reason,
                **(payload or {}),
            })
            conn.execute("COMMIT")

    def schedule_retry(self, assignment_id: str, *, completion_percent: int,
                       reason: str, delay_seconds: int) -> None:
        if delay_seconds < 1:
            raise ValueError("delay_seconds must be positive")
        due = (
            datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
        ).isoformat(timespec="seconds")
        self.update_state(
            assignment_id,
            state="retry_ready",
            runnable=True,
            completion_percent=completion_percent,
            reason=reason,
            next_eligible_at=due,
            payload={"retry_due_at": due},
        )

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

    def health_snapshot(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT component,instance_id,status,checked_at,details_json "
                "FROM component_health ORDER BY component"
            ).fetchall()
        return [
            {
                "component": row["component"],
                "instance_id": row["instance_id"],
                "status": row["status"],
                "checked_at": row["checked_at"],
                "details": json.loads(row["details_json"]),
            }
            for row in rows
        ]

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


    def register_component(self, *, component: str, owner: str) -> None:
        stamp = utcnow()
        initial = "external_v1" if owner == "v1" else "ready"
        with self.connect() as conn:
            row = conn.execute(
                "SELECT owner,state FROM component_runs WHERE component=?",
                (component,),
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO component_runs(
                      component,owner,state,next_due_at,updated_at
                    ) VALUES(?,?,?,?,?)
                    """,
                    (component, owner, initial, stamp if owner == "pm_v2" else None, stamp),
                )
            elif row["owner"] != owner:
                conn.execute(
                    """
                    UPDATE component_runs
                    SET owner=?,state=?,next_due_at=?,lease_owner=NULL,
                        lease_until=NULL,consecutive_failures=0,updated_at=?
                    WHERE component=?
                    """,
                    (owner, initial, stamp if owner == "pm_v2" else None, stamp, component),
                )
                self._event_conn(conn, None, "component_owner_changed", {
                    "component": component, "owner": owner,
                })

    def claim_due_component(self, *, component: str, instance_id: str,
                            lease_seconds: int) -> bool:
        now_dt = datetime.now(timezone.utc)
        stamp = now_dt.isoformat(timespec="seconds")
        lease_until = (now_dt + timedelta(seconds=lease_seconds)).isoformat(timespec="seconds")
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM component_runs WHERE component=?",
                (component,),
            ).fetchone()
            if row is None or row["owner"] != "pm_v2":
                conn.execute("COMMIT")
                return False
            if row["state"] == "running" and row["lease_until"] and row["lease_until"] >= stamp:
                conn.execute("COMMIT")
                return False
            if row["next_due_at"] and row["next_due_at"] > stamp:
                conn.execute("COMMIT")
                return False
            conn.execute(
                """
                UPDATE component_runs
                SET state='running',lease_owner=?,lease_until=?,last_started_at=?,
                    updated_at=?
                WHERE component=?
                """,
                (instance_id, lease_until, stamp, stamp, component),
            )
            conn.execute("COMMIT")
            return True

    def finish_component(self, *, component: str, return_code: int,
                         next_due_at: str, state: str,
                         consecutive_failures: int) -> None:
        stamp = utcnow()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE component_runs
                SET state=?,next_due_at=?,lease_owner=NULL,lease_until=NULL,
                    consecutive_failures=?,last_return_code=?,
                    last_finished_at=?,updated_at=?
                WHERE component=?
                """,
                (state, next_due_at, consecutive_failures, return_code,
                 stamp, stamp, component),
            )

    def component_snapshot(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM component_runs ORDER BY component"
            ).fetchall()
        return [dict(row) for row in rows]

    def record_validation(self, *, assignment_id: str, check_name: str,
                          status: str, evidence: dict[str, Any]) -> None:
        if status not in {"pass", "fail", "unknown", "pending", "not_applicable"}:
            raise ValueError("unsupported validation status")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO validation_checks(
                  assignment_id,check_name,status,evidence_json,checked_at
                ) VALUES(?,?,?,?,?)
                ON CONFLICT(assignment_id,check_name) DO UPDATE SET
                  status=excluded.status,evidence_json=excluded.evidence_json,
                  checked_at=excluded.checked_at
                """,
                (assignment_id, check_name, status, canonical_json(evidence), utcnow()),
            )

    def validation_checks(self, assignment_id: str) -> dict[str, dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT check_name,status,evidence_json,checked_at "
                "FROM validation_checks WHERE assignment_id=? ORDER BY check_name",
                (assignment_id,),
            ).fetchall()
        return {
            row["check_name"]: {
                "status": row["status"],
                "evidence": json.loads(row["evidence_json"]),
                "checked_at": row["checked_at"],
            }
            for row in rows
        }

    def heartbeat_node(self, *, node_id: str, status: str,
                       capabilities: dict[str, Any], capacity: dict[str, Any]) -> None:
        if not node_id.strip():
            raise ValueError("node_id must be non-empty")
        if status not in {"healthy", "degraded", "offline", "draining"}:
            raise ValueError("invalid node status")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO nodes(node_id,status,capabilities_json,capacity_json,last_seen_at)
                VALUES(?,?,?,?,?)
                ON CONFLICT(node_id) DO UPDATE SET
                  status=excluded.status,
                  capabilities_json=excluded.capabilities_json,
                  capacity_json=excluded.capacity_json,
                  last_seen_at=excluded.last_seen_at
                """,
                (node_id, status, canonical_json(capabilities),
                 canonical_json(capacity), utcnow()),
            )

    def node_snapshot(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT node_id,status,capabilities_json,capacity_json,last_seen_at "
                "FROM nodes ORDER BY node_id"
            ).fetchall()
        return [
            {
                "node_id": row["node_id"],
                "status": row["status"],
                "capabilities": json.loads(row["capabilities_json"]),
                "capacity": json.loads(row["capacity_json"]),
                "last_seen_at": row["last_seen_at"],
            }
            for row in rows
        ]

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
