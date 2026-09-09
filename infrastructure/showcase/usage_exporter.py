#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

HOST = os.environ.get("JASON_USAGE_HOST", "0.0.0.0")
PORT = int(os.environ.get("JASON_USAGE_PORT", "9465"))
ORGANIZATION_ID = os.environ.get("JASON_USAGE_ORGANIZATION_ID", "aot").strip()
TIMEZONE_NAME = os.environ.get("JASON_USAGE_TIMEZONE", "America/New_York").strip()
MODEL_USAGE_DB = Path(
    os.environ.get(
        "JASON_MODEL_USAGE_DB",
        "/var/lib/jason/openclaw/model-usage.sqlite3",
    )
)
ORCHESTRATION_EVENTS_DB = Path(
    os.environ.get(
        "JASON_ORCHESTRATION_EVENTS_DB",
        "/var/lib/jason/openclaw/orchestration-events.sqlite3",
    )
)
IDENTITY_BINDINGS_DB = Path(
    os.environ.get(
        "JASON_TEAMS_IDENTITY_BINDINGS_DB",
        "/var/lib/jason/openclaw/teams-identity-bindings.sqlite3",
    )
)

WINDOWS = ("24h", "today", "month_to_date")


def _metric_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    uri = f"file:{quote(str(path.resolve()), safe='/')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=1.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _parse_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _integer(value: object) -> int:
    try:
        number = int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0
    return max(0, number)


def _window_starts(now: datetime) -> dict[str, datetime]:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    tz = ZoneInfo(TIMEZONE_NAME)
    now_utc = now.astimezone(timezone.utc)
    local = now_utc.astimezone(tz)
    today_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
    month_local = today_local.replace(day=1)
    return {
        "24h": now_utc - timedelta(hours=24),
        "today": today_local.astimezone(timezone.utc),
        "month_to_date": month_local.astimezone(timezone.utc),
    }


def _load_model_rows(path: Path, organization_id: str) -> tuple[list[dict], dict[str, dict]]:
    connection = _connect_readonly(path)
    try:
        entries = connection.execute(
            """
            SELECT entry_id, payload_json
            FROM model_usage_entries
            WHERE organization_id = ?
            ORDER BY rowid
            """,
            (organization_id,),
        ).fetchall()
        adjustments = connection.execute(
            """
            SELECT original_entry_id, payload_json
            FROM model_usage_adjustments
            WHERE organization_id = ?
            ORDER BY rowid
            """,
            (organization_id,),
        ).fetchall()
    finally:
        connection.close()

    parsed_entries: list[dict] = []
    for row in entries:
        try:
            payload = json.loads(str(row["payload_json"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            payload["_entry_id"] = str(row["entry_id"])
            parsed_entries.append(payload)

    latest_adjustment: dict[str, dict] = {}
    for row in adjustments:
        try:
            payload = json.loads(str(row["payload_json"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            latest_adjustment[str(row["original_entry_id"])] = payload

    return parsed_entries, latest_adjustment


def _effective_usage(entry: dict, adjustment: dict | None) -> tuple[dict, dict]:
    tokens = entry.get("tokens") if isinstance(entry.get("tokens"), dict) else {}
    cost = entry.get("cost") if isinstance(entry.get("cost"), dict) else {}
    if adjustment:
        replacement_tokens = adjustment.get("replacement_tokens")
        replacement_cost = adjustment.get("replacement_cost")
        if isinstance(replacement_tokens, dict):
            tokens = replacement_tokens
        if isinstance(replacement_cost, dict):
            cost = replacement_cost
    return tokens, cost


def _chosen_cost(cost: dict) -> Decimal:
    provider_reported = _decimal(cost.get("provider_reported_cost"))
    if provider_reported is not None:
        return provider_reported
    calculated = _decimal(cost.get("calculated_cost"))
    return calculated if calculated is not None else Decimal("0")


def _load_binding_emails(path: Path) -> dict[str, str]:
    connection = _connect_readonly(path)
    try:
        rows = connection.execute(
            """
            SELECT jason_identity_id, email_address
            FROM microsoft_identity_bindings
            WHERE status = 'active'
            ORDER BY jason_identity_id, email_address
            """
        ).fetchall()
    finally:
        connection.close()

    result: dict[str, str] = {}
    for row in rows:
        identity_id = str(row["jason_identity_id"] or "").strip()
        email = str(row["email_address"] or "").strip()
        if identity_id and email and identity_id not in result:
            result[identity_id] = email
    return result


def _load_request_events(path: Path, organization_id: str) -> list[dict]:
    connection = _connect_readonly(path)
    try:
        rows = connection.execute(
            """
            SELECT execution_id, principal_id, capability_name, payload, occurred_at
            FROM orchestration_events
            WHERE organization_id = ?
              AND event_type = 'orchestration.request.received'
            ORDER BY occurred_at
            """,
            (organization_id,),
        ).fetchall()
    finally:
        connection.close()

    events: list[dict] = []
    for row in rows:
        requester_kind = ""
        try:
            payload = json.loads(str(row["payload"]))
            if isinstance(payload, dict):
                requester_kind = str(payload.get("requester_kind") or "").strip()
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        events.append(
            {
                "execution_id": str(row["execution_id"] or ""),
                "principal_id": str(row["principal_id"] or "").strip(),
                "capability": str(row["capability_name"] or "").strip(),
                "occurred_at": _parse_timestamp(row["occurred_at"]),
                "requester_kind": requester_kind,
            }
        )
    return events


def render_metrics(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    starts = _window_starts(now)

    lines = [
        "# HELP jason_usage_exporter_build_info Jason usage telemetry exporter metadata.",
        "# TYPE jason_usage_exporter_build_info gauge",
        'jason_usage_exporter_build_info{version="1"} 1',
        "# HELP jason_usage_source_available Whether a read-only Jason telemetry source is available.",
        "# TYPE jason_usage_source_available gauge",
    ]

    model_entries: list[dict] = []
    model_adjustments: dict[str, dict] = {}
    model_available = 0
    try:
        model_entries, model_adjustments = _load_model_rows(MODEL_USAGE_DB, ORGANIZATION_ID)
        model_available = 1
    except (OSError, sqlite3.Error, ValueError):
        pass
    lines.append(f'jason_usage_source_available{{source="model_usage"}} {model_available}')

    bindings: dict[str, str] = {}
    bindings_available = 0
    try:
        bindings = _load_binding_emails(IDENTITY_BINDINGS_DB)
        bindings_available = 1
    except (OSError, sqlite3.Error, ValueError):
        pass
    lines.append(f'jason_usage_source_available{{source="identity_bindings"}} {bindings_available}')

    request_events: list[dict] = []
    events_available = 0
    try:
        request_events = _load_request_events(ORCHESTRATION_EVENTS_DB, ORGANIZATION_ID)
        events_available = 1
    except (OSError, sqlite3.Error, ValueError):
        pass
    lines.append(f'jason_usage_source_available{{source="orchestration_events"}} {events_available}')

    model_totals: dict[str, dict[str, object]] = {
        window: {
            "attempts": 0,
            "cost": Decimal("0"),
            "unknown": 0,
            "tokens": defaultdict(int),
        }
        for window in WINDOWS
    }
    model_24h: dict[tuple[str, str], dict[str, object]] = defaultdict(
        lambda: {"attempts": 0, "cost": Decimal("0"), "tokens": 0}
    )
    usage_sources_24h: dict[str, int] = defaultdict(int)
    last_model_timestamp: datetime | None = None

    for entry in model_entries:
        completed_at = _parse_timestamp(entry.get("completed_at"))
        if completed_at is None or completed_at > now:
            continue
        if last_model_timestamp is None or completed_at > last_model_timestamp:
            last_model_timestamp = completed_at

        adjustment = model_adjustments.get(str(entry.get("_entry_id") or ""))
        tokens, cost = _effective_usage(entry, adjustment)
        chosen_cost = _chosen_cost(cost)
        token_values = {
            "input": _integer(tokens.get("input_tokens")),
            "cached_input": _integer(tokens.get("cached_input_tokens")),
            "output": _integer(tokens.get("output_tokens")),
            "reasoning": _integer(tokens.get("reasoning_tokens")),
            "total": _integer(tokens.get("total_tokens")),
        }
        usage_source = str(entry.get("usage_source") or "unknown").strip() or "unknown"
        provider = str(entry.get("provider") or "unknown").strip() or "unknown"
        model = str(entry.get("model") or "unknown").strip() or "unknown"

        for window, start in starts.items():
            if completed_at < start:
                continue
            aggregate = model_totals[window]
            aggregate["attempts"] = int(aggregate["attempts"]) + 1
            aggregate["cost"] = Decimal(aggregate["cost"]) + chosen_cost
            if usage_source == "unknown":
                aggregate["unknown"] = int(aggregate["unknown"]) + 1
            token_totals = aggregate["tokens"]
            assert isinstance(token_totals, defaultdict)
            for token_type, value in token_values.items():
                token_totals[token_type] += value

        if completed_at >= starts["24h"]:
            key = (provider, model)
            aggregate = model_24h[key]
            aggregate["attempts"] = int(aggregate["attempts"]) + 1
            aggregate["cost"] = Decimal(aggregate["cost"]) + chosen_cost
            aggregate["tokens"] = int(aggregate["tokens"]) + token_values["total"]
            usage_sources_24h[usage_source] += 1

    lines.extend(
        [
            "# HELP jason_model_cost_usd Effective Jason model cost for a rolling or calendar window.",
            "# TYPE jason_model_cost_usd gauge",
            "# HELP jason_model_attempts Jason model attempts for a rolling or calendar window.",
            "# TYPE jason_model_attempts gauge",
            "# HELP jason_model_tokens Jason model tokens by token type and window.",
            "# TYPE jason_model_tokens gauge",
            "# HELP jason_model_unknown_usage_attempts Model attempts whose usage source is unknown.",
            "# TYPE jason_model_unknown_usage_attempts gauge",
        ]
    )
    for window in WINDOWS:
        aggregate = model_totals[window]
        lines.append(
            f'jason_model_cost_usd{{window="{window}"}} {Decimal(aggregate["cost"]):.8f}'
        )
        lines.append(f'jason_model_attempts{{window="{window}"}} {int(aggregate["attempts"])}')
        token_totals = aggregate["tokens"]
        assert isinstance(token_totals, defaultdict)
        for token_type in ("input", "cached_input", "output", "reasoning", "total"):
            lines.append(
                f'jason_model_tokens{{window="{window}",type="{token_type}"}} '
                f'{int(token_totals[token_type])}'
            )
        lines.append(
            f'jason_model_unknown_usage_attempts{{window="{window}"}} '
            f'{int(aggregate["unknown"])}'
        )

    lines.extend(
        [
            "# HELP jason_model_24h_cost_by_model_usd Effective model cost during the last 24 hours.",
            "# TYPE jason_model_24h_cost_by_model_usd gauge",
            "# HELP jason_model_24h_attempts_by_model Model attempts during the last 24 hours.",
            "# TYPE jason_model_24h_attempts_by_model gauge",
            "# HELP jason_model_24h_tokens_by_model Total tokens during the last 24 hours.",
            "# TYPE jason_model_24h_tokens_by_model gauge",
        ]
    )
    for (provider, model), aggregate in sorted(model_24h.items()):
        labels = (
            f'provider="{_metric_escape(provider)}",'
            f'model="{_metric_escape(model)}"'
        )
        lines.append(
            f'jason_model_24h_cost_by_model_usd{{{labels}}} '
            f'{Decimal(aggregate["cost"]):.8f}'
        )
        lines.append(
            f'jason_model_24h_attempts_by_model{{{labels}}} {int(aggregate["attempts"])}'
        )
        lines.append(
            f'jason_model_24h_tokens_by_model{{{labels}}} {int(aggregate["tokens"])}'
        )

    lines.extend(
        [
            "# HELP jason_model_24h_usage_source_attempts Model attempts in the last 24 hours by accounting source.",
            "# TYPE jason_model_24h_usage_source_attempts gauge",
        ]
    )
    for source, count in sorted(usage_sources_24h.items()):
        lines.append(
            f'jason_model_24h_usage_source_attempts{{source="{_metric_escape(source)}"}} {count}'
        )

    lines.extend(
        [
            "# HELP jason_model_usage_last_entry_timestamp_seconds Timestamp of the newest model usage ledger entry.",
            "# TYPE jason_model_usage_last_entry_timestamp_seconds gauge",
            f"jason_model_usage_last_entry_timestamp_seconds "
            f"{last_model_timestamp.timestamp():.3f}"
            if last_model_timestamp is not None
            else "jason_model_usage_last_entry_timestamp_seconds 0",
        ]
    )

    events_24h = [
        event
        for event in request_events
        if event.get("occurred_at") is not None
        and starts["24h"] <= event["occurred_at"] <= now
        and event.get("principal_id")
    ]
    per_user: dict[str, dict[str, object]] = {}
    capability_counts: dict[tuple[str, str], int] = defaultdict(int)
    for event in events_24h:
        identity_id = str(event["principal_id"])
        current = per_user.setdefault(
            identity_id,
            {"requests": 0, "last_seen": None, "requester_kind": ""},
        )
        current["requests"] = int(current["requests"]) + 1
        event_time = event["occurred_at"]
        previous = current["last_seen"]
        if previous is None or event_time > previous:
            current["last_seen"] = event_time
            current["requester_kind"] = str(event.get("requester_kind") or "")
        capability = str(event.get("capability") or "unknown")
        capability_counts[(identity_id, capability)] += 1

    lines.extend(
        [
            "# HELP jason_governed_requests_24h Governed Jason orchestration requests in the last 24 hours.",
            "# TYPE jason_governed_requests_24h gauge",
            f"jason_governed_requests_24h {len(events_24h)}",
            "# HELP jason_active_users_24h Distinct authenticated Jason principals with governed requests in the last 24 hours.",
            "# TYPE jason_active_users_24h gauge",
            f"jason_active_users_24h {len(per_user)}",
            "# HELP jason_user_requests_24h Governed requests per Jason identity during the last 24 hours.",
            "# TYPE jason_user_requests_24h gauge",
            "# HELP jason_user_last_seen_timestamp_seconds Last governed request timestamp for a Jason identity.",
            "# TYPE jason_user_last_seen_timestamp_seconds gauge",
        ]
    )

    for identity_id, aggregate in sorted(per_user.items()):
        email = bindings.get(identity_id, "")
        requester_kind = str(aggregate.get("requester_kind") or "")
        labels = (
            f'identity_id="{_metric_escape(identity_id)}",'
            f'email="{_metric_escape(email)}",'
            f'requester_kind="{_metric_escape(requester_kind)}"'
        )
        lines.append(
            f'jason_user_requests_24h{{{labels}}} {int(aggregate["requests"])}'
        )
        last_seen = aggregate.get("last_seen")
        if isinstance(last_seen, datetime):
            lines.append(
                f'jason_user_last_seen_timestamp_seconds{{{labels}}} {last_seen.timestamp():.3f}'
            )

    lines.extend(
        [
            "# HELP jason_user_capability_requests_24h Governed requests per identity and capability during the last 24 hours.",
            "# TYPE jason_user_capability_requests_24h gauge",
        ]
    )
    for (identity_id, capability), count in sorted(capability_counts.items()):
        email = bindings.get(identity_id, "")
        labels = (
            f'identity_id="{_metric_escape(identity_id)}",'
            f'email="{_metric_escape(email)}",'
            f'capability="{_metric_escape(capability)}"'
        )
        lines.append(f'jason_user_capability_requests_24h{{{labels}}} {count}')

    lines.extend(
        [
            "# HELP jason_usage_exporter_scrape_timestamp_seconds Timestamp when this telemetry snapshot was rendered.",
            "# TYPE jason_usage_exporter_scrape_timestamp_seconds gauge",
            f"jason_usage_exporter_scrape_timestamp_seconds {now.timestamp():.3f}",
        ]
    )
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path not in ("/", "/metrics"):
            self.send_response(404)
            self.end_headers()
            return
        payload = render_metrics().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    server = HTTPServer((HOST, PORT), Handler)
    print(f"Jason usage exporter listening on {HOST}:{PORT}", flush=True)
    while True:
        server.handle_request()
        time.sleep(0)
