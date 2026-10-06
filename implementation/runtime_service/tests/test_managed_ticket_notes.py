from __future__ import annotations

import pytest

from jason_runtime.managed_ticket_notes import (
    ManagedTicketNoteError,
    exact_named_note,
    managed_note_mutation,
    meaningful_activity_rows,
    render_activity_chunks,
)


def test_managed_note_create_then_update_shape():
    create = managed_note_mutation(
        ticket_id=123,
        title="GPT Insights",
        body="first",
        notes=[],
    )
    assert create.capability == "service.ticket.note.create"
    assert "id" not in create.payload

    update = managed_note_mutation(
        ticket_id=123,
        title="GPT Insights",
        body="second",
        notes=[{"id": 456, "title": "GPT Insights", "description": "first"}],
    )
    assert update.capability == "service.ticket.note.update"
    assert update.payload["id"] == 456
    assert update.payload["noteType"] == 3
    assert update.payload["publish"] == 2


def test_duplicate_managed_title_fails_closed():
    with pytest.raises(ManagedTicketNoteError, match="multiple managed notes"):
        exact_named_note(
            [
                {"id": 1, "title": "Jason Activity"},
                {"id": 2, "title": "Jason Activity"},
            ],
            title="Jason Activity",
        )


def test_activity_suppresses_unchanged_consecutive_polling():
    rows = [
        {"phase": "waiting_device_access:claim", "reason": "offline", "occurred_at": "2026-10-06T10:00:00+00:00"},
        {"phase": "waiting_device_access:claim", "reason": "offline", "occurred_at": "2026-10-06T11:00:00+00:00"},
        {"phase": "claim", "reason": "online again", "occurred_at": "2026-10-06T12:00:00+00:00"},
    ]
    assert len(meaningful_activity_rows(rows)) == 2
    chunks = render_activity_chunks(rows)
    assert len(chunks) == 1
    title, body = chunks[0]
    assert title == "Jason Activity"
    assert body.count("offline") == 1
    assert "online again" in body


def test_activity_rollover_is_deterministic_and_preserves_first_chunk():
    rows = [
        {
            "phase": f"phase_{index}",
            "reason": "x" * 180,
            "occurred_at": f"2026-10-06T{index:02d}:00:00+00:00",
        }
        for index in range(1, 12)
    ]
    first = render_activity_chunks(rows[:8], max_body_chars=1000)
    later = render_activity_chunks(rows, max_body_chars=1000)
    assert len(later) > 1
    assert later[0] == first[0]
    assert later[1][0] == "Jason Activity 2"
