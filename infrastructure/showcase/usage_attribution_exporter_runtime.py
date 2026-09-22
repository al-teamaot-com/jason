#!/usr/bin/env python3
"""Runtime adapter for Jason usage attribution telemetry.

This layer extends the base read-only exporter with safe Microsoft Graph identity
usage events and correlation-based actor enrichment. It keeps the existing metric
contract stable while recognizing identity-directory API calls as provider usage,
using successful directory enrichment for friendly email display, and associating
pre-identity model work with the later governed request when both share a correlation
identifier.

Correlation enrichment is dashboard-time accounting only. It does not rewrite the
append-only model ledger and it does not create identity, authority, tenant/client
scope, or provider permissions.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from http.server import HTTPServer
from pathlib import Path
from urllib import error, parse, request

import usage_attribution_exporter as base


_ORIGINAL_ORCHESTRATION_EVENTS = base._orchestration_events
_ORIGINAL_MODEL_EVENT = base._model_event
_REQUEST_BY_CORRELATION: dict[str, dict[str, str]] = {}
_DIRECTORY_EMAILS: dict[str, str] = {}
_ORIGINAL_RENDER_METRICS = base.render_metrics

_OPENBAO_URL = os.environ.get("JASON_OPENBAO_URL", "http://127.0.0.1:8200").rstrip("/")
_OPENAI_API_BASE = os.environ.get("JASON_OPENAI_ADMIN_API_BASE", "https://api.openai.com/v1").rstrip("/")
_OPENAI_USAGE_ROLE_ID = Path(os.environ.get(
    "JASON_OPENAI_USAGE_ROLE_ID_PATH",
    "/var/lib/jason/runtime-secrets/openbao/openai-usage-reporting-approle/role-id",
))
_OPENAI_USAGE_SECRET_ID = Path(os.environ.get(
    "JASON_OPENAI_USAGE_SECRET_ID_PATH",
    "/var/lib/jason/runtime-secrets/openbao/openai-usage-reporting-approle/secret-id",
))
_OPENAI_USAGE_CACHE_SECONDS = max(
    60, int(os.environ.get("JASON_OPENAI_USAGE_CACHE_SECONDS", "300"))
)
_OPENAI_USAGE_TIMEOUT_SECONDS = float(
    os.environ.get("JASON_OPENAI_USAGE_TIMEOUT_SECONDS", "20")
)
_OPENAI_USAGE_CACHE: dict[str, object] = {
    "expires_at": 0.0,
    "snapshot": None,
    "last_success": None,
}


def _valid_email(value: object) -> str:
    text = str(value or "").strip()
    if not text or "@" not in text or text.startswith("@") or text.endswith("@"):
        return ""
    return text


def _directory_emails(events: list[dict]) -> dict[str, str]:
    """Return latest safe directory email enrichment by stable Jason identity."""

    result: dict[str, str] = {}
    for event in events:
        if event.get("event_type") != "identity.directory.completed":
            continue
        actor_id = str(event.get("principal_id") or "").strip()
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
        email = _valid_email(details.get("email_address"))
        if actor_id and email:
            result[actor_id] = email
    return result


def _governed_requests(events: list[dict]) -> dict[str, dict[str, str]]:
    """Index the minimum safe actor metadata needed for correlation enrichment."""

    result: dict[str, dict[str, str]] = {}
    for event in events:
        if event.get("event_type") != "orchestration.request.received":
            continue
        correlation_id = str(event.get("correlation_id") or "").strip()
        if not correlation_id:
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        result[correlation_id] = {
            "actor_type": base._actor_type(payload.get("requester_kind")),
            "principal_id": str(event.get("principal_id") or "").strip(),
            "capability": str(event.get("capability") or "").strip(),
        }
    return result


def _orchestration_events() -> list[dict]:
    """Load orchestration events and prepare read-only correlation indexes."""

    global _REQUEST_BY_CORRELATION, _DIRECTORY_EMAILS
    events = _ORIGINAL_ORCHESTRATION_EVENTS()
    _REQUEST_BY_CORRELATION = _governed_requests(events)
    _DIRECTORY_EMAILS = _directory_emails(events)
    return events


def _model_event(entry: dict, emails: dict[str, str]) -> dict | None:
    """Normalize model usage and enrich only otherwise-unknown actors by correlation.

    A model call that occurred before Jason bound a human remains unknown in the
    immutable ledger. If the same correlation later entered the governed orchestrator,
    this read-only presentation layer can show that stable Jason principal as inferred
    attribution while preserving the original model purpose/capability metadata.
    """

    friendly_emails = dict(emails)
    friendly_emails.update(_DIRECTORY_EMAILS)
    normalized = _ORIGINAL_MODEL_EVENT(entry, friendly_emails)
    if normalized is None or normalized.get("attributable"):
        return normalized

    correlation_id = str(normalized.get("correlation_id") or "").strip()
    request = _REQUEST_BY_CORRELATION.get(correlation_id)
    if not request:
        return normalized

    actor_id = str(request.get("principal_id") or "").strip()
    actor_type = base._actor_type(request.get("actor_type"))
    if not actor_id or actor_type == "unknown":
        return normalized

    enriched = dict(normalized)
    enriched["actor_id"] = actor_id
    enriched["actor_type"] = actor_type
    enriched["email"] = friendly_emails.get(actor_id, "")
    enriched["workload_name"] = actor_id if actor_type != "human" else ""
    enriched["attributable"] = True
    # The underlying token/cost facts remain unchanged, but the exported event
    # is correlation-attributed rather than ledger-native, so its overall
    # telemetry quality is conservatively reported as inferred.
    enriched["telemetry_quality"] = "inferred"
    return enriched


def _provider_events(events: list[dict], emails: dict[str, str]) -> list[dict]:
    """Normalize observable external provider request attempts.

    The event parser deliberately reads only an allowlisted set of audit fields.
    Tokens, provider responses, Microsoft tenant/object identifiers, recipient
    addresses, raw evidence, and arbitrary payload values are not exported.
    """

    request_by_correlation = _governed_requests(events)

    friendly_emails = dict(emails)
    friendly_emails.update(_directory_emails(events))

    result: list[dict] = []
    accepted = {
        "connector.requested",
        "email.send.attempted",
        "identity.directory.requested",
    }

    for event in events:
        event_type = str(event.get("event_type") or "")
        if event_type not in accepted:
            continue

        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
        correlation_id = str(event.get("correlation_id") or "").strip()
        request = request_by_correlation.get(correlation_id, {})

        actor_id = str(
            event.get("principal_id")
            or request.get("principal_id")
            or "unknown"
        ).strip() or "unknown"

        actor_type = base._actor_type(
            request.get("actor_type") or payload.get("requester_kind")
        )
        if actor_type == "unknown" and event_type == "identity.directory.requested" and actor_id != "unknown":
            actor_type = "human"
        if actor_type == "unknown" and actor_id != "unknown" and correlation_id.startswith("corr_mcp_"):
            actor_type = "human"

        capability = str(
            event.get("capability")
            or request.get("capability")
            or "unknown"
        ).strip() or "unknown"

        if event_type == "email.send.attempted":
            provider = "aws_ses"
            operation = "email.send"
            source_channel = str(details.get("source_channel") or "").strip()
            purpose = str(details.get("purpose") or "Send governed email").strip()
        elif event_type == "identity.directory.requested":
            provider = "microsoft_graph"
            operation = str(details.get("operation") or "user.profile.read").strip()
            source_channel = str(details.get("source_channel") or "teams").strip() or "teams"
            purpose = str(
                details.get("purpose")
                or "Enrich authenticated Jason human identity with directory email"
            ).strip()
        else:
            provider = str(
                details.get("provider")
                or payload.get("provider")
                or "unknown"
            ).strip() or "unknown"
            operation = str(
                details.get("operation")
                or payload.get("operation")
                or capability
            ).strip() or capability
            source_channel = str(details.get("source_channel") or "").strip()
            purpose = str(details.get("purpose") or "").strip()

        if not source_channel:
            source_channel = base._channel(correlation_id, actor_type)
        if not purpose:
            purpose = f"{capability}: {operation}"

        occurred_at = event.get("occurred_at")
        if occurred_at is None:
            continue

        email = friendly_emails.get(actor_id, "")
        attributable = actor_id != "unknown" and actor_type != "unknown"

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
                "purpose": purpose,
                "capability": capability,
                "provider": provider,
                "product": base._provider_product(provider),
                "service": operation,
                "billing_class": base._billing_class(provider),
                "telemetry_quality": "exact",
                "usage_quantity": 1,
                "usage_unit": "request",
                "cost": Decimal("0"),
                "outcome": "attempted",
                "correlation_id": correlation_id,
                "request_id": str(payload.get("request_id") or event.get("execution_id") or ""),
                "attributable": attributable,
            }
        )

    return result


class _OpenAIUsageError(RuntimeError):
    """Safe usage-query failure that never includes credential values."""


def _http_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    merged = {"Accept": "application/json"}
    merged.update(headers or {})
    if body is not None:
        merged["Content-Type"] = "application/json"
    req = request.Request(url, data=body, headers=merged, method=method)
    try:
        with request.urlopen(req, timeout=_OPENAI_USAGE_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        raise _OpenAIUsageError(f"HTTP request failed with status {exc.code}.") from exc
    except (error.URLError, TimeoutError, OSError) as exc:
        raise _OpenAIUsageError("HTTP request failed.") from exc
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _OpenAIUsageError("HTTP endpoint returned malformed JSON.") from exc
    if not isinstance(value, dict):
        raise _OpenAIUsageError("HTTP endpoint returned an unexpected payload.")
    return value


def _openbao_token() -> str:
    role_id = _OPENAI_USAGE_ROLE_ID.read_text(encoding="utf-8").strip()
    secret_id = _OPENAI_USAGE_SECRET_ID.read_text(encoding="utf-8").strip()
    if not role_id or not secret_id:
        raise _OpenAIUsageError("OpenAI usage AppRole credentials are incomplete.")
    response = _http_json(
        f"{_OPENBAO_URL}/v1/auth/approle/login",
        method="POST",
        payload={"role_id": role_id, "secret_id": secret_id},
    )
    token = str((response.get("auth") or {}).get("client_token") or "").strip()
    if not token:
        raise _OpenAIUsageError("OpenBao did not issue a runtime token.")
    return token


def _openai_admin_key(token: str) -> str:
    response = _http_json(
        f"{_OPENBAO_URL}/v1/secret/data/providers/openai/production/usage-reporting",
        headers={"X-Vault-Token": token},
    )
    key = str(
        (((response.get("data") or {}).get("data") or {}).get("admin_api_key"))
        or ""
    ).strip()
    if not key:
        raise _OpenAIUsageError("OpenAI usage credential is unavailable.")
    return key


def _revoke_openbao_token(token: str) -> None:
    try:
        _http_json(
            f"{_OPENBAO_URL}/v1/auth/token/revoke-self",
            method="POST",
            payload={},
            headers={"X-Vault-Token": token},
        )
    except _OpenAIUsageError:
        pass


def _openai_get(path: str, params: list[tuple[str, str]], admin_key: str) -> list[dict]:
    buckets: list[dict] = []
    page = ""
    for _ in range(10):
        query = list(params)
        if page:
            query.append(("page", page))
        response = _http_json(
            f"{_OPENAI_API_BASE}{path}?{parse.urlencode(query)}",
            headers={"Authorization": f"Bearer {admin_key}"},
        )
        buckets.extend(
            item for item in response.get("data", []) if isinstance(item, dict)
        )
        if not response.get("has_more"):
            return buckets
        page = str(response.get("next_page") or "").strip()
        if not page:
            return buckets
    raise _OpenAIUsageError("OpenAI pagination exceeded the safety bound.")


def _openai_dimension_names(
    admin_key: str,
    dimensions: set[tuple[str, str]],
) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    projects: dict[str, str] = {}
    keys: dict[tuple[str, str], str] = {}
    for project_id, api_key_id in sorted(dimensions):
        if project_id and project_id not in projects:
            try:
                item = _http_json(
                    f"{_OPENAI_API_BASE}/organization/projects/{parse.quote(project_id)}",
                    headers={"Authorization": f"Bearer {admin_key}"},
                )
                projects[project_id] = str(item.get("name") or project_id)
            except _OpenAIUsageError:
                projects[project_id] = project_id
        if project_id and api_key_id:
            try:
                item = _http_json(
                    f"{_OPENAI_API_BASE}/organization/projects/"
                    f"{parse.quote(project_id)}/api_keys/{parse.quote(api_key_id)}",
                    headers={"Authorization": f"Bearer {admin_key}"},
                )
                keys[(project_id, api_key_id)] = str(item.get("name") or api_key_id)
            except _OpenAIUsageError:
                keys[(project_id, api_key_id)] = api_key_id
    return projects, keys


def _fetch_openai_org_snapshot(now: datetime) -> dict[str, object]:
    now = now.astimezone(timezone.utc)
    start = now - timedelta(hours=24)
    token = _openbao_token()
    admin_key = ""
    try:
        admin_key = _openai_admin_key(token)
        common = [
            ("start_time", str(int(start.timestamp()))),
            ("end_time", str(int(now.timestamp()))),
        ]
        usage_buckets = _openai_get(
            "/organization/usage/completions",
            common + [
                ("bucket_width", "1h"),
                ("limit", "24"),
                ("group_by", "model"),
                ("group_by", "project_id"),
                ("group_by", "api_key_id"),
            ],
            admin_key,
        )
        cost_buckets = _openai_get(
            "/organization/costs",
            common + [
                ("bucket_width", "1d"),
                ("limit", "2"),
                ("group_by", "project_id"),
                ("group_by", "line_item"),
            ],
            admin_key,
        )

        detail: dict[tuple[str, str, str], dict[str, int]] = {}
        totals = {"requests": 0, "input": 0, "cached_input": 0, "output": 0}
        last_activity = 0
        for bucket in usage_buckets:
            bucket_end = int(bucket.get("end_time") or 0)
            for result in bucket.get("results", []):
                if not isinstance(result, dict):
                    continue
                dimension = (
                    str(result.get("model") or "unknown"),
                    str(result.get("project_id") or ""),
                    str(result.get("api_key_id") or ""),
                )
                row = detail.setdefault(
                    dimension,
                    {"requests": 0, "input": 0, "cached_input": 0, "output": 0},
                )
                values = {
                    "requests": int(result.get("num_model_requests") or 0),
                    "input": int(result.get("input_tokens") or 0),
                    "cached_input": int(result.get("input_cached_tokens") or 0),
                    "output": int(result.get("output_tokens") or 0),
                }
                for name, value in values.items():
                    row[name] += value
                    totals[name] += value
                if values["requests"] > 0:
                    last_activity = max(last_activity, bucket_end)

        dimensions = {(project_id, api_key_id) for _, project_id, api_key_id in detail}
        projects, keys = _openai_dimension_names(admin_key, dimensions)
        rows = [
            {
                "model": model,
                "project_id": project_id,
                "project": projects.get(project_id, project_id or "unknown"),
                "api_key_id": api_key_id,
                "api_key": keys.get((project_id, api_key_id), api_key_id or "unknown"),
                **values,
            }
            for (model, project_id, api_key_id), values in sorted(detail.items())
        ]

        cost_usd = Decimal("0")
        for bucket in cost_buckets:
            for result in bucket.get("results", []):
                if not isinstance(result, dict):
                    continue
                amount = result.get("amount")
                if not isinstance(amount, dict):
                    continue
                if str(amount.get("currency") or "usd").casefold() != "usd":
                    continue
                try:
                    cost_usd += Decimal(str(amount.get("value") or "0"))
                except Exception:
                    continue

        return {
            "source_available": 1,
            "cost_source_available": 1,
            "fetched_at": now.timestamp(),
            "last_activity": float(last_activity),
            "cost_usd": cost_usd,
            "rows": rows,
            **totals,
        }
    finally:
        admin_key = ""
        _revoke_openbao_token(token)


def _openai_org_snapshot(now: datetime) -> dict[str, object]:
    clock = time.monotonic()
    cached = _OPENAI_USAGE_CACHE.get("snapshot")
    if isinstance(cached, dict) and clock < float(_OPENAI_USAGE_CACHE["expires_at"]):
        return dict(cached)
    try:
        current = _fetch_openai_org_snapshot(now)
        _OPENAI_USAGE_CACHE["snapshot"] = current
        _OPENAI_USAGE_CACHE["last_success"] = current
        _OPENAI_USAGE_CACHE["expires_at"] = clock + _OPENAI_USAGE_CACHE_SECONDS
        return dict(current)
    except (_OpenAIUsageError, OSError, ValueError):
        previous = _OPENAI_USAGE_CACHE.get("last_success")
        if isinstance(previous, dict):
            degraded = dict(previous)
            degraded["source_available"] = 0
            degraded["cost_source_available"] = 0
            _OPENAI_USAGE_CACHE["snapshot"] = degraded
            _OPENAI_USAGE_CACHE["expires_at"] = clock + 60
            return degraded
        return {
            "source_available": 0, "cost_source_available": 0,
            "fetched_at": 0.0, "last_activity": 0.0,
            "cost_usd": Decimal("0"), "rows": [],
            "requests": 0, "input": 0, "cached_input": 0, "output": 0,
        }


def _render_openai_org_metrics(now: datetime) -> str:
    data = _openai_org_snapshot(now)
    lines = [
        "# HELP jason_openai_org_usage_source_available Whether authoritative OpenAI organization usage is reachable.",
        "# TYPE jason_openai_org_usage_source_available gauge",
        f"jason_openai_org_usage_source_available {int(data['source_available'])}",
        "# HELP jason_openai_org_cost_source_available Whether authoritative OpenAI organization costs are reachable.",
        "# TYPE jason_openai_org_cost_source_available gauge",
        f"jason_openai_org_cost_source_available {int(data['cost_source_available'])}",
        "# HELP jason_openai_org_requests_24h OpenAI requests reported over the rolling 24h window.",
        "# TYPE jason_openai_org_requests_24h gauge",
        f"jason_openai_org_requests_24h {int(data['requests'])}",
        "# HELP jason_openai_org_tokens_24h OpenAI tokens reported over the rolling 24h window.",
        "# TYPE jason_openai_org_tokens_24h gauge",
        f'jason_openai_org_tokens_24h{{token_type="input"}} {int(data["input"])}',
        f'jason_openai_org_tokens_24h{{token_type="cached_input"}} {int(data["cached_input"])}',
        f'jason_openai_org_tokens_24h{{token_type="output"}} {int(data["output"])}',
        "# HELP jason_openai_org_cost_usd_24h Cost reported by OpenAI for the rolling 24h query window.",
        "# TYPE jason_openai_org_cost_usd_24h gauge",
        f"jason_openai_org_cost_usd_24h {Decimal(data['cost_usd']):.8f}",
        "# HELP jason_openai_org_last_activity_timestamp_seconds End of the newest usage bucket containing requests.",
        "# TYPE jason_openai_org_last_activity_timestamp_seconds gauge",
        f"jason_openai_org_last_activity_timestamp_seconds {float(data['last_activity']):.3f}",
        "# HELP jason_openai_org_snapshot_timestamp_seconds Timestamp of the last successful organization snapshot.",
        "# TYPE jason_openai_org_snapshot_timestamp_seconds gauge",
        f"jason_openai_org_snapshot_timestamp_seconds {float(data['fetched_at']):.3f}",
        "# HELP jason_openai_org_usage_by_dimension_24h OpenAI usage grouped by model, project and API key.",
        "# TYPE jason_openai_org_usage_by_dimension_24h gauge",
    ]
    for row in data["rows"]:
        labels = {
            "model": row["model"], "project": row["project"],
            "project_id": row["project_id"], "api_key_name": row["api_key"],
            "api_key_id": row["api_key_id"],
        }
        for usage_type, field in (
            ("requests", "requests"), ("input_tokens", "input"),
            ("cached_input_tokens", "cached_input"), ("output_tokens", "output"),
        ):
            label_text = base._labels({**labels, "usage_type": usage_type})
            lines.append(
                f"jason_openai_org_usage_by_dimension_24h{{{label_text}}} {int(row[field])}"
            )
    provider_labels = base._labels({
        "provider": "openai", "product": "OpenAI API",
        "billing_class": "metered", "telemetry_quality": "provider_reported",
    })
    lines.append(
        f"jason_usage_provider_events_24h{{{provider_labels}}} {int(data['requests'])}"
    )
    return "\n".join(lines) + "\n"


def _render_metrics(now: datetime | None = None) -> str:
    resolved = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return _ORIGINAL_RENDER_METRICS(resolved) + _render_openai_org_metrics(resolved)


# Keep the dashboard's existing metric contract while extending safe runtime parsing.
base._orchestration_events = _orchestration_events
base._model_event = _model_event
base._provider_events = _provider_events
base.render_metrics = _render_metrics


if __name__ == "__main__":
    server = HTTPServer((base.HOST, base.PORT), base.Handler)
    print(
        f"Jason usage attribution exporter listening on {base.HOST}:{base.PORT}",
        flush=True,
    )
    server.serve_forever()
