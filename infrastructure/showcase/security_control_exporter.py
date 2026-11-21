#!/usr/bin/env python3
"""Bounded, read-only security audit projection for Prometheus.

Scrapes NEVER execute SQLite queries. An independent worker incrementally scans
the append-only audit by indexed rowid and persists ONLY aggregate counters.
Incomplete, stale, or broken projections fail closed rather than publishing
partial counts as complete. Nothing creates an index or mutates the audit DB.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from collections import Counter
from contextlib import closing
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

DB = Path(os.environ.get("JASON_ORCHESTRATION_EVENTS_DB", "/var/lib/jason/openclaw/orchestration-events.sqlite3"))
HOST = os.environ.get("JASON_SECURITY_CONTROL_EXPORTER_HOST", "0.0.0.0")
PORT = int(os.environ.get("JASON_SECURITY_CONTROL_EXPORTER_PORT", "9471"))
STATE = Path(os.environ.get("JASON_SECURITY_CONTROL_STATE_FILE", "/var/lib/jason-security-control-exporter/checkpoint.json"))
BATCH_SIZE = 5_000
POLL_SECONDS = 0.50
STALE_AFTER_SECONDS = 60.0

SAFE_TERMINATION_REASONS = {
    "client_context_required",
    "no_eligible_provider",
    "authority_context_required",
    "approval_required",
    "provider_authority_denied",
    "execution_plan_binding_required",
    "execution_plan_authorization_rejected",
    "execution_plan_mismatch",
}

SECURITY_EVENT_TYPES = (
    "orchestration.execution_plan.denied",
    "orchestration.idempotency.deduplicated",
    "orchestration.authority_context.denied",
    "orchestration.approval.consumed",
    "orchestration.request.terminated",
)

def _safe_reason(payload: dict) -> str | None:
    values = payload.get("reason_codes")
    if isinstance(values, list):
        for value in values:
            reason = str(value or "").strip().lower()
            if reason in SAFE_TERMINATION_REASONS:
                return reason
    value = str(payload.get("reason_code") or "").strip().lower()
    if value in SAFE_TERMINATION_REASONS:
        return value
    return None

def _record_event(event_type: str, raw: str | None, controls: Counter[str], terminations: Counter[str]) -> int:
    names = {
        "orchestration.execution_plan.denied": "execution_plan_denied",
        "orchestration.idempotency.deduplicated": "idempotency_deduplicated",
        "orchestration.authority_context.denied": "authority_context_denied",
        "orchestration.approval.consumed": "approval_consumed",
    }
    control = names.get(event_type)
    if control:
        controls[control] += 1
    if event_type not in ("orchestration.execution_plan.denied", "orchestration.request.terminated"):
        return 0
    try:
        payload = json.loads(raw) if raw else {}
        if not isinstance(payload, dict):
            payload = {}
    except (TypeError, ValueError):
        payload = {}
    if event_type == "orchestration.execution_plan.denied":
        return int(payload.get("provider_invoked") is False)
    reason = _safe_reason(payload)
    if reason:
        terminations[reason] += 1
    return 0

def _source_identity(db: Path) -> tuple[int, int]:
    st = db.stat()
    return st.st_dev, st.st_ino

def _digest_event_id(value: Any) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()

class SecurityAuditProjection:
    def __init__(self, db: Path, state: Path | None = None) -> None:
        self.db = Path(db)
        self.state = Path(state) if state is not None else None
        self.lock = threading.Lock()
        self.cursor = 0
        self.controls: Counter[str] = Counter()
        self.terminations: Counter[str] = Counter()
        self.blocked = 0
        self.source_id: tuple[int, int] | None = None
        self.cursor_event_hash: str | None = None
        self.complete = False
        self.last_ok = 0.0
        self.persist_ok = False
        self.error = False
        self._batches_since_save = 0
        self._restore()

    def _connect(self):
        # A distinct short read transaction per bounded batch; no audit writes.
        # The DB is WAL-backed, so concurrent audit writers can proceed.
        uri = "file:" + str(self.db.resolve()) + "?mode=ro"
        return sqlite3.connect(uri, uri=True, timeout=0.2)

    def _restore(self) -> None:
        if self.state is None or not self.state.is_file() or not self.db.exists():
            return
        try:
            saved = json.loads(self.state.read_text(encoding="utf-8"))
            if saved.get("schema") != 1:
                raise ValueError("checkpoint schema invalid")
            if tuple(saved["source_id"]) != _source_identity(self.db):
                raise ValueError("checkpoint source identity mismatch")
            cursor = int(saved["cursor"])
            if cursor < 0:
                raise ValueError("checkpoint cursor negative")
            with closing(self._connect()) as c:
                high = c.execute("SELECT MAX(rowid) FROM orchestration_events").fetchone()[0] or 0
                if cursor > high:
                    raise ValueError("checkpoint cursor ahead of audit")
                if cursor:
                    item = c.execute("SELECT event_id FROM orchestration_events WHERE rowid=?", (cursor,)).fetchone()
                    if item is None or _digest_event_id(item[0]) != saved["cursor_event_hash"]:
                        raise ValueError("checkpoint final event hash mismatch")
            controls = Counter(saved["controls"])
            terminations = Counter(saved["terminations"])
            if not all(type(v) is int and v >= 0 for v in (*controls.values(), *terminations.values())):
                raise ValueError("checkpoint counters malformed")
            if not set(terminations).issubset(SAFE_TERMINATION_REASONS):
                raise ValueError("checkpoint reason label not permitted")
            if not set(controls).issubset({
                "execution_plan_denied", "idempotency_deduplicated",
                "authority_context_denied", "approval_consumed",
            }):
                raise ValueError("checkpoint control label not permitted")
            blocked = int(saved["blocked"])
            if blocked < 0:
                raise ValueError("checkpoint blocked count negative")
        except (OSError, ValueError, KeyError, TypeError, AssertionError, sqlite3.Error):
            return  # fail-closed: rebuild from rowid zero, never trust broken cache
        self.cursor = cursor
        self.controls = controls
        self.terminations = terminations
        self.blocked = blocked
        self.source_id = _source_identity(self.db)
        self.cursor_event_hash = saved.get("cursor_event_hash")
        self.persist_ok = True

    def _save(self, data: dict[str, Any]) -> None:
        if self.state is None:
            self.persist_ok = True
            return
        self.state.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temp = self.state.with_name(self.state.name + ".tmp")
        with temp.open("w", encoding="utf-8") as file:
            json.dump(data, file, sort_keys=True)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, self.state)

    def advance(self, limit: int = BATCH_SIZE) -> int:
        if not (1 <= limit <= 50_000):
            raise ValueError("bounded scan limit must be <= 50000")
        try:
            source = _source_identity(self.db)
            if self.source_id is not None and source != self.source_id:
                # Never mix totals across a replaced audit database.
                with self.lock:
                    self.cursor = 0
                    self.controls.clear()
                    self.terminations.clear()
                    self.blocked = 0
                    self.cursor_event_hash = None
                    self.complete = False
            current = self.cursor
            with closing(self._connect()) as c:
                high = c.execute("SELECT MAX(rowid) FROM orchestration_events").fetchone()[0] or 0
                if high < current:
                    # Truncation/rewrites are not append-only; mark unavailable.
                    raise ValueError("audit rowid decreased: manual reconciliation required")
                # SQLite's rowid range lookup is an existing primary B-tree,
                # not a full scan or a new event_type index.
                rows = c.execute(
                    """SELECT rowid,event_id,event_type,
                          CASE WHEN event_type IN (
                            'orchestration.execution_plan.denied',
                            'orchestration.request.terminated'
                          ) THEN payload ELSE NULL END
                       FROM orchestration_events
                       WHERE rowid > ? ORDER BY rowid LIMIT ?""",
                    (current, limit),
                ).fetchall()
            controls: Counter[str] = Counter()
            terminations: Counter[str] = Counter()
            blocked = 0
            for _, _, kind, payload in rows:
                if kind in SECURITY_EVENT_TYPES:
                    blocked += _record_event(kind, payload, controls, terminations)
            snapshot = None
            with self.lock:
                self.source_id = source
                self.cursor = rows[-1][0] if rows else current
                if rows:
                    self.cursor_event_hash = _digest_event_id(rows[-1][1])
                self.controls.update(controls)
                self.terminations.update(terminations)
                self.blocked += blocked
                self.complete = self.cursor >= high
                self.last_ok = time.monotonic()
                self.error = False
                self._batches_since_save += 1
                if self.complete or self._batches_since_save >= 5:
                    snapshot = {
                        "schema": 1,
                        "source_id": list(self.source_id),
                        "cursor": self.cursor,
                        "cursor_event_hash": self.cursor_event_hash,
                        "controls": dict(self.controls),
                        "terminations": dict(self.terminations),
                        "blocked": self.blocked,
                    }
                    self._batches_since_save = 0
            if snapshot is not None:
                # fsync can stall under disk pressure. Never hold the HTTP
                # rendering lock while persisting an independent checkpoint.
                try:
                    self._save(snapshot)
                    self.persist_ok = True
                except OSError:
                    self.persist_ok = False
            return len(rows)
        except (OSError, sqlite3.Error, ValueError):
            with self.lock:
                self.complete = False
                self.error = True
                self.last_ok = 0.0
            return 0

    def render(self) -> str:
        # This method is deliberately free of ANY database or filesystem I/O.
        with self.lock:
            ready = (self.complete and not self.error and
                     self.last_ok and time.monotonic() - self.last_ok <= STALE_AFTER_SECONDS)
            available = int(bool(ready))
            controls = self.controls.copy() if ready else Counter()
            terminations = self.terminations.copy() if ready else Counter()
            blocked = self.blocked if ready else 0
            cursor = self.cursor
            complete = int(bool(self.complete))
            persist = int(self.persist_ok)
        lines = [
            "# HELP jason_security_control_audit_available Full up-to-date security audit projection is readable and complete.",
            "# TYPE jason_security_control_audit_available gauge",
            f"jason_security_control_audit_available {available}",
            "# HELP jason_security_control_projection_complete Backfill has reached the observed audit head.",
            "# TYPE jason_security_control_projection_complete gauge",
            f"jason_security_control_projection_complete {complete}",
            "# HELP jason_security_control_projection_cursor Last covered audit rowid (progress, not total rows).",
            "# TYPE jason_security_control_projection_cursor gauge",
            f"jason_security_control_projection_cursor {cursor}",
            "# HELP jason_security_control_projection_persist_ok Projection checkpoint can be persisted for restart recovery.",
            "# TYPE jason_security_control_projection_persist_ok gauge",
            f"jason_security_control_projection_persist_ok {persist}",
            "# HELP jason_security_control_events Aggregate secret-safe security control event counts from durable orchestration audit.",
            "# TYPE jason_security_control_events gauge",
        ]
        for control, count in sorted(controls.items()):
            lines.append(f'jason_security_control_events{{control="{control}"}} {count}')
        lines += [
            "# HELP jason_security_request_terminations Aggregate fail-closed request termination counts by approved low-cardinality reason.",
            "# TYPE jason_security_request_terminations gauge",
        ]
        for reason, count in sorted(terminations.items()):
            lines.append(f'jason_security_request_terminations{{reason="{reason}"}} {count}')
        lines += [
            "# HELP jason_security_provider_invocations_blocked Execution-plan denials proven to occur before provider invocation.",
            "# TYPE jason_security_provider_invocations_blocked gauge",
            f"jason_security_provider_invocations_blocked {blocked}",
            "",
        ]
        return "\n".join(lines)

_projection: SecurityAuditProjection | None = None

def collect_counts(db: Path = DB) -> tuple[int, Counter[str], Counter[str], int]:
    """Compatibility helper for small unit fixtures; production uses _projection."""
    view = SecurityAuditProjection(db)
    # Do not synchronously process an unbounded database on a metrics request.
    view.advance()
    with view.lock:
        if not view.complete or view.error:
            return 0, Counter(), Counter(), 0
        return 1, view.controls.copy(), view.terminations.copy(), view.blocked

def metrics(db: Path = DB) -> str:
    global _projection
    if _projection is not None and Path(db) == DB:
        return _projection.render()
    # Unit fixture path: at most one bounded batch, fail closed if unfinished.
    view = SecurityAuditProjection(db)
    view.advance()
    return view.render()

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in {"/", "/metrics"}:
            self.send_response(404)
            self.end_headers()
            return
        body = metrics().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass

def _run_projection() -> None:
    assert _projection is not None
    while True:
        n = _projection.advance()
        # Quiet after catching up. Consume small bounded batches on backlog.
        time.sleep(2.0 if _projection.complete and n == 0 else POLL_SECONDS)

if __name__ == "__main__":
    _projection = SecurityAuditProjection(DB, STATE)
    worker = threading.Thread(target=_run_projection, name="security-audit-projection", daemon=True)
    worker.start()
    HTTPServer((HOST, PORT), Handler).serve_forever()
