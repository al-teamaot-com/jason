#!/usr/bin/env python3
"""Read-only Prometheus exporter for Jason usage attribution.

The exporter joins existing append-only model usage and orchestration telemetry.
It never reads or exports prompts, provider response bodies, credentials, API keys,
bearer tokens, OAuth tokens, client secrets, or raw provider evidence.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import quote

HOST = os.environ.get("JASON_ATTRIBUTION_HOST", "0.0.0.0")
PORT = int(os.environ.get("JASON_ATTRIBUTION_PORT", "9466"))
ORGANIZATION_ID = os.environ.get("JASON_USAGE_ORGANIZATION_ID", "aot").strip() or "aot"
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
AUTHORITY_DB = Path(
    os.environ.get(
        "JASON_AUTHORITY_DB",
        "/var/lib/jason/authority/authority.sqlite3",
    )
)
MAX_RECENT_EVENT_SERIES = int(os.environ.get("JASON_ATTRIBUTION_MAX_RECENT_EVENTS", "250"))


def _escape(value: object) -> str:
    return (
        str(value if value is not None else "")
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
    )


def _connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    uri = f"file:{quote(str(path.resolve()), safe='/')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=1.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _timestamp(value: object) -> datetime | None:
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
    except (InvalidOperation, TypeError, ValueError):
        return None


def _integer(value: object) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _safe_json(raw: object) -> dict:
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _binding_emails() -> dict[str, str]:
    connection = _connect_readonly(IDENTITY_BINDINGS_DB)
    try:
        rows = connection.execute(
            """
            SELECT jason_identity_id, email_address
            FROM microsoft_identity_bindings
            WHERE status = 'active'
            ORDER BY jason_identity_id
            """
        ).fetchall()
    finally:
        connection.close()
    result: dict[str, str] = {}
    for row in rows:
        identity = str(row["jason_identity_id"] or "").strip()
        email = str(row["email_address"] or "").strip()
        if identity and email and identity not in result:
            result[identity] = email
    return result


def _model_entries() -> list[dict]:
    connection = _connect_readonly(MODEL_USAGE_DB)
    try:
        rows = connection.execute(
            """
            SELECT entry_id, payload_json
            FROM model_usage_entries
            WHERE organization_id = ?
            ORDER BY rowid
            """,
            (ORGANIZATION_ID,),
        ).fetchall()
        adjustments = connection.execute(
            """
            SELECT original_entry_id, payload_json
            FROM model_usage_adjustments
            WHERE organization_id = ?
            ORDER BY rowid
            """,
            (ORGANIZATION_ID,),
        ).fetchall()
    finally:
        connection.close()

    latest_adjustment: dict[str, dict] = {}
    for row in adjustments:
        payload = _safe_json(row["payload_json"])
        if payload:
            latest_adjustment[str(row["original_entry_id"])] = payload

    result = []
    for row in rows:
        payload = _safe_json(row["payload_json"])
        if not payload:
            continue
        payload["_entry_id"] = str(row["entry_id"])
        payload["_adjustment"] = latest_adjustment.get(str(row["entry_id"]))
        result.append(payload)
    return result


def _orchestration_events() -> list[dict]:
    connection = _connect_readonly(ORCHESTRATION_EVENTS_DB)
    try:
        rows = connection.execute(
            """
            SELECT event_id, event_type, execution_id, correlation_id,
                   principal_id, capability_name, payload, occurred_at
            FROM orchestration_events
            WHERE organization_id = ?
            ORDER BY occurred_at, event_id
            """,
            (ORGANIZATION_ID,),
        ).fetchall()
    finally:
        connection.close()

    return [
        {
            "event_id": str(row["event_id"]),
            "event_type": str(row["event_type"]),
            "execution_id": str(row["execution_id"]),
            "correlation_id": str(row["correlation_id"]),
            "principal_id": str(row["principal_id"] or "").strip(),
            "capability": str(row["capability_name"] or "").strip(),
            "payload": _safe_json(row["payload"]),
            "occurred_at": _timestamp(row["occurred_at"]),
        }
        for row in rows
    ]


def _authority_approvals() -> list[dict]:
    connection = _connect_readonly(AUTHORITY_DB)
    try:
        rows = connection.execute("SELECT approval_id, payload FROM approvals ORDER BY rowid").fetchall()
    finally:
        connection.close()
    result = []
    for row in rows:
        payload = _safe_json(row["payload"])
        decided_at = _timestamp(payload.get("decided_at"))
        if decided_at is None:
            continue
        result.append({
            "approval_id": str(row["approval_id"]),
            "capability": str(payload.get("capability") or "unknown"),
            "client_id": str(payload.get("client_id") or ""),
            "organization_id": str(payload.get("organization_id") or ""),
            "requested_by": str(payload.get("requested_by") or "unknown"),
            "decided_by": str(payload.get("decided_by") or "unknown"),
            "status": str(payload.get("status") or "unknown"),
            "request_id": str(payload.get("request_id") or ""),
            "decided_at": decided_at,
        })
    return result


def _audit_dimensions(events: list[dict], approvals: list[dict], now: datetime) -> dict:
    start = now - timedelta(hours=24)
    mutation_types = {
        "connector.mutation.requested",
        "connector.mutation.accepted",
        "connector.mutation.completed",
        "connector.mutation.verified",
        "connector.mutation.failed",
    }
    mutations, autonomous, client_access = [], [], []
    for event in events:
        occurred_at = event.get("occurred_at")
        if occurred_at is None or not (start <= occurred_at <= now):
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        event_type = str(event.get("event_type") or "")
        capability = str(event.get("capability") or "unknown")
        principal_id = str(event.get("principal_id") or "unknown")
        correlation_id = str(event.get("correlation_id") or "")
        execution_id = str(event.get("execution_id") or "")
        client_id = str(payload.get("client_id") or "")
        requester_kind = str(payload.get("requester_kind") or "").strip().casefold()
        common = {
            "capability": capability, "principal_id": principal_id,
            "correlation_id": correlation_id, "execution_id": execution_id,
            "client_id": client_id, "occurred_at": occurred_at,
        }
        if event_type in mutation_types:
            mutations.append({**common, "event_type": event_type})
        if event_type == "orchestration.request.received" and requester_kind and requester_kind != "human":
            autonomous.append({**common, "requester_kind": requester_kind})
        if event_type == "orchestration.request.received" and client_id:
            client_access.append({**common, "requester_kind": requester_kind or "unknown"})
    recent_approvals = [
        row for row in approvals
        if row["organization_id"] == ORGANIZATION_ID and start <= row["decided_at"] <= now
    ]
    return {
        "approvals": recent_approvals,
        "mutations": mutations,
        "autonomous": autonomous,
        "client_access": client_access,
    }


def _provider_product(provider: str) -> str:
    normalized = provider.casefold()
    return {
        "openai": "OpenAI API",
        "openai-conversation-kernel": "OpenAI API",
        "openrouter": "OpenRouter API",
        "ollama": "Local LLM",
        "datto_rmm": "Datto RMM",
        "microsoft_graph": "Microsoft Graph",
        "aws_ses": "AWS SES",
    }.get(normalized, provider or "unknown")


def _billing_class(provider: str) -> str:
    normalized = provider.casefold()
    if normalized in {"openai", "openai-conversation-kernel", "openrouter", "aws_ses"}:
        return "metered"
    if normalized in {"datto_rmm", "microsoft_graph"}:
        return "subscription"
    if normalized == "ollama":
        return "included"
    return "unknown"


def _channel(correlation_id: str, actor_type: str) -> str:
    if correlation_id.startswith("corr_mcp_"):
        return "chatgpt_mcp"
    if actor_type == "human":
        return "teams"
    if actor_type in {"service", "agent", "scheduled_process", "system"}:
        return "internal_automation"
    return "unknown"


def _actor_type(value: object) -> str:
    normalized = str(value or "").strip().casefold()
    if normalized in {"human", "service", "agent", "scheduled_process", "system"}:
        return normalized
    return "unknown"


def _model_event(entry: dict, emails: dict[str, str]) -> dict | None:
    occurred_at = _timestamp(entry.get("completed_at"))
    if occurred_at is None:
        return None

    context = entry.get("context") if isinstance(entry.get("context"), dict) else {}
    context_metadata = (
        context.get("metadata") if isinstance(context.get("metadata"), dict) else {}
    )
    entry_metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    metadata = {**entry_metadata, **context_metadata}

    actor_id = str(
        metadata.get("actor_id")
        or metadata.get("principal_id")
        or "unknown"
    ).strip() or "unknown"
    actor_type = _actor_type(metadata.get("actor_type"))
    if actor_type == "unknown" and actor_id != "unknown":
        actor_type = "human"

    correlation_id = str(
        metadata.get("correlation_id")
        or context.get("request_id")
        or ""
    ).strip()
    if not correlation_id:
        correlation_id = "unattributed:" + str(entry.get("_entry_id") or "unknown")

    source_channel = str(
        metadata.get("source_channel")
        or context.get("routing_profile")
        or ""
    ).strip()
    if not source_channel:
        source_channel = _channel(correlation_id, actor_type)

    capability = str(context.get("capability") or "unknown").strip() or "unknown"
    purpose = str(metadata.get("purpose") or capability).strip() or capability
    provider = str(entry.get("provider") or "unknown").strip() or "unknown"
    product = _provider_product(provider)
    model = str(entry.get("model") or "unknown").strip() or "unknown"
    outcome = str(entry.get("outcome") or "unknown").strip() or "unknown"

    adjustment = entry.get("_adjustment") if isinstance(entry.get("_adjustment"), dict) else {}
    cost = entry.get("cost") if isinstance(entry.get("cost"), dict) else {}
    tokens = entry.get("tokens") if isinstance(entry.get("tokens"), dict) else {}
    if isinstance(adjustment.get("replacement_cost"), dict):
        cost = adjustment["replacement_cost"]
    if isinstance(adjustment.get("replacement_tokens"), dict):
        tokens = adjustment["replacement_tokens"]

    provider_cost = _decimal(cost.get("provider_reported_cost"))
    calculated_cost = _decimal(cost.get("calculated_cost"))
    effective_cost = provider_cost if provider_cost is not None else calculated_cost
    total_tokens = _integer(tokens.get("total_tokens"))

    usage_source = str(entry.get("usage_source") or "unknown").strip() or "unknown"
    if provider_cost is not None:
        telemetry_quality = "exact"
    elif calculated_cost is not None:
        telemetry_quality = "calculated"
    elif usage_source in {"provider_reported", "local_runtime_reported"}:
        telemetry_quality = "exact"
    else:
        telemetry_quality = "unavailable"

    email = str(metadata.get("email_address") or emails.get(actor_id, "")).strip()
    display_name = str(metadata.get("display_name") or "").strip()
    workload_name = str(
        metadata.get("workload_name")
        or context.get("agent_name")
        or ""
    ).strip()

    attributable = actor_id != "unknown" and actor_type != "unknown"
    return {
        "kind": "model",
        "occurred_at": occurred_at,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "email": email,
        "display_name": display_name,
        "workload_name": workload_name,
        "source_channel": source_channel,
        "purpose": purpose,
        "capability": capability,
        "provider": provider,
        "product": product,
        "service": model,
        "billing_class": _billing_class(provider),
        "telemetry_quality": telemetry_quality,
        "usage_quantity": total_tokens,
        "usage_unit": "tokens" if total_tokens else "unavailable",
        "cost": effective_cost or Decimal("0"),
        "outcome": outcome,
        "correlation_id": correlation_id,
        "request_id": str(context.get("request_id") or ""),
        "attributable": attributable,
    }


def _provider_events(events: list[dict], emails: dict[str, str]) -> list[dict]:
    request_by_correlation: dict[str, dict] = {}
    for event in events:
        if event["event_type"] != "orchestration.request.received":
            continue
        payload = event["payload"]
        request_by_correlation[event["correlation_id"]] = {
            "actor_type": _actor_type(payload.get("requester_kind")),
            "principal_id": event["principal_id"],
            "capability": event["capability"],
            "occurred_at": event["occurred_at"],
        }

    result = []
    for event in events:
        event_type = event["event_type"]
        if event_type not in {"connector.requested", "email.send.attempted"}:
            continue

        payload = event["payload"]
        details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
        correlation_id = event["correlation_id"]
        request = request_by_correlation.get(correlation_id, {})
        actor_id = str(
            event["principal_id"]
            or request.get("principal_id")
            or "unknown"
        ).strip() or "unknown"
        actor_type = _actor_type(request.get("actor_type"))
        if actor_type == "unknown" and actor_id != "unknown":
            actor_type = "human" if correlation_id.startswith("corr_mcp_") else "unknown"

        capability = str(event["capability"] or request.get("capability") or "unknown")
        if event_type == "email.send.attempted":
            provider = "aws_ses"
            operation = "email.send"
        else:
            provider = str(details.get("provider") or payload.get("provider") or "unknown").strip()
            operation = str(details.get("operation") or payload.get("operation") or capability).strip()

        product = _provider_product(provider)
        source_channel = _channel(correlation_id, actor_type)
        email = emails.get(actor_id, "")
        attributable = actor_id != "unknown" and actor_type != "unknown"
        occurred_at = event["occurred_at"]
        if occurred_at is None:
            continue

        result.append(
            {
                "kind": "provider_api",
                "occurred_at": occurred_at,
                "actor_type": actor_type,
                "actor_id": actor_id,
                "email": email,
                "display_name": "",
                "workload_name": actor_id if actor_type != "human" else "",
                "source_channel": source_channel,
                "purpose": f"{capability}: {operation}",
                "capability": capability,
                "provider": provider or "unknown",
                "product": product,
                "service": operation or "unknown",
                "billing_class": _billing_class(provider),
                "telemetry_quality": "exact",
                "usage_quantity": 1,
                "usage_unit": "request",
                "cost": Decimal("0"),
                "outcome": "attempted",
                "correlation_id": correlation_id,
                "request_id": event["execution_id"],
                "attributable": attributable,
            }
        )
    return result


def _labels(values: dict[str, object]) -> str:
    return ",".join(f'{name}="{_escape(value)}"' for name, value in values.items())


def render_metrics(now: datetime | None = None) -> str:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start = now - timedelta(hours=24)
    lines = [
        "# HELP jason_usage_attribution_exporter_build_info Jason usage attribution exporter metadata.",
        "# TYPE jason_usage_attribution_exporter_build_info gauge",
        'jason_usage_attribution_exporter_build_info{version="1"} 1',
        "# HELP jason_usage_attribution_source_available Whether an attribution telemetry source is available.",
        "# TYPE jason_usage_attribution_source_available gauge",
    ]

    emails: dict[str, str] = {}
    bindings_available = 0
    try:
        emails = _binding_emails()
        bindings_available = 1
    except (OSError, sqlite3.Error, ValueError):
        pass
    lines.append(
        f'jason_usage_attribution_source_available{{source="identity_bindings"}} {bindings_available}'
    )

    model_rows: list[dict] = []
    model_available = 0
    try:
        model_rows = _model_entries()
        model_available = 1
    except (OSError, sqlite3.Error, ValueError):
        pass
    lines.append(
        f'jason_usage_attribution_source_available{{source="model_usage"}} {model_available}'
    )

    orchestration_rows: list[dict] = []
    orchestration_available = 0
    try:
        orchestration_rows = _orchestration_events()
        orchestration_available = 1
    except (OSError, sqlite3.Error, ValueError):
        pass
    lines.append(
        f'jason_usage_attribution_source_available{{source="orchestration_events"}} {orchestration_available}'
    )

    approval_rows: list[dict] = []
    authority_available = 0
    try:
        approval_rows = _authority_approvals()
        authority_available = 1
    except (OSError, sqlite3.Error, ValueError):
        pass
    lines.append(
        f'jason_usage_attribution_source_available{{source="authority"}} {authority_available}'
    )
    audit = _audit_dimensions(orchestration_rows, approval_rows, now)

    events: list[dict] = []
    for entry in model_rows:
        normalized = _model_event(entry, emails)
        if normalized is not None and start <= normalized["occurred_at"] <= now:
            events.append(normalized)
    events.extend(
        item
        for item in _provider_events(orchestration_rows, emails)
        if start <= item["occurred_at"] <= now
    )
    events.sort(key=lambda item: item["occurred_at"])

    by_kind = defaultdict(int)
    by_actor = defaultdict(int)
    by_provider = defaultdict(int)
    provider_cost = defaultdict(lambda: Decimal("0"))
    unattributed = 0
    human_events = 0
    human_events_with_email = 0

    for event in events:
        by_kind[event["kind"]] += 1
        actor_key = (
            event["actor_type"],
            event["actor_id"],
            event["email"],
            event["workload_name"],
            event["source_channel"],
        )
        by_actor[actor_key] += 1
        provider_key = (
            event["provider"],
            event["product"],
            event["billing_class"],
            event["telemetry_quality"],
        )
        by_provider[provider_key] += 1
        provider_cost[(event["provider"], event["product"])] += Decimal(event["cost"])
        if not event["attributable"]:
            unattributed += 1
        if event["actor_type"] == "human":
            human_events += 1
            if event["email"]:
                human_events_with_email += 1

    total = len(events)
    coverage = (total - unattributed) / total if total else 1.0
    email_coverage = human_events_with_email / human_events if human_events else 1.0

    lines.extend(
        [
            "# HELP jason_usage_observed_events_24h Observable model/provider API usage events in the last 24 hours.",
            "# TYPE jason_usage_observed_events_24h gauge",
        ]
    )
    for kind in ("model", "provider_api"):
        lines.append(
            f'jason_usage_observed_events_24h{{kind="{kind}"}} {by_kind[kind]}'
        )

    lines.extend(
        [
            "# HELP jason_usage_attribution_coverage_ratio_24h Fraction of observable usage events attributed to a known actor.",
            "# TYPE jason_usage_attribution_coverage_ratio_24h gauge",
            f"jason_usage_attribution_coverage_ratio_24h {coverage:.6f}",
            "# HELP jason_usage_unattributed_events_24h Observable usage events lacking a known actor.",
            "# TYPE jason_usage_unattributed_events_24h gauge",
            f"jason_usage_unattributed_events_24h {unattributed}",
            "# HELP jason_usage_human_email_coverage_ratio_24h Fraction of human usage events with trusted email display metadata.",
            "# TYPE jason_usage_human_email_coverage_ratio_24h gauge",
            f"jason_usage_human_email_coverage_ratio_24h {email_coverage:.6f}",
        ]
    )

    lines.extend(
        [
            "# HELP jason_usage_actor_events_24h Observable usage events by actor and source channel.",
            "# TYPE jason_usage_actor_events_24h gauge",
        ]
    )
    for (actor_type, actor_id, email, workload_name, source_channel), count in sorted(by_actor.items()):
        labels = _labels(
            {
                "actor_type": actor_type,
                "actor_id": actor_id,
                "email": email,
                "workload_name": workload_name,
                "source_channel": source_channel,
            }
        )
        lines.append(f"jason_usage_actor_events_24h{{{labels}}} {count}")

    lines.extend(
        [
            "# HELP jason_usage_provider_events_24h Observable usage events by provider/product and billing class.",
            "# TYPE jason_usage_provider_events_24h gauge",
        ]
    )
    for (provider, product, billing_class, telemetry_quality), count in sorted(by_provider.items()):
        labels = _labels(
            {
                "provider": provider,
                "product": product,
                "billing_class": billing_class,
                "telemetry_quality": telemetry_quality,
            }
        )
        lines.append(f"jason_usage_provider_events_24h{{{labels}}} {count}")

    lines.extend(
        [
            "# HELP jason_usage_provider_cost_usd_24h Effective known model/provider cost in the last 24 hours.",
            "# TYPE jason_usage_provider_cost_usd_24h gauge",
        ]
    )
    for (provider, product), amount in sorted(provider_cost.items()):
        labels = _labels({"provider": provider, "product": product})
        lines.append(f"jason_usage_provider_cost_usd_24h{{{labels}}} {amount:.8f}")

    lines.extend(
        [
            "# HELP jason_usage_recent_event_info Bounded recent usage-event trace rows for dashboard drill-down.",
            "# TYPE jason_usage_recent_event_info gauge",
        ]
    )
    for event in events[-MAX_RECENT_EVENT_SERIES:]:
        labels = _labels(
            {
                "kind": event["kind"],
                "actor_type": event["actor_type"],
                "actor_id": event["actor_id"],
                "email": event["email"],
                "workload_name": event["workload_name"],
                "source_channel": event["source_channel"],
                "purpose": event["purpose"],
                "capability": event["capability"],
                "provider": event["provider"],
                "product": event["product"],
                "service": event["service"],
                "billing_class": event["billing_class"],
                "telemetry_quality": event["telemetry_quality"],
                "usage_unit": event["usage_unit"],
                "outcome": event["outcome"],
                "correlation_id": event["correlation_id"],
                "request_id": event["request_id"],
            }
        )
        lines.append(
            f"jason_usage_recent_event_info{{{labels}}} {event['occurred_at'].timestamp():.3f}"
        )

    lines.extend([
        "# HELP jason_audit_approvals_24h Persisted approval decisions in the last 24 hours.",
        "# TYPE jason_audit_approvals_24h gauge",
    ])
    approval_counts = defaultdict(int)
    for item in audit["approvals"]:
        approval_counts[(item["status"], item["capability"], item["decided_by"])] += 1
    for (status, capability, decided_by), count in sorted(approval_counts.items()):
        labels = _labels({"status": status, "capability": capability, "decided_by": decided_by})
        lines.append(f"jason_audit_approvals_24h{{{labels}}} {count}")

    lines.extend([
        "# HELP jason_audit_mutation_events_24h Governed mutation lifecycle events in the last 24 hours.",
        "# TYPE jason_audit_mutation_events_24h gauge",
    ])
    mutation_counts = defaultdict(int)
    for item in audit["mutations"]:
        mutation_counts[(item["event_type"], item["capability"], item["principal_id"])] += 1
    for (event_type, capability, principal_id), count in sorted(mutation_counts.items()):
        labels = _labels({"event_type": event_type, "capability": capability, "principal_id": principal_id})
        lines.append(f"jason_audit_mutation_events_24h{{{labels}}} {count}")

    lines.extend([
        "# HELP jason_audit_autonomous_requests_24h Explicit non-human orchestration requests in the last 24 hours.",
        "# TYPE jason_audit_autonomous_requests_24h gauge",
    ])
    autonomous_counts = defaultdict(int)
    for item in audit["autonomous"]:
        autonomous_counts[(item["requester_kind"], item["capability"], item["principal_id"])] += 1
    for (requester_kind, capability, principal_id), count in sorted(autonomous_counts.items()):
        labels = _labels({"requester_kind": requester_kind, "capability": capability, "principal_id": principal_id})
        lines.append(f"jason_audit_autonomous_requests_24h{{{labels}}} {count}")

    lines.extend([
        "# HELP jason_audit_client_access_24h Governed requests explicitly scoped to a client in the last 24 hours.",
        "# TYPE jason_audit_client_access_24h gauge",
    ])
    client_counts = defaultdict(int)
    for item in audit["client_access"]:
        client_counts[(item["client_id"], item["capability"], item["principal_id"], item["requester_kind"])] += 1
    for (client_id, capability, principal_id, requester_kind), count in sorted(client_counts.items()):
        labels = _labels({"client_id": client_id, "capability": capability, "principal_id": principal_id, "requester_kind": requester_kind})
        lines.append(f"jason_audit_client_access_24h{{{labels}}} {count}")

    lines.extend([
        "# HELP jason_audit_recent_approval_info Bounded recent approval records.",
        "# TYPE jason_audit_recent_approval_info gauge",
    ])
    for item in audit["approvals"][-MAX_RECENT_EVENT_SERIES:]:
        labels = _labels({
            "approval_id": item["approval_id"], "status": item["status"],
            "capability": item["capability"], "requested_by": item["requested_by"],
            "decided_by": item["decided_by"], "client_id": item["client_id"],
            "request_id": item["request_id"],
        })
        lines.append(f"jason_audit_recent_approval_info{{{labels}}} {item['decided_at'].timestamp():.3f}")

    newest = events[-1]["occurred_at"].timestamp() if events else 0
    lines.extend(
        [
            "# HELP jason_usage_last_observed_timestamp_seconds Timestamp of the newest observable usage event.",
            "# TYPE jason_usage_last_observed_timestamp_seconds gauge",
            f"jason_usage_last_observed_timestamp_seconds {newest:.3f}",
            "# HELP jason_usage_attribution_exporter_scrape_timestamp_seconds Timestamp when this attribution snapshot was rendered.",
            "# TYPE jason_usage_attribution_exporter_scrape_timestamp_seconds gauge",
            f"jason_usage_attribution_exporter_scrape_timestamp_seconds {now.timestamp():.3f}",
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
    print(f"Jason usage attribution exporter listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()
