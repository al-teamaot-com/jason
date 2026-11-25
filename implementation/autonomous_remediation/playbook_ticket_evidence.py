"""Reusable, read-only exact ticket evidence guard for JSON playbook facts.

Consumes responses supplied by the existing governed read port. It never
executes a capability, queries a provider, stores credentials, grants approval,
or creates execution authority. A caller must independently verify Owner
promotion through the existing governed promotion store before proposing any
action. The output intentionally contains no approval or action grant fact.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Any, Mapping, Sequence

HANDOFF_STATES = frozenset({
    "needs_human_review", "needs_device_identity", "needs_execution_authority",
    "needs_security_review", "needs_playbook_review", "needs_diagnostic_evidence",
    "read_only_assessed",
})
SAFE_SOURCE_STATUSES = frozenset({"new", "in progress"})
MANAGED_NOTE_TITLE = "Jason - Governed Read-Only Investigation"


class UntrustedTicketEvidence(ValueError):
    """A required authoritative current-state read or identity proof is missing."""


def _records(response: Mapping[str, Any], *, capability: str) -> list[Mapping[str, Any]]:
    if response.get("status") != "succeeded":
        raise UntrustedTicketEvidence(f"{capability}:GOVERNED_READ_NOT_SUCCEEDED")
    evidence = response.get("evidence")
    data = evidence.get("data") if isinstance(evidence, Mapping) else None
    items = data.get("items") if isinstance(data, Mapping) else None
    if not isinstance(items, list) or any(not isinstance(x, Mapping) for x in items):
        raise UntrustedTicketEvidence(f"{capability}:EXACT_PROVIDER_ITEMS_MISSING")
    return items


def handoff_identity_facts(
    *,
    source_snapshot: Mapping[str, Any],
    source_queue: str,
    owned_by_jason: bool,
    source_status_label: str,
    review_reason: str,
    ticket_search_result: Mapping[str, Any],
    notes_search_result: Mapping[str, Any],
    expected_note_body: str,
    permitted_ticket_ids: frozenset[int],
) -> Mapping[str, Any]:
    """Verify exact current Autotask ticket and managed internal note.

    No fact about approval, post-action readback, provider authority, or
    successful handoff is generated. Those require separate governed evidence.
    """
    try:
        ticket_id = int(source_snapshot["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise UntrustedTicketEvidence("TICKET_ID_MISSING") from exc
    if ticket_id not in permitted_ticket_ids:
        raise UntrustedTicketEvidence("TICKET_NOT_IN_EXACT_PILOT")
    if not owned_by_jason or str(source_queue).strip().casefold() != "jason":
        raise UntrustedTicketEvidence("TICKET_NOT_JASON_OWNED")
    status = str(source_status_label).strip().casefold()
    if status not in SAFE_SOURCE_STATUSES:
        raise UntrustedTicketEvidence("SOURCE_STATUS_NOT_ELIGIBLE")
    reason = str(review_reason).strip()
    if reason not in HANDOFF_STATES:
        raise UntrustedTicketEvidence("HANDOFF_STATE_NOT_ELIGIBLE")
    required_fields = ("companyID", "queueID", "status", "assignedResourceID")
    if any(field not in source_snapshot for field in required_fields):
        raise UntrustedTicketEvidence("SOURCE_SNAPSHOT_INCOMPLETE")

    current = _records(ticket_search_result, capability="service.ticket.search")
    if len(current) != 1:
        raise UntrustedTicketEvidence("EXACT_TICKET_READ_NOT_UNIQUE")
    exact = current[0]
    if str(exact.get("id")) != str(ticket_id):
        raise UntrustedTicketEvidence("TICKET_IDENTITY_CHANGED")
    for field in required_fields:
        if field not in exact or exact[field] != source_snapshot[field]:
            raise UntrustedTicketEvidence("TICKET_SCOPE_OR_STATE_CHANGED")

    notes = _records(notes_search_result, capability="service.ticket.notes.search")
    matches = [note for note in notes
               if str(note.get("title") or "") == MANAGED_NOTE_TITLE]
    if len(matches) != 1:
        raise UntrustedTicketEvidence("EXACT_MANAGED_NOTE_NOT_UNIQUE")
    body = str(matches[0].get("description") or "")
    if not expected_note_body or body != expected_note_body:
        raise UntrustedTicketEvidence("MANAGED_NOTE_READBACK_MISMATCH")

    # Facts are candidate identity/readback proof only. A separate signed
    # promotion and the modifying capability's approval/readback are required.
    return {
        "ticket_id": ticket_id,
        "unique_current_ticket": True,
        "company_identity_exact": True,
        "owned_by_jason": True,
        "current_queue": "Jason",
        "current_status": "New" if status == "new" else "In Progress",
        "source_snapshot_unchanged": True,
        "review_reason": reason,
        "internal_note_readback_verified": True,
        "internal_note_sha256": sha256(body.encode("utf-8")).hexdigest(),
    }
