#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

DB = Path(os.environ.get("JASON_ORCHESTRATION_EVENTS_DB", "/var/lib/jason/openclaw/orchestration-events.sqlite3"))
HOST = os.environ.get("JASON_SECURITY_CONTROL_EXPORTER_HOST", "0.0.0.0")
PORT = int(os.environ.get("JASON_SECURITY_CONTROL_EXPORTER_PORT", "9471"))

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


def collect_counts(db: Path = DB) -> tuple[int, Counter[str], Counter[str], int]:
    available = 0
    controls: Counter[str] = Counter()
    terminations: Counter[str] = Counter()
    blocked_provider_invocations = 0
    if not db.exists():
        return available, controls, terminations, blocked_provider_invocations
    try:
        connection = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        rows = connection.execute("select event_type, payload from orchestration_events").fetchall()
        connection.close()
        available = 1
    except sqlite3.Error:
        return 0, controls, terminations, blocked_provider_invocations

    for event_type, raw in rows:
        if event_type == "orchestration.execution_plan.denied":
            controls["execution_plan_denied"] += 1
        elif event_type == "orchestration.idempotency.deduplicated":
            controls["idempotency_deduplicated"] += 1
        elif event_type == "orchestration.authority_context.denied":
            controls["authority_context_denied"] += 1
        elif event_type == "orchestration.approval.consumed":
            controls["approval_consumed"] += 1

        try:
            payload = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
        if event_type == "orchestration.execution_plan.denied" and payload.get("provider_invoked") is False:
            blocked_provider_invocations += 1
        if event_type == "orchestration.request.terminated":
            reason = _safe_reason(payload)
            if reason:
                terminations[reason] += 1
    return available, controls, terminations, blocked_provider_invocations


def metrics(db: Path = DB) -> str:
    available, controls, terminations, blocked = collect_counts(db)
    lines = [
        "# HELP jason_security_control_audit_available Whether the orchestration audit store is readable.",
        "# TYPE jason_security_control_audit_available gauge",
        f"jason_security_control_audit_available {available}",
        "# HELP jason_security_control_events Aggregate secret-safe security control event counts from durable orchestration audit.",
        "# TYPE jason_security_control_events gauge",
    ]
    for control, count in sorted(controls.items()):
        lines.append(f'jason_security_control_events{{control="{control}"}} {count}')
    lines.extend([
        "# HELP jason_security_request_terminations Aggregate fail-closed request termination counts by approved low-cardinality reason.",
        "# TYPE jason_security_request_terminations gauge",
    ])
    for reason, count in sorted(terminations.items()):
        lines.append(f'jason_security_request_terminations{{reason="{reason}"}} {count}')
    lines.extend([
        "# HELP jason_security_provider_invocations_blocked Execution-plan denials proven to occur before provider invocation.",
        "# TYPE jason_security_provider_invocations_blocked gauge",
        f"jason_security_provider_invocations_blocked {blocked}",
        "",
    ])
    return "\n".join(lines)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in {"/", "/metrics"}:
            self.send_response(404); self.end_headers(); return
        body = metrics().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    HTTPServer((HOST, PORT), Handler).serve_forever()
