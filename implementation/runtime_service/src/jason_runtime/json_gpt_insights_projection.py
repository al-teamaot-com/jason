"""GPT Insights immutable source-only projection using deployed pure functions.

This module never issues a provider read or mutation; all evidence/authority
is supplied by existing governed connectors and persisted augmentation state.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping, Sequence

from .gpt_insights import (
    BASE_TITLE, InsightEvidence, classify_ticket,
    material_fingerprint, render_insight,
)
from .managed_ticket_notes import exact_named_note, managed_note_mutation, ManagedTicketNoteError


class JsonGptInsightsBoundaryError(RuntimeError):
    pass


@dataclass(frozen=True)
class GptInsightProjection:
    disposition: str
    category: str
    fingerprint: str
    body: str
    capability: str | None
    arguments: Mapping[str, Any] | None
    previous_sha256: str | None
    revised_sha256: str | None


def plan_gpt_insights(
    *,
    ticket: Mapping[str, Any],
    ticket_id: int,
    client_id: str,
    source_queue: str,
    source_status: str,
    source_label: str,
    device_identity_verified: bool,
    evidence: InsightEvidence,
    notes_response: Mapping[str, Any],
    prior_fingerprint: str | None,
    jason_creator_id: int,
) -> GptInsightProjection:
    if (not isinstance(ticket_id, int) or ticket_id < 1 or
        str(ticket.get("id")) != str(ticket_id) or
        str(ticket.get("companyID")) != str(client_id) or
        not client_id):
        raise JsonGptInsightsBoundaryError("GPT_INSIGHTS_TICKET_SCOPE_UNVERIFIED")
    if (source_queue.strip().casefold() != "help desk i" or
        source_status.strip().casefold() != "new" or
        source_label.strip().casefold() == "recurring"):
        return GptInsightProjection("ineligible", "none", "", "", None, None, None, None)
    category = classify_ticket(
        str(ticket.get("title") or ""),
        str(ticket.get("description") or ""),
    )
    if category != evidence.category or (
        str(ticket.get("ticketNumber") or ticket_id) != evidence.ticket_number
    ):
        raise JsonGptInsightsBoundaryError("GPT_INSIGHTS_CLASSIFICATION_NOT_SOURCE_BOUND")
    if evidence.device_name is not None and device_identity_verified is not True:
        raise JsonGptInsightsBoundaryError("GPT_INSIGHTS_DEVICE_IDENTITY_NOT_VERIFIED")
    response = notes_response
    if response.get("status") != "succeeded":
        raise JsonGptInsightsBoundaryError("GPT_INSIGHTS_NOTES_READ_FAILED")
    data = response.get("evidence")
    data = data.get("data") if isinstance(data, Mapping) else None
    if not isinstance(data, Mapping) or not isinstance(data.get("items"), list):
        raise JsonGptInsightsBoundaryError("GPT_INSIGHTS_AUTHORITATIVE_NOTES_MISSING")
    if data.get("has_more") or data.get("next_cursor") or data.get("nextCursor"):
        raise JsonGptInsightsBoundaryError("GPT_INSIGHTS_NOTES_PAGINATED")
    notes = data["items"]
    if any(not isinstance(note, Mapping) for note in notes):
        raise JsonGptInsightsBoundaryError("GPT_INSIGHTS_NOTE_ITEM_INVALID")
    try:
        existing = exact_named_note(notes, title=BASE_TITLE)
    except ManagedTicketNoteError as exc:
        raise JsonGptInsightsBoundaryError("GPT_INSIGHTS_DUPLICATE_BASE_NOTE") from exc
    fingerprint = material_fingerprint(evidence)
    body = render_insight(evidence)
    revised_sha = sha256(body.encode()).hexdigest()
    if existing is not None:
        if (str(existing.get("ticketID")) != str(ticket_id) or
            str(existing.get("creatorResourceID")) != str(jason_creator_id) or
            existing.get("publish") != 2 or existing.get("noteType") != 3):
            raise JsonGptInsightsBoundaryError("GPT_INSIGHTS_BASE_NOTE_NOT_JASON_INTERNAL")
        previous = str(existing.get("description") or "")
        prior_sha = sha256(previous.encode()).hexdigest()
        if prior_fingerprint is None:
            # Legacy behavior seeds persisted augmentation state on database reset;
            # no retroactive rewrite of a managed note.
            return GptInsightProjection(
                "seed_existing", category, fingerprint, body,
                None, None, prior_sha, revised_sha)
        if prior_fingerprint == fingerprint:
            return GptInsightProjection(
                "current", category, fingerprint, body,
                None, None, prior_sha, revised_sha)
    else:
        prior_sha = None
        if prior_fingerprint == fingerprint:
            # Local cache may be stale after provider deletion. Do not silently
            # claim current without a note, but do not recreate blindly.
            raise JsonGptInsightsBoundaryError("GPT_INSIGHTS_MISSING_BASE_STATE_CONFLICT")
    try:
        mutation = managed_note_mutation(
            ticket_id=ticket_id, title=BASE_TITLE, body=body, notes=notes)
    except ManagedTicketNoteError as exc:
        raise JsonGptInsightsBoundaryError("GPT_INSIGHTS_MANAGED_MUTATION_INVALID") from exc
    return GptInsightProjection(
        "update" if existing else "create", category, fingerprint, body,
        mutation.capability, {"payload": dict(mutation.payload)},
        prior_sha, revised_sha)
