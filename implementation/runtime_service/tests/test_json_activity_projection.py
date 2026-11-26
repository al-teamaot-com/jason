"""Actual legacy Activity pure rendering versus guarded JSON source plan."""
from datetime import datetime, timezone
from hashlib import sha256

import pytest

from jason_runtime.json_activity_projection import (
    JsonActivityProjectionBoundaryError, plan_activity_projection,
)
from jason_runtime.managed_ticket_notes import (
    render_activity_chunks, managed_note_mutation,
)

TICKET = {"id": 123, "companyID": 777}
NOTE = {"ticketID": 123, "creatorResourceID": 950,
        "noteType": 3, "publish": 2}
ROWS = [
    {"phase": "claim", "reason": "started",
     "occurred_at": "2026-11-19T16:00:00+00:00"},
    {"phase": "claim", "reason": "started",
     "occurred_at": "2026-11-19T16:01:00+00:00"},
    {"phase": "waiting_device_access:diagnose", "reason": "offline",
     "occurred_at": "2026-11-19T16:02:00+00:00"},
]


def plan(rows=ROWS, notes=(), **kwargs):
    arguments = {
        "ticket_id": 123, "client_id": "777",
        "exact_current_ticket": TICKET,
        "local_ticket_id": 123, "local_activity_rows": rows,
        "governed_note_search": {
            "status": "succeeded", "evidence": {"data": {"items": list(notes)}}
        },
        "jason_creator_resource_id": 950,
    }
    arguments.update(kwargs)
    return plan_activity_projection(**arguments)


def test_source_rows_suppress_consecutive_noise_and_create_exact_internal_note():
    expected = render_activity_chunks(ROWS)
    intents = plan()
    assert len(intents) == len(expected) == 1
    assert intents[0].disposition == "create"
    mutation = managed_note_mutation(
        ticket_id=123, title=expected[0][0],
        body=expected[0][1], notes=(),
    )
    assert intents[0].capability == mutation.capability
    assert intents[0].arguments == {"payload": dict(mutation.payload)}
    assert intents[0].source_rows == 3
    assert intents[0].revised_sha256 == sha256(expected[0][1].encode()).hexdigest()


def test_exact_current_note_suppresses_duplicate_mutation():
    title, body = render_activity_chunks(ROWS)[0]
    current = {**NOTE, "id": 40, "title": title, "description": body}
    result = plan(notes=[current])
    assert len(result) == 1
    assert result[0].disposition == "current"
    assert result[0].capability is None
    assert result[0].arguments is None


def test_new_state_appends_without_overwriting_prior():
    first = render_activity_chunks(ROWS[:2])[0]
    current = {**NOTE, "id": 40,
               "title": first[0], "description": first[1]}
    output = plan(notes=[current])
    assert output[0].disposition == "update"
    assert output[0].arguments["payload"]["id"] == 40
    assert output[0].arguments["payload"]["description"].startswith(first[1])
    assert output[0].prior_sha256 == sha256(first[1].encode()).hexdigest()


def test_rollover_preserves_first_note_body_and_creates_second():
    rows = [
        {"phase": f"phase_{i}", "reason": "x" * 180,
         "occurred_at": f"2026-11-19T{i:02d}:00:00+00:00"}
        for i in range(1, 12)
    ]
    chunks = render_activity_chunks(rows, max_body_chars=1000)
    assert len(chunks) > 1
    old = {**NOTE, "id": 77,
           "title": chunks[0][0], "description": chunks[0][1]}
    output = plan(rows=rows, notes=[old], max_body_chars=1000)
    assert output[0].disposition == "current"
    assert output[1].title == "Jason Activity 2"
    assert output[1].disposition == "create"


@pytest.mark.parametrize("changes", [
    {"creatorResourceID": 999},
    {"noteType": 1},
    {"publish": 1},
    {"ticketID": 999},
])
def test_non_jason_or_external_note_cannot_be_updated(changes):
    title, body = render_activity_chunks(ROWS[:2])[0]
    note = {**NOTE, "id": 50,
            "title": title, "description": body, **changes}
    with pytest.raises(JsonActivityProjectionBoundaryError,
                       match="NOT_JASON_OWNED_INTERNAL"):
        plan(notes=[note])


def test_duplicate_managed_notes_are_ambiguous_and_blocked():
    title, body = render_activity_chunks(ROWS)[0]
    note = {**NOTE, "id": 50, "title": title, "description": body}
    with pytest.raises(JsonActivityProjectionBoundaryError,
                       match="DUPLICATE_MANAGED_TITLE"):
        plan(notes=[note, {**note, "id": 51}])


def test_prior_historical_note_cannot_be_rewritten():
    title, body = render_activity_chunks(ROWS)[0]
    note = {**NOTE, "id": 50, "title": title, "description": "older other text"}
    with pytest.raises(JsonActivityProjectionBoundaryError,
                       match="NON_APPEND_UPDATE_FORBIDDEN"):
        plan(notes=[note])


@pytest.mark.parametrize("scope", [
    {"client_id": "wrong"},
    {"local_ticket_id": 456},
    {"exact_current_ticket": {"id": 123, "companyID": "different"}},
    {"jason_creator_resource_id": 0},
])
def test_stale_identity_or_local_state_cannot_create(scope):
    with pytest.raises(JsonActivityProjectionBoundaryError,
                       match="EXACT_TICKET_SCOPE_MISSING"):
        plan(**scope)


def test_incomplete_governed_note_list_denies_writes():
    with pytest.raises(JsonActivityProjectionBoundaryError):
        plan_activity_projection(
            ticket_id=123, client_id="777", exact_current_ticket=TICKET,
            local_ticket_id=123, local_activity_rows=ROWS,
            governed_note_search={
                "status": "succeeded",
                "evidence": {"data": {"items": [], "has_more": True}},
            },
            jason_creator_resource_id=950,
        )


def test_canonical_json_activity_branch_does_not_execute_mutation():
    import json
    from pathlib import Path
    from autonomous_remediation.playbook_document import validate_playbook_document
    from autonomous_remediation.playbook_runtime import JsonPlaybookInterpreter
    path = (Path(__file__).resolve().parents[3] /
            "docs/playbooks/json/migration/candidates/jason_activity_log.v1.json")
    doc = validate_playbook_document(json.loads(path.read_text()))
    runner = JsonPlaybookInterpreter(doc)
    assert runner.instruction(step_id="ticket_gate", facts={}).step_id == "human_review"
    assert runner.instruction(step_id="projection_gate", facts={}).step_id == "human_review"
    for disposition, verified_fact, step in [
        ("create", "exact_owner_promotion_and_intent_bound", "create_note"),
        ("update", "exact_jason_internal_note_owned_and_promotion_bound", "update_note"),
    ]:
        refused = runner.instruction(
            step_id="projection_gate",
            facts={"verified_projection_disposition": disposition},
        )
        assert refused.step_id == "human_review"
        instruction = runner.instruction(
            step_id="projection_gate",
            facts={
                "verified_projection_disposition": disposition,
                verified_fact: True,
                "verified_exact_note_mutation_arguments": {
                    "payload": {"ticketID": 123, "title": "Jason Activity",
                                "description": "source-only"}},
            },
        )
        assert instruction.step_id == step
        assert instruction.approval_required
        assert instruction.approval_classification == "modifying"
        assert instruction.arguments["payload"]["ticketID"] == 123
    assert runner.instruction(
        step_id="projection_gate",
        facts={"verified_projection_disposition": "current"},
    ).step_id == "already_current"
    assert runner.instruction(step_id="readback_gate", facts={}).step_id == "human_review"
