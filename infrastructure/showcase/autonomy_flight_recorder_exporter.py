#!/usr/bin/env python3
"""Read-only Project Jason autonomous action flight recorder exporter.

Surfaces:
- /metrics: low-cardinality Prometheus summary metrics only.
- /api/actions: sanitized autonomous execution records for Grafana Infinity.
- /api/actions/<execution_id>: one sanitized detail record.
- /healthz: exporter health.

The exporter never mutates Jason/provider state and never treats Grafana as an
authority source.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from typing import Any

HOST = os.environ.get("JASON_AUTONOMY_FLIGHT_RECORDER_HOST", "0.0.0.0")
PORT = int(os.environ.get("JASON_AUTONOMY_FLIGHT_RECORDER_PORT", "9475"))
EVENT_DB = Path(os.environ.get("JASON_ORCHESTRATION_EVENTS_DB", "/var/lib/jason/openclaw/orchestration-events.sqlite3"))
LEDGER_DB = Path(os.environ.get("JASON_GOVERNED_EXECUTION_DB", "/var/lib/jason/openclaw/governed-execution.sqlite3"))
AUTHORITY_DB = Path(os.environ.get("JASON_AUTHORITY_DB", "/var/lib/jason/authority/authority.sqlite3"))
SHADOW_DB = Path(os.environ.get("JASON_AUTONOMY_SHADOW_DB", "/var/lib/jason/openclaw/autonomy-shadow.sqlite3"))
PRINCIPAL = os.environ.get("JASON_AUTONOMY_PRINCIPAL", "jason-autonomy-worker")
ENRICHMENT_PATH = Path(os.environ.get("JASON_AUTONOMY_FLIGHT_RECORDER_ENRICHMENT", "/app/flight_recorder_enrichment.json"))

SENSITIVE_KEY = re.compile(r"(?i)(secret|password|passwd|token|api[_-]?key|credential|authorization|cookie|private[_-]?key|client[_-]?secret)")
SENSITIVE_TEXT = re.compile(r"(?i)(bearer\s+[A-Za-z0-9._~+/=-]{12,}|basic\s+[A-Za-z0-9+/=]{12,})")
MAX_STRING = 8000


def _db(path: Path) -> sqlite3.Connection:
    # governed-execution.sqlite3 is mounted read-only inside the observability
    # container and its normal SQLite read-only open still attempts lock/journal
    # handling that fails on the bind mount. It uses DELETE journaling in
    # production, so a fresh immutable connection is safe for this evidence-only
    # exporter and cannot create lock/journal files. Other stores retain normal
    # mode=ro semantics so WAL sidecars remain visible where required.
    suffix = "?mode=ro&immutable=1" if path == LEDGER_DB else "?mode=ro"
    c = sqlite3.connect(f"file:{path}{suffix}", uri=True, timeout=3.0)
    c.row_factory = sqlite3.Row
    return c


def _json(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list, int, float, bool)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return default if default is not None else value


def _sanitize(value: Any, key: str | None = None) -> Any:
    if key and SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _sanitize(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize(v) for v in value[:250]]
    if isinstance(value, str):
        text = SENSITIVE_TEXT.sub("[REDACTED]", value)
        return text if len(text) <= MAX_STRING else text[:MAX_STRING] + "...[truncated]"
    return value


def _iso(value: Any) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except Exception:
        return str(value)


def _target_from_plan(plan: dict[str, Any]) -> dict[str, Any]:
    args = plan.get("arguments") if isinstance(plan, dict) else None
    payload = args.get("payload") if isinstance(args, dict) else None
    payload = payload if isinstance(payload, dict) else {}
    normalized_payload = plan.get("normalized_payload") if isinstance(plan, dict) else None
    normalized_payload = normalized_payload if isinstance(normalized_payload, dict) else {}
    selectors = plan.get("target_selectors") if isinstance(plan, dict) else None
    selectors = selectors if isinstance(selectors, dict) else {}
    ticket_id = (
        payload.get("ticketID") or payload.get("ticketId") or payload.get("id")
        or normalized_payload.get("ticketID") or normalized_payload.get("ticketId")
        or selectors.get("ticket_id") or selectors.get("ticketID")
        or (plan.get("resource_identifier") if plan.get("resource_type") in {"service_ticket", "service_ticket_note"} else None)
    )
    ticket_number = (payload.get("ticketNumber") or normalized_payload.get("ticketNumber") or selectors.get("ticketNumber"))
    configuration_item_id = (payload.get("configurationItemID") or normalized_payload.get("configurationItemID") or selectors.get("configurationItemID"))
    device_name = (payload.get("deviceName") or normalized_payload.get("deviceName") or selectors.get("deviceName") or selectors.get("hostname"))
    device = ((args.get("device_uid") if isinstance(args, dict) else None) or (args.get("device_id") if isinstance(args, dict) else None) or (args.get("endpoint_uid") if isinstance(args, dict) else None) or normalized_payload.get("device_uid") or normalized_payload.get("device_id") or normalized_payload.get("endpoint_uid") or selectors.get("device_uid") or selectors.get("device_id") or selectors.get("endpoint_uid") or device_name or configuration_item_id or (plan.get("resource_identifier") if str(plan.get("resource_type") or "").startswith("endpoint") else None))
    client_id = ((plan.get("client_id") if isinstance(plan, dict) else None) or (args.get("client_id") if isinstance(args, dict) else None) or (args.get("companyID") if isinstance(args, dict) else None) or payload.get("companyID") or normalized_payload.get("companyID") or selectors.get("companyID"))
    client_name = payload.get("companyName") or normalized_payload.get("companyName") or selectors.get("companyName")
    return {
        "ticket_id": str(ticket_id) if ticket_id not in (None, "") else None,
        "ticket_number": str(ticket_number) if ticket_number not in (None, "") else None,
        "device": str(device) if device not in (None, "") else None,
        "device_name": str(device_name) if device_name not in (None, "") else None,
        "configuration_item_id": str(configuration_item_id) if configuration_item_id not in (None, "") else None,
        "client_id": str(client_id) if client_id not in (None, "") else None,
        "client_name": str(client_name) if client_name not in (None, "") else None,
    }




def _display_time(value: Any) -> str:
    if not value:
        return "Unknown time"
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(ZoneInfo("America/New_York"))
        return dt.strftime("%m/%d/%Y %I:%M:%S %p %Z")
    except Exception:
        return str(value)


def _first_present(mapping: Any, *keys: str) -> Any:
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _action_input(plan: dict[str, Any]) -> Any:
    args = plan.get("arguments") if isinstance(plan, dict) else {}
    args = args if isinstance(args, dict) else {}
    normalized = plan.get("normalized_payload") if isinstance(plan, dict) else {}
    normalized = normalized if isinstance(normalized, dict) else {}
    payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
    for source in (args, normalized, payload):
        value = _first_present(source, "command", "script", "componentName", "component_name", "name", "title", "description")
        if value not in (None, ""):
            return value
    if normalized:
        return normalized
    return args or None


def _provider_output(result: dict[str, Any]) -> Any:
    output = result.get("output") if isinstance(result, dict) else None
    data = output.get("data") if isinstance(output, dict) and isinstance(output.get("data"), dict) else output
    if isinstance(data, dict):
        for key in ("stdout", "output", "result", "message", "description", "stderr"):
            value = data.get(key)
            if value not in (None, "", [], {}):
                return value
        # Remove verification metadata from the human-facing provider return summary.
        compact = {k: v for k, v in data.items() if k != "jasonVerification"}
        if compact:
            return compact
    if data not in (None, "", [], {}):
        return data
    return None


def _timeline(*, row: dict[str, Any], terminal: dict[str, Any] | None, plan: dict[str, Any], result: dict[str, Any], action_name: str, target: dict[str, Any], state: str, failure_reason: str | None, verification: dict[str, Any]) -> list[dict[str, Any]]:
    started = row.get("created_at")
    finished = terminal.get("occurred_at") if isinstance(terminal, dict) else row.get("consumed_at") or started
    action_input = _sanitize(_action_input(plan))
    provider_output = _sanitize(_provider_output(result))
    target_bits = []
    if target.get("ticket_number") or target.get("ticket_id"):
        target_bits.append(f"ticket {target.get('ticket_number') or target.get('ticket_id')}")
    if target.get("client_name") or target.get("client_id"):
        target_bits.append(f"client {target.get('client_name') or target.get('client_id')}")
    if target.get("device_name") or target.get("device"):
        target_bits.append(f"device {target.get('device_name') or target.get('device')}")
    target_text = f" against {', '.join(target_bits)}" if target_bits else ""
    entries = [{
        "time": _display_time(started),
        "event": "Ran",
        "message": f"Jason ran {action_name}{target_text}.",
        "input": action_input,
    }]
    if provider_output not in (None, "", [], {}):
        entries.append({
            "time": _display_time(finished),
            "event": "Returned",
            "message": "Provider returned output.",
            "output": provider_output,
        })
    if state == "succeeded":
        entries.append({
            "time": _display_time(finished),
            "event": "Result",
            "message": "Result: Success.",
        })
    else:
        entries.append({
            "time": _display_time(finished),
            "event": "Result",
            "message": f"Result: Failed — {failure_reason or 'Unspecified failure'}.",
        })
    if verification:
        passed = bool(verification.get("readbackVerified"))
        entries.append({
            "time": _display_time(finished),
            "event": "Verification",
            "message": "Verification: Passed." if passed else "Verification: Not passed.",
            "evidence": _sanitize(verification),
        })
    return entries



def _load_enrichment() -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(ENRICHMENT_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(payload, dict):
        return {}
    tickets = payload.get("tickets", payload)
    if not isinstance(tickets, dict):
        return {}
    return {str(k): v for k, v in tickets.items() if isinstance(v, dict)}


def _enrich_target(target: dict[str, Any], enrichment: dict[str, dict[str, Any]]) -> dict[str, Any]:
    out = dict(target)
    ticket_id = out.get("ticket_id")
    record = enrichment.get(str(ticket_id)) if ticket_id not in (None, "") else None
    if not isinstance(record, dict):
        return out
    mapping = {
        "ticket_number": "ticket_number",
        "client_id": "company_id",
        "client_name": "company_name",
        "configuration_item_id": "configuration_item_id",
        "device": "device_id",
        "device_name": "device_name",
        "ticket_title": "ticket_title",
    }
    for target_key, record_key in mapping.items():
        if out.get(target_key) in (None, "") and record.get(record_key) not in (None, ""):
            out[target_key] = str(record[record_key])
    return out


def _human_value(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                item_text = json.dumps(_sanitize(item), separators=(",", ":"), default=str)
            else:
                item_text = _human_value(item)
            parts.append(f"{key}={item_text}")
        return "; ".join(parts)
    if isinstance(value, list):
        return "; ".join(_human_value(v) for v in value)
    return str(value)


def _timeline_rows(record: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    timeline = ((record.get("details") or {}).get("action_timeline") or []) if isinstance(record, dict) else []
    for entry in timeline:
        if not isinstance(entry, dict):
            continue
        rows.append({
            "time": entry.get("time") or "",
            "event": entry.get("event") or "",
            "what_jason_did": entry.get("message") or "",
            "input": _human_value(entry.get("input")),
            "returned": _human_value(entry.get("output")),
            "verification": _human_value(entry.get("evidence")),
        })
    return rows


def _display_playbook(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "—"
    return " ".join(part.capitalize() for part in re.split(r"[_\-]+", text) if part)


def _summary_row(record: dict[str, Any]) -> dict[str, Any]:
    details = record.get("details") if isinstance(record.get("details"), dict) else {}
    target = details.get("target") if isinstance(details.get("target"), dict) else {}
    return {
        "ticket": record.get("ticket") or "",
        "ticket_title": target.get("ticket_title") or "",
        "client": record.get("client") or "",
        "device": record.get("device") or "",
        "playbook": record.get("playbook") or "",
        "playbook_version": record.get("playbook_version") or "",
        "action": record.get("action") or "",
        "capability": record.get("capability") or "",
        "provider": record.get("provider") or "",
        "result": record.get("result") or "",
        "failure_reason": record.get("failure_reason") or "",
        "verified": bool(record.get("verified")),
        "provider_attempts": record.get("provider_attempts") or 0,
        "execution_id": record.get("execution_id") or "",
        "correlation_id": record.get("correlation_id") or "",
        "approval_id": details.get("approval_id") or "",
    }

def _approval_metadata(approval_ids: set[str]) -> dict[str, dict[str, Any]]:
    if not approval_ids or not AUTHORITY_DB.exists():
        return {}
    out: dict[str, dict[str, Any]] = {}
    c = _db(AUTHORITY_DB)
    try:
        for approval_id in approval_ids:
            row = c.execute("SELECT payload FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
            if row is None:
                continue
            payload = _json(row["payload"], {}) or {}
            decided_by = str(payload.get("decided_by") or "")
            playbook = None
            version = None
            policy_id = None
            if decided_by.startswith("policy:"):
                body = decided_by[len("policy:"):]
                if ":" in body:
                    policy_id, pb = body.rsplit(":", 1)
                    if "@" in pb:
                        playbook, version = pb.rsplit("@", 1)
            out[approval_id] = {
                "approved_by": payload.get("decided_by"),
                "playbook": playbook,
                "playbook_version": version,
                "policy_id": policy_id,
                "approval_status": payload.get("status"),
                "approval_expires_at": payload.get("expires_at"),
            }
    finally:
        c.close()
    return out


def _event_groups() -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if not EVENT_DB.exists():
        return groups
    c = _db(EVENT_DB)
    try:
        rows = c.execute(
            "SELECT event_type,execution_id,correlation_id,capability_name,stage,payload,occurred_at "
            "FROM orchestration_events WHERE principal_id=? ORDER BY occurred_at DESC LIMIT 4000",
            (PRINCIPAL,),
        ).fetchall()
        for row in rows:
            d = dict(row)
            d["payload"] = _json(d.get("payload"), {}) or {}
            groups[str(d.get("execution_id") or "")].append(d)
    finally:
        c.close()
    return groups


def load_actions(limit: int = 200) -> list[dict[str, Any]]:
    ledger_rows: list[dict[str, Any]] = []
    approval_ids: set[str] = set()
    if LEDGER_DB.exists():
        c = _db(LEDGER_DB)
        try:
            rows = c.execute(
                "SELECT * FROM governed_action_approvals WHERE principal_id=? ORDER BY created_at DESC LIMIT ?",
                (PRINCIPAL, max(limit * 3, 200)),
            ).fetchall()
            ledger_rows = [dict(r) for r in rows]
            approval_ids = {str(r.get("approval_id")) for r in ledger_rows if r.get("approval_id")}
        finally:
            c.close()

    approval_meta = _approval_metadata(approval_ids)
    event_groups = _event_groups()
    enrichment = _load_enrichment()
    actions: list[dict[str, Any]] = []
    covered_execution_ids: set[str] = set()

    for row in ledger_rows:
        execution_id = str(row.get("request_id") or "")
        covered_execution_ids.add(execution_id)
        plan = _json(row.get("execution_plan_json"), {}) or {}
        result = _json(row.get("result_json"), {}) or {}
        target = _enrich_target(_target_from_plan(plan), enrichment)
        approval_id = str(row.get("approval_id") or "") or None
        meta = approval_meta.get(approval_id or "", {})
        events = event_groups.get(execution_id, [])
        completion = next((e for e in events if e["event_type"] == "orchestration.capability.completed"), None)
        failed = next((e for e in events if e["event_type"] in {"orchestration.capability.failed", "orchestration.capability.denied"}), None)
        event_payload = (completion or failed or {}).get("payload") or {}
        provider = plan.get("provider_id") or event_payload.get("provider_id")
        capability = row.get("capability_name") or plan.get("capability_name")
        provider_cap = plan.get("provider_capability") or event_payload.get("provider_capability")
        state = str(row.get("state") or event_payload.get("status") or "unknown")
        failure_reason = None
        if state != "succeeded":
            failure_reason = row.get("failure_reason") or result.get("error_code") or event_payload.get("failure_reason") or event_payload.get("reason_code")
            if not failure_reason and isinstance(result.get("reason_codes"), list) and result.get("reason_codes"):
                failure_reason = ", ".join(str(x) for x in result.get("reason_codes")[:3])
            failure_reason = str(failure_reason or "Unspecified failure")
        verification = None
        if isinstance(result.get("output"), dict):
            output_data = result["output"].get("data")
            if isinstance(output_data, dict):
                verification = output_data.get("jasonVerification")
        if not isinstance(verification, dict) and isinstance(result.get("data"), dict):
            verification = result["data"].get("jasonVerification")
        if not isinstance(verification, dict):
            verification = result.get("jasonVerification") if isinstance(result.get("jasonVerification"), dict) else {}
        verified = bool(verification.get("readbackVerified")) if verification else state == "succeeded"
        action_title = None
        if isinstance(plan.get("arguments"), dict):
            payload = plan["arguments"].get("payload")
            if isinstance(payload, dict):
                action_title = payload.get("title") or payload.get("componentName") or payload.get("name")
        if not action_title and isinstance(plan.get("normalized_payload"), dict):
            payload = plan["normalized_payload"]
            action_title = payload.get("title") or payload.get("componentName") or payload.get("name")
        action_name = str(action_title or provider_cap or capability or "autonomous action")
        terminal = completion or failed
        action_timeline = _timeline(row=row, terminal=terminal, plan=plan, result=result, action_name=action_name, target=target, state=state, failure_reason=failure_reason, verification=verification)
        raw_details = {
            "action_timeline": action_timeline,
            "execution_id": execution_id,
            "correlation_id": row.get("correlation_id"),
            "approval_id": approval_id,
            "idempotency_key": row.get("idempotency_key"),
            "intent_fingerprint": row.get("intent_fingerprint"),
            "execution_plan_fingerprint": row.get("execution_plan_fingerprint"),
            "playbook": meta.get("playbook"),
            "playbook_version": meta.get("playbook_version"),
            "policy_id": meta.get("policy_id"),
            "capability": capability,
            "provider": provider,
            "provider_capability": provider_cap,
            "provider_attempts": result.get("attempts") or row.get("attempt_count"),
            "state": state,
            "failure_reason": failure_reason,
            "target": target,
            "execution_plan": plan,
            "result": result,
            "verification": verification,
            "orchestration": {
                "duration_ms": event_payload.get("duration_ms"),
                "replay_result": event_payload.get("replay_result"),
                "consumption_state": event_payload.get("consumption_state"),
                "information_release_gate_applied": event_payload.get("information_release_gate_applied"),
            },
        }
        actions.append({
            "kind": "action",
            "time": _iso(row.get("created_at")),
            "ticket": target.get("ticket_number") or target.get("ticket_id") or "—",
            "client": target.get("client_name") or str(target.get("client_id") or "—"),
            "device": target.get("device_name") or target.get("device") or "No device / CI",
            "playbook": _display_playbook(meta.get("playbook")),
            "playbook_version": meta.get("playbook_version") or "—",
            "action": action_name,
            "capability": capability or "—",
            "provider": provider or "—",
            "result": state,
            "failure_reason": failure_reason or "",
            "verified": verified,
            "provider_attempts": int(result.get("attempts") or row.get("attempt_count") or 0),
            "duration_ms": event_payload.get("duration_ms"),
            "execution_id": execution_id,
            "correlation_id": row.get("correlation_id") or "—",
            "details_link": "View Timeline",
            "details": _sanitize(raw_details),
        })

    # Include autonomous read-only executions not represented in the governed-action ledger.
    for execution_id, events in event_groups.items():
        if execution_id in covered_execution_ids or not execution_id.startswith("exec_autonomy"):
            continue
        terminal = next((e for e in events if e["event_type"] in {"orchestration.capability.completed", "orchestration.capability.failed", "orchestration.capability.denied"}), None)
        if terminal is None:
            continue
        p = terminal.get("payload") or {}
        state = str(p.get("status") or ("failed" if terminal["event_type"].endswith("failed") else terminal.get("stage") or "unknown"))
        actions.append({
            "kind": "read",
            "time": _iso(terminal.get("occurred_at")),
            "ticket": "—",
            "client": str(p.get("client_id") or "—"),
            "device": "—",
            "playbook": "shadow/read",
            "playbook_version": "—",
            "action": str(p.get("provider_capability") or terminal.get("capability_name") or "autonomous read"),
            "capability": terminal.get("capability_name") or "—",
            "provider": p.get("provider_id") or "—",
            "result": state,
            "verified": state == "succeeded",
            "provider_attempts": int(p.get("attempts") or 0),
            "duration_ms": p.get("duration_ms"),
            "execution_id": execution_id,
            "correlation_id": terminal.get("correlation_id") or "—",
            "details": _sanitize({
                "execution_id": execution_id,
                "correlation_id": terminal.get("correlation_id"),
                "capability": terminal.get("capability_name"),
                "provider": p.get("provider_id"),
                "provider_capability": p.get("provider_capability"),
                "status": state,
                "duration_ms": p.get("duration_ms"),
                "attempts": p.get("attempts"),
                "information_release_gate_applied": p.get("information_release_gate_applied"),
                "provider_resources": p.get("provider_resources"),
            }),
        })

    actions.sort(key=lambda x: x.get("time") or "", reverse=True)
    return actions[:limit]


def load_shadow_summary() -> dict[str, int]:
    result = {"active": 0, "waiting": 0, "approval_pending": 0, "blocked": 0}
    if not SHADOW_DB.exists():
        return result
    c = _db(SHADOW_DB)
    try:
        row = c.execute("SELECT payload FROM autonomy_shadow_runs ORDER BY run_id DESC LIMIT 1").fetchone()
        if row is None:
            return result
        payload = _json(row["payload"], {}) or {}
        for item in payload.get("selected_for_attention") or []:
            state = str(item.get("match_state") or "")
            if state == "matched_autonomy":
                result["active"] += 1
            elif state == "candidate_investigation":
                result["waiting"] += 1
            elif state == "conflict_blocked":
                result["blocked"] += 1
    finally:
        c.close()
    return result


def metrics_text() -> str:
    actions = load_actions(500)
    today = datetime.now(timezone.utc).date().isoformat()
    today_actions = [a for a in actions if a.get("kind") == "action" and str(a.get("time") or "").startswith(today)]
    today_reads = [a for a in actions if a.get("kind") == "read" and str(a.get("time") or "").startswith(today)]
    counts = Counter(a.get("result") or "unknown" for a in today_actions)
    verified = sum(1 for a in today_actions if a.get("verified"))
    shadow = load_shadow_summary()
    lines = [
        "# HELP jason_autonomy_actions_today Autonomous executions observed today.",
        "# TYPE jason_autonomy_actions_today gauge",
        f"jason_autonomy_actions_today {len(today_actions)}",
        "# HELP jason_autonomy_reads_today Autonomous governed reads observed today.",
        "# TYPE jason_autonomy_reads_today gauge",
        f"jason_autonomy_reads_today {len(today_reads)}",
        "# HELP jason_autonomy_verified_today Autonomous executions verified today.",
        "# TYPE jason_autonomy_verified_today gauge",
        f"jason_autonomy_verified_today {verified}",
        "# HELP jason_autonomy_result_today Autonomous execution result counts today.",
        "# TYPE jason_autonomy_result_today gauge",
    ]
    for result in sorted(counts):
        safe = result.replace('\\', '_').replace('"', '_')
        lines.append(f'jason_autonomy_result_today{{result="{safe}"}} {counts[result]}')
    lines.extend([
        "# HELP jason_autonomy_attention Current shadow attention counts.",
        "# TYPE jason_autonomy_attention gauge",
    ])
    for state, count in shadow.items():
        lines.append(f'jason_autonomy_attention{{state="{state}"}} {count}')
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    server_version = "JasonAutonomyFlightRecorder/1.0"

    def _send_json(self, payload: Any, status: int = 200) -> None:
        raw = json.dumps(payload, separators=(",", ":"), default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/healthz":
                return self._send_json({"status": "ok", "principal": PRINCIPAL})
            if parsed.path == "/metrics":
                raw = metrics_text().encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            if parsed.path == "/api/actions":
                q = parse_qs(parsed.query)
                limit = max(1, min(int((q.get("limit") or ["100"])[0]), 500))
                kind = str((q.get("kind") or ["action"])[0]).strip().casefold()
                records = load_actions(500)
                if kind in {"action", "read"}:
                    records = [item for item in records if item.get("kind") == kind]
                return self._send_json(records[:limit])
            if parsed.path.startswith("/api/actions/") and parsed.path.endswith("/timeline"):
                execution_id = parsed.path.split("/")[-2]
                record = next((a for a in load_actions(500) if a["execution_id"] == execution_id), None)
                return self._send_json(_timeline_rows(record) if record else {"error": "not_found"}, 200 if record else 404)
            if parsed.path.startswith("/api/actions/") and parsed.path.endswith("/summary"):
                execution_id = parsed.path.split("/")[-2]
                record = next((a for a in load_actions(500) if a["execution_id"] == execution_id), None)
                return self._send_json([_summary_row(record)] if record else {"error": "not_found"}, 200 if record else 404)
            if parsed.path.startswith("/api/actions/"):
                execution_id = parsed.path.rsplit("/", 1)[-1]
                record = next((a for a in load_actions(500) if a["execution_id"] == execution_id), None)
                return self._send_json(record or {"error": "not_found"}, 200 if record else 404)
            return self._send_json({"error": "not_found"}, 404)
        except Exception as exc:
            return self._send_json({"error": type(exc).__name__, "message": str(exc)[:300]}, 500)

    def log_message(self, fmt: str, *args: Any) -> None:
        return


if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
