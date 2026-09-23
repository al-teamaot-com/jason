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

from decimal import Decimal
from http.server import HTTPServer

import usage_attribution_exporter as base


_ORIGINAL_ORCHESTRATION_EVENTS = base._orchestration_events
_ORIGINAL_MODEL_EVENT = base._model_event
_REQUEST_BY_CORRELATION: dict[str, dict[str, str]] = {}
_DIRECTORY_EMAILS: dict[str, str] = {}


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


# Keep the dashboard's existing metric contract while extending safe runtime parsing.
base._orchestration_events = _orchestration_events
base._model_event = _model_event
base._provider_events = _provider_events


if __name__ == "__main__":
    server = HTTPServer((base.HOST, base.PORT), base.Handler)
    print(
        f"Jason usage attribution exporter listening on {base.HOST}:{base.PORT}",
        flush=True,
    )
    server.serve_forever()
