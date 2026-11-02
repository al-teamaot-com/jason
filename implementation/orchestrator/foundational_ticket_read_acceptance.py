"""Bounded, privacy-minimizing foundational Autotask ticket read acceptance.

This routine performs NO direct provider/network calls. Its injected read port
MUST already be bound to an authenticated and independently authorized requester
through JKD-001 / the Central Orchestrator. It cannot grant source release
rights, impersonate a technician, or prove its caller's identity.

A PASS here proves only functional consistency of the supplied, authorized
observations: count, complete cursor pagination, and one exact resource read.
It does not replace a cryptographically verified authority receipt or permit
production promotion by itself.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any, Callable, Mapping


SHA = re.compile(r"^[0-9a-f]{40}$")
CAPABILITY_COUNT = "service.ticket.count"
CAPABILITY_SEARCH = "service.ticket.search"
CAPABILITY_READ = "service.ticket.read"


class TicketReadCanaryError(ValueError):
    """Safe non-sensitive reason for refusing an incomplete read canary."""


def _timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise TicketReadCanaryError("invalid_timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise TicketReadCanaryError("invalid_timestamp") from None
    if parsed.tzinfo is None:
        raise TicketReadCanaryError("timezone_required")
    return parsed.astimezone(timezone.utc)


def _data(
    response: Mapping[str, Any],
    *,
    capability: str,
) -> Mapping[str, Any]:
    if not isinstance(response, Mapping):
        raise TicketReadCanaryError("malformed_read_response")
    if (response.get("status") != "succeeded"
            or response.get("provider") != "autotask"
            or response.get("error_code") is not None):
        raise TicketReadCanaryError("governed_read_not_successful")
    if response.get("capability") not in (None, capability):
        raise TicketReadCanaryError("read_capability_mismatch")
    evidence = response.get("evidence")
    if not isinstance(evidence, Mapping):
        raise TicketReadCanaryError("read_evidence_missing")
    data = evidence.get("data")
    if not isinstance(data, Mapping):
        raise TicketReadCanaryError("read_data_missing")
    return data


def _ticket_ids(data: Mapping[str, Any]) -> tuple[int, ...]:
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise TicketReadCanaryError("ticket_list_empty_or_malformed")
    ids = []
    for item in items:
        if not isinstance(item, Mapping):
            raise TicketReadCanaryError("ticket_item_malformed")
        identifier = item.get("id")
        if type(identifier) is not int or identifier <= 0:
            raise TicketReadCanaryError("ticket_identifier_invalid")
        ids.append(identifier)
    return tuple(ids)


def run_ticket_read_canary(
    read: Callable[[str, Mapping[str, Any]], Mapping[str, Any]],
    *,
    release_candidate_sha: str,
    running_revision: str,
    phase: str,
    created_after: str,
    created_before: str,
    page_size: int = 5,
    max_pages: int = 50,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run count -> exhaustive cursor search -> exact read through a bound port.

    Returns only a content-free summary. Never returns ticket IDs, ticket
    bodies, company names, user data, ticket descriptions, or provider outputs.
    Any error fails closed with an allowlisted reason, not raw provider text.
    """
    if (not isinstance(release_candidate_sha, str)
            or SHA.fullmatch(release_candidate_sha) is None
            or not isinstance(running_revision, str)
            or SHA.fullmatch(running_revision) is None):
        raise TicketReadCanaryError("invalid_source_revision")
    if phase not in ("before", "after"):
        raise TicketReadCanaryError("invalid_phase")
    if phase == "after" and running_revision != release_candidate_sha:
        raise TicketReadCanaryError("post_release_revision_mismatch")
    if (type(page_size) is not int or not 1 <= page_size <= 100
            or type(max_pages) is not int or not 1 <= max_pages <= 50):
        raise TicketReadCanaryError("unbounded_page_budget")
    start = _timestamp(created_after)
    end = _timestamp(created_before)
    instant = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if not (start < end <= instant + timedelta(seconds=10)):
        raise TicketReadCanaryError("invalid_bounded_window")
    if end - start > timedelta(days=7):
        raise TicketReadCanaryError("sample_window_too_wide")

    filters = {"created_after": created_after, "created_before": created_before}

    def governed(capability: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            response = read(capability, dict(arguments))
        except Exception:
            # Never expose a provider exception that might include customer
            # ticket metadata, credentials, or a raw provider payload.
            raise TicketReadCanaryError("governed_read_exception") from None
        return _data(response, capability=capability)

    count_data = governed(CAPABILITY_COUNT, filters)
    count = count_data.get("queryCount")
    if type(count) is not int or count <= 0:
        raise TicketReadCanaryError("count_missing_or_empty")
    if count > page_size * max_pages:
        raise TicketReadCanaryError("sample_exceeds_page_budget")

    ticket_ids: set[int] = set()
    read_id = None
    cursor: int | None = None
    page_count = 0

    while len(ticket_ids) < count:
        if page_count >= max_pages:
            raise TicketReadCanaryError("pagination_budget_exhausted")
        arguments: dict[str, Any] = {**filters, "page_size": page_size}
        if cursor is not None:
            arguments["after_resource_id"] = cursor
        page_data = governed(CAPABILITY_SEARCH, arguments)
        page_ids = _ticket_ids(page_data)
        if len(page_ids) > page_size:
            raise TicketReadCanaryError("page_exceeds_requested_size")
        if len(page_ids) != len(set(page_ids)):
            raise TicketReadCanaryError("duplicate_ticket_on_page")
        if any(identifier in ticket_ids or
               (cursor is not None and identifier <= cursor)
               for identifier in page_ids):
            raise TicketReadCanaryError("pagination_repeated_or_regressed")
        if tuple(sorted(page_ids)) != page_ids:
            raise TicketReadCanaryError("page_order_unstable")
        if len(ticket_ids) + len(page_ids) > count:
            raise TicketReadCanaryError("search_exceeds_count")

        if read_id is None:
            read_id = page_ids[0]
        ticket_ids.update(page_ids)
        cursor = page_ids[-1]
        page_count += 1

    if len(ticket_ids) != count or read_id is None:
        raise TicketReadCanaryError("pagination_incomplete")

    read_data = governed(CAPABILITY_READ, {"resource_id": read_id})
    returned_ids = _ticket_ids(read_data)
    if returned_ids != (read_id,):
        raise TicketReadCanaryError("exact_ticket_read_mismatch")

    return {
        "schema_version": "1.0",
        "status": "PASS",
        "phase": phase,
        "release_candidate_sha": release_candidate_sha,
        "running_revision": running_revision,
        "created_after": start.isoformat(),
        "created_before": end.isoformat(),
        "observed_at": instant.isoformat(),
        "provider": "autotask",
        "count_verified": count,
        "enumerated_count": len(ticket_ids),
        "pages_verified": page_count,
        "exact_ticket_read_verified": True,
        "provider_error_count": 0,
        "raw_customer_content_retained": False,
        "independent_requester_authorization_required": True,
    }
