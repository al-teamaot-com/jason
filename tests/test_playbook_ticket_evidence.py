"""Reusable exact ticket guard: synthetic existing governed-read envelopes only."""
from copy import deepcopy

import pytest

from implementation.autonomous_remediation.playbook_ticket_evidence import (
    UntrustedTicketEvidence, handoff_identity_facts,
)
from implementation.autonomous_remediation.playbook_document import validate_playbook_document
from implementation.autonomous_remediation.playbook_runtime import JsonPlaybookInterpreter
from implementation.runtime_service.tests.test_unsupported_ticket_triage import (
    NoteReadStub, ticket,
)

ALLOWED = frozenset({200001, 200002})
BODY = "JASON READ-ONLY INVESTIGATION - source-matched synthetic evidence"


def context(*, source_status="New", reason="needs_human_review",
            owned_by_jason=True, source_queue="Jason"):
    source = ticket(queue=source_queue, status=source_status)
    reads = NoteReadStub()
    reads.notes.append({
        "id": 9001, "title": "Jason - Governed Read-Only Investigation",
        "description": BODY,
    })
    return source, reads, {
        "source_snapshot": source.context,
        "source_queue": source_queue,
        "owned_by_jason": owned_by_jason,
        "source_status_label": source_status,
        "review_reason": reason,
        "ticket_search_result": {
            "status": "succeeded",
            "evidence": {"data": {"items": [dict(reads.current_ticket)]}},
        },
        "notes_search_result": {
            "status": "succeeded",
            "evidence": {"data": {"items": list(reads.notes)}},
        },
        "expected_note_body": BODY,
        "permitted_ticket_ids": ALLOWED,
    }


def test_exact_handoff_guard_produces_evidence_but_not_approval():
    source, reads, kwargs = context()
    facts = handoff_identity_facts(**kwargs)
    assert facts["ticket_id"] == 200001
    assert facts["unique_current_ticket"] is True
    assert facts["internal_note_readback_verified"] is True
    assert len(facts["internal_note_sha256"]) == 64
    assert "exact_handoff_promotion_verified" not in facts
    assert "exact_handoff_readback_verified" not in facts
    assert "service.ticket.update" not in str(facts)


@pytest.mark.parametrize("field,value", [
    ("companyID", 999),
    ("queueID", 29682833),
    ("status", 7),
    ("assignedResourceID", 12),
])
def test_exact_handoff_guard_blocks_changed_ticket(field, value):
    _, _, kwargs = context()
    kwargs["ticket_search_result"]["evidence"]["data"]["items"][0][field] = value
    with pytest.raises(UntrustedTicketEvidence, match="SCOPE_OR_STATE_CHANGED"):
        handoff_identity_facts(**kwargs)


@pytest.mark.parametrize("status", ["Waiting Customer", "Waiting Device Access", "On Hold", "Complete", ""])
def test_exact_handoff_guard_blocks_waiting_or_unknown_source(status):
    _, _, kwargs = context(source_status=status)
    with pytest.raises(UntrustedTicketEvidence, match="SOURCE_STATUS_NOT_ELIGIBLE"):
        handoff_identity_facts(**kwargs)


@pytest.mark.parametrize("reason", ["healthy", "resolved", "needs_playbook_promotion"])
def test_exact_handoff_guard_blocks_nonhandoff_reason(reason):
    _, _, kwargs = context(reason=reason)
    with pytest.raises(UntrustedTicketEvidence, match="HANDOFF_STATE_NOT_ELIGIBLE"):
        handoff_identity_facts(**kwargs)


def test_exact_handoff_guard_blocks_human_owned_ticket():
    _, _, kwargs = context(owned_by_jason=False)
    with pytest.raises(UntrustedTicketEvidence, match="NOT_JASON_OWNED"):
        handoff_identity_facts(**kwargs)


@pytest.mark.parametrize("case", ["duplicate_ticket", "missing_ticket", "wrong_id",
                                    "duplicate_note", "edited_note", "failed_notes_read",
                                    "failed_ticket_read", "incomplete_source"])
def test_exact_handoff_guard_blocks_evidence_failure(case):
    _, _, kwargs = context()
    kwargs = deepcopy(kwargs)
    records = kwargs["ticket_search_result"]["evidence"]["data"]["items"]
    notes = kwargs["notes_search_result"]["evidence"]["data"]["items"]
    if case == "duplicate_ticket":
        records.append(dict(records[0]))
    elif case == "missing_ticket":
        records.clear()
    elif case == "wrong_id":
        records[0]["id"] = 50
    elif case == "duplicate_note":
        notes.append(dict(notes[-1]))
    elif case == "edited_note":
        notes[-1]["description"] = "Human note edited"
    elif case == "failed_notes_read":
        kwargs["notes_search_result"]["status"] = "denied"
    elif case == "failed_ticket_read":
        kwargs["ticket_search_result"]["status"] = "denied"
    else:
        del kwargs["source_snapshot"]["companyID"]
    with pytest.raises(UntrustedTicketEvidence):
        handoff_identity_facts(**kwargs)


def test_exact_handoff_guard_blocks_out_of_scope_pilot():
    _, _, kwargs = context()
    kwargs["permitted_ticket_ids"] = frozenset({143305, 143272})
    with pytest.raises(UntrustedTicketEvidence, match="NOT_IN_EXACT_PILOT"):
        handoff_identity_facts(**kwargs)


def test_ticket_guard_facts_enter_existing_json_interpreter_without_granting_write():
    import json
    from pathlib import Path
    _, _, kwargs = context()
    facts = dict(handoff_identity_facts(**kwargs))
    path = (Path(__file__).resolve().parents[1] /
            "docs/playbooks/json/migration/candidates/unsupported_triage_human_review.v1.json")
    doc = json.loads(path.read_text())
    doc["trigger"]["exact_ticket_ids"] = [200001, 200002]
    for step in doc["steps"]:
        if step["id"] == "pilot_gate":
            step["branches"][0]["when"]["value"] = [200001, 200002]
    runtime = JsonPlaybookInterpreter(validate_playbook_document(doc))
    instruction = runtime.instruction(step_id="pilot_gate", facts=facts)
    assert instruction.step_id == "blocked"
    assert instruction.capability is None
    assert "exact_handoff_promotion_verified" not in facts
    assert "exact_handoff_readback_verified" not in facts
