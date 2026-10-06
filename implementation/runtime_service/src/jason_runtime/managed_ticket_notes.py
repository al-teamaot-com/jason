from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

GPT_INSIGHTS_TITLE = "GPT Insights"
JASON_ACTIVITY_TITLE = "Jason Activity"
JASON_ACTIVITY_MAX_BODY_CHARS = 7000


class ManagedTicketNoteError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ManagedNoteMutation:
    capability: str
    payload: Mapping[str, Any]


def _positive_note_id(value: Any) -> int:
    if isinstance(value, bool):
        raise ManagedTicketNoteError("managed note id is invalid")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ManagedTicketNoteError("managed note id is invalid") from error
    if parsed < 1:
        raise ManagedTicketNoteError("managed note id is invalid")
    return parsed


def exact_named_note(
    notes: Sequence[Mapping[str, Any]],
    *,
    title: str,
) -> Mapping[str, Any] | None:
    matches = [
        item
        for item in notes
        if isinstance(item, Mapping)
        and str(item.get("title") or "").strip().casefold() == title.strip().casefold()
    ]
    if len(matches) > 1:
        raise ManagedTicketNoteError(
            f"multiple managed notes exist for title: {title}"
        )
    return None if not matches else dict(matches[0])


def managed_note_mutation(
    *,
    ticket_id: int,
    title: str,
    body: str,
    notes: Sequence[Mapping[str, Any]],
) -> ManagedNoteMutation:
    existing = exact_named_note(notes, title=title)
    payload: dict[str, Any] = {
        "ticketID": int(ticket_id),
        "title": title,
        "description": body,
        "noteType": 3,
        "publish": 2,
    }
    if existing is None:
        return ManagedNoteMutation(
            capability="service.ticket.note.create",
            payload=payload,
        )
    payload["id"] = _positive_note_id(existing.get("id"))
    return ManagedNoteMutation(
        capability="service.ticket.note.update",
        payload=payload,
    )


def _activity_label(phase: str) -> str:
    normalized = str(phase or "").strip()
    if normalized.startswith("waiting_device_access:"):
        return "Device Check"
    if normalized.startswith("waiting_recheck:"):
        return "Recheck"
    if normalized == "waiting_patch_approval":
        return "Waiting Patch Approval"
    if normalized == "approval_pending":
        return "Waiting Approval"
    if normalized == "blocked":
        return "Blocked"
    if normalized == "escalated":
        return "Human Review"
    if normalized == "complete":
        return "Verified Complete"
    if normalized == "claim":
        return "Work Started"
    return normalized.replace("_", " ").replace(":", " - ").title() or "Activity"


def _display_timestamp(value: str) -> str:
    text = str(value or "").strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return text or "time unavailable"


def render_activity_entry(row: Mapping[str, Any]) -> str:
    phase = str(row.get("phase") or "").strip()
    reason = str(row.get("reason") or "").strip()
    stamp = _display_timestamp(str(row.get("occurred_at") or ""))
    lines = [
        f"{stamp} — {_activity_label(phase)}",
        f"Result: {reason or 'State changed; no additional result text was recorded.'}",
        f"Jason state: {phase or 'unknown'}",
    ]
    return "\n".join(lines)


def meaningful_activity_rows(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    result: list[Mapping[str, Any]] = []
    prior: tuple[str, str] | None = None
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        current = (
            str(row.get("phase") or "").strip(),
            str(row.get("reason") or "").strip(),
        )
        if current == prior:
            continue
        result.append(dict(row))
        prior = current
    return tuple(result)


def render_activity_chunks(
    rows: Sequence[Mapping[str, Any]],
    *,
    max_body_chars: int = JASON_ACTIVITY_MAX_BODY_CHARS,
) -> tuple[tuple[str, str], ...]:
    if max_body_chars < 1000:
        raise ValueError("activity note body limit is too small")
    entries = [render_activity_entry(row) for row in meaningful_activity_rows(rows)]
    if not entries:
        return ()

    chunks: list[str] = []
    current = ""
    for entry in entries:
        candidate = entry if not current else current + "\n\n" + entry
        if len(candidate) <= max_body_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(entry) > max_body_chars:
            raise ManagedTicketNoteError("single activity entry exceeds note body limit")
        current = entry
    if current:
        chunks.append(current)

    titled: list[tuple[str, str]] = []
    for index, body in enumerate(chunks, start=1):
        title = JASON_ACTIVITY_TITLE if index == 1 else f"{JASON_ACTIVITY_TITLE} {index}"
        titled.append((title, body))
    return tuple(titled)
