"""Controlled legacy worker vs JSON *intent* comparison on identical fake tickets.

No real provider calls. This covers only two safe branches and is not a
full legacy-vs-JSON operational acceptance.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from autonomous_remediation.playbook_document import validate_playbook_document
from autonomous_remediation.playbook_runtime import JsonPlaybookInterpreter
from implementation.runtime_service.tests.test_unsupported_ticket_triage import (
    NoteActionStub, NoteReadStub, PromotionForTriage, make_worker, ticket,
)

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "docs/playbooks/json/migration/candidates"


def fixture_interpreter(filename):
    # Legacy existing fixture is ticket 200001. Override only the allowlist
    # in-memory to use identical synthetic inputs in both branches; never
    # modify versioned production-scope candidate files.
    payload = json.loads((CANDIDATES / filename).read_text())
    payload["trigger"]["exact_ticket_ids"] = [200001, 200002]
    for step in payload["steps"]:
        if step["id"] == "pilot_gate":
            step["branches"][0]["when"]["value"] = [200001, 200002]
    return JsonPlaybookInterpreter(validate_playbook_document(payload))


@pytest.mark.parametrize("approval,status,expected", [
    (True, "New", True),
    (False, "New", False),
    (True, "Waiting Customer", False),
])
def test_legacy_handoff_and_json_same_fixture_intent(tmp_path, approval, status, expected):
    candidate = ticket(queue="Jason", status=status)
    reads = NoteReadStub()
    body = "JASON READ-ONLY INVESTIGATION - previously independently verified"
    reads.notes.append({
        "id": 9001, "title": "Jason - Governed Read-Only Investigation",
        "description": body,
    })
    worker, store, _ = make_worker(tmp_path, [candidate], reads)
    worker.promotion_store = PromotionForTriage(handoff=approval)
    actions = NoteActionStub(reads)
    worker.actions = actions
    try:
        worker._maybe_handoff_unsupported_ticket(
            candidate, state="needs_human_review", body=body,
            note_fingerprint=hashlib.sha256(body.encode()).hexdigest(),
            now=datetime.now(timezone.utc),
        )
        legacy = [arguments for _, cap, arguments in actions.calls
                  if cap == "service.ticket.update"]
        fact = {
            "ticket_id": 200001, "unique_current_ticket": True,
            "company_identity_exact": True, "owned_by_jason": True,
            "current_queue": "Jason", "current_status": status,
            "source_snapshot_unchanged": True, "review_reason": "needs_human_review",
            "internal_note_readback_verified": True,
            "exact_handoff_promotion_verified": approval,
        }
        inst = fixture_interpreter("unsupported_triage_human_review.v1.json").instruction(
            step_id="pilot_gate", facts=fact,
        )
        assert (inst.step_id == "handoff_update") is expected
        assert bool(legacy) is expected
        if expected:
            assert inst.arguments["payload"] == legacy[0]
            assert store.unsupported_handoff_delivery(200001)["state"] == "verified"
        else:
            assert inst.step_id == "blocked"
    finally:
        store.close()


def test_legacy_internal_note_and_json_same_fixture_write_payload(tmp_path):
    from jason_runtime.unsupported_ticket_triage import render_triage_note
    candidate = ticket(title="Space Issue", queue="Jason")
    reads = NoteReadStub()
    worker, store, _ = make_worker(tmp_path, [candidate], reads)
    worker.promotion_store = PromotionForTriage()
    actions = NoteActionStub(reads)
    worker.actions = actions
    evidence = {"company_verified": True, "ticket_id": 200001}
    body = render_triage_note(
        ticket_number=candidate.context["ticketNumber"], state="needs_human_review",
        category="general", evidence=evidence,
        next_step="Technician must inspect the failed provider evidence path.",
    )
    evidence["note_draft"] = body
    record = {"state": "needs_human_review", "evidence": evidence,
              "source_version": candidate.source_version,
              "ticket_number": candidate.context["ticketNumber"]}
    try:
        worker._maybe_publish_unsupported_triage_note(
            candidate, record, now=datetime.now(timezone.utc))
        legacy_notes = [args for _, cap, args in actions.calls
                        if cap == "service.ticket.note.create"]
        assert len(legacy_notes) == 1
        inst = fixture_interpreter("unsupported_readonly_triage_note.v1.json").instruction(
            step_id="pilot_gate",
            facts={
                "ticket_id": 200001, "source_version_current": True,
                "company_identity_verified": True, "assigned_elsewhere": False,
                "valid_nontransient_note_draft": True,
                "exact_note_promotion_verified": True,
                "note_fingerprint_already_verified": False,
                "existing_managed_note": False, "note_body": body,
            },
        )
        assert inst.step_id == "note_create"
        assert inst.arguments["payload"] == legacy_notes[0]
        assert store.last_note_fingerprint(
            200001, "unsupported_readonly_triage_note",
            "Jason - Governed Read-Only Investigation")
    finally:
        store.close()
