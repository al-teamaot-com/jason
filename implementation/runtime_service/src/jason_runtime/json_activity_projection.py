"""Source-only deterministic JSON Activity projection plan.

Reuses the currently deployed pure managed-ticket-note formatting logic.
No action is executed, no provider read is initiated, and no approval is
granted. Provider evidence must come from the existing governed read port.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping, Sequence

from .managed_ticket_notes import (
    JASON_ACTIVITY_TITLE, exact_named_note, render_activity_chunks,
    managed_note_mutation, ManagedTicketNoteError,
)


class JsonActivityProjectionBoundaryError(RuntimeError):
    pass


@dataclass(frozen=True)
class ActivityProjectionIntent:
    title: str
    disposition: str
    capability: str | None
    arguments: Mapping[str, Any] | None
    prior_sha256: str | None
    revised_sha256: str | None
    source_rows: int


def _notes(response: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if response.get("status") != "succeeded":
        raise JsonActivityProjectionBoundaryError("ACTIVITY_GOVERNED_NOTE_READ_NOT_SUCCEEDED")
    evidence = response.get("evidence")
    data = evidence.get("data") if isinstance(evidence, Mapping) else None
    if not isinstance(data, Mapping) or not isinstance(data.get("items"), list):
        raise JsonActivityProjectionBoundaryError("ACTIVITY_NOTE_LIST_NOT_AUTHORITATIVE")
    if any(not isinstance(x, Mapping) for x in data["items"]):
        raise JsonActivityProjectionBoundaryError("ACTIVITY_NOTE_RESULT_INVALID")
    if any(data.get(k) for k in ("has_more", "next_cursor", "nextCursor")):
        raise JsonActivityProjectionBoundaryError("ACTIVITY_NOTE_LIST_TRUNCATED")
    return data["items"]


def plan_activity_projection(
    *,
    ticket_id: int,
    client_id: str,
    exact_current_ticket: Mapping[str, Any],
    local_ticket_id: int,
    local_activity_rows: Sequence[Mapping[str, Any]],
    governed_note_search: Mapping[str, Any],
    jason_creator_resource_id: int,
    max_body_chars: int = 7000,
) -> tuple[ActivityProjectionIntent, ...]:
    if (not isinstance(ticket_id, int) or ticket_id < 1 or
        not client_id or local_ticket_id != ticket_id or
        str(exact_current_ticket.get("id")) != str(ticket_id) or
        str(exact_current_ticket.get("companyID")) != str(client_id) or
        not isinstance(jason_creator_resource_id, int) or
        jason_creator_resource_id < 1):
        raise JsonActivityProjectionBoundaryError("ACTIVITY_EXACT_TICKET_SCOPE_MISSING")
    notes = _notes(governed_note_search)
    chunks = render_activity_chunks(local_activity_rows, max_body_chars=max_body_chars)
    if not chunks:
        return ()
    output = []
    for title, body in chunks:
        try:
            existing = exact_named_note(notes, title=title)
        except ManagedTicketNoteError as exc:
            raise JsonActivityProjectionBoundaryError("ACTIVITY_DUPLICATE_MANAGED_TITLE") from exc
        if existing is not None:
            creator = existing.get("creatorResourceID")
            if (str(existing.get("ticketID")) != str(ticket_id) or
                str(creator) != str(jason_creator_resource_id) or
                existing.get("noteType") != 3 or existing.get("publish") != 2):
                raise JsonActivityProjectionBoundaryError("ACTIVITY_NOTE_NOT_JASON_OWNED_INTERNAL")
            old = str(existing.get("description") or "")
            if old == body:
                output.append(ActivityProjectionIntent(
                    title, "current", None, None, sha256(old.encode()).hexdigest(),
                    sha256(body.encode()).hexdigest(), len(local_activity_rows),
                ))
                continue
            # Activity chunks are append-only. A changing historical chunk is
            # a source discrepancy, NOT permission to overwrite past history.
            if not body.startswith(old) or not old:
                raise JsonActivityProjectionBoundaryError("ACTIVITY_NON_APPEND_UPDATE_FORBIDDEN")
        else:
            old = None
        try:
            mutation = managed_note_mutation(
                ticket_id=ticket_id, title=title, body=body, notes=notes,
            )
        except ManagedTicketNoteError as exc:
            raise JsonActivityProjectionBoundaryError("ACTIVITY_MUTATION_PLAN_INVALID") from exc
        output.append(ActivityProjectionIntent(
            title, "create" if existing is None else "update",
            mutation.capability, {"payload": dict(mutation.payload)},
            sha256(old.encode()).hexdigest() if old is not None else None,
            sha256(body.encode()).hexdigest(), len(local_activity_rows),
        ))
    # Defensive: the original worker currently lacks a strict ownership/readback
    # per individual note; this source-only planner is intentionally stricter.
    return tuple(output)
