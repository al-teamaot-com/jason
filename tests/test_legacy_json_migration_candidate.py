"""Source-only synthetic acceptance for exact pilot handoff JSON candidate.

No provider calls, no production activation, no authority grant.
"""
import copy
import json
from pathlib import Path

import jsonschema
import pytest

from implementation.autonomous_remediation.playbook_document import (
    PlaybookValidationError, validate_playbook_document,
)
from implementation.autonomous_remediation.playbook_runtime import JsonPlaybookInterpreter
from implementation.autonomous_remediation.playbook_store import SQLitePlaybookRegistry

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "docs/playbooks/json/migration/candidates/unsupported_triage_human_review.v1.json"
SCHEMA = ROOT / "docs/playbooks/json/playbook-v1.schema.json"
GOOD = {
    "ticket_id": 143305, "unique_current_ticket": True,
    "company_identity_exact": True, "owned_by_jason": True,
    "current_queue": "Jason", "current_status": "In Progress",
    "source_snapshot_unchanged": True, "review_reason": "needs_human_review",
    "internal_note_readback_verified": True,
    "exact_handoff_promotion_verified": True,
    "exact_handoff_readback_verified": True,
}


def payload():
    return json.loads(CANDIDATE.read_text())


def interpreter():
    return JsonPlaybookInterpreter(validate_playbook_document(payload()))


def advance_gate(facts):
    engine = interpreter()
    step = engine.instruction(step_id="pilot_gate", facts=facts)
    return step


def test_schema_and_project_semantics():
    doc = payload()
    jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text())).validate(doc)
    validated = validate_playbook_document(doc)
    assert validated.autonomy_activation == "shadow"
    assert len(validated.fingerprint) == 64
    assert doc["scope"]["direct_provider_access"] is False


def test_proven_gate_chain_proposes_only_exact_approved_update():
    step = advance_gate(GOOD)
    assert step.step_id == "handoff_update"
    assert step.step_type == "remediation"
    assert step.approval_required is True
    assert step.approval_classification == "modifying"
    assert step.capability == "service.ticket.update"
    assert step.arguments == {"payload": {"id": 143305, "queueID": "Help Desk I", "status": "Human Review"}}


@pytest.mark.parametrize("fact,bad", [
    ("ticket_id", 143073),
    ("unique_current_ticket", False),
    ("company_identity_exact", False),
    ("owned_by_jason", False),
    ("current_queue", "Help Desk I"),
    ("current_status", "Waiting Customer"),
    ("current_status", "Waiting Device Access"),
    ("current_status", "On Hold"),
    ("current_status", "Complete"),
    ("current_status", "Unknown"),
    ("source_snapshot_unchanged", False),
    ("review_reason", "healthy"),
    ("internal_note_readback_verified", False),
    ("exact_handoff_promotion_verified", False),
])
def test_negative_gate_blocks(fact, bad):
    facts = dict(GOOD, **{fact: bad})
    instruction = advance_gate(facts)
    assert instruction.step_id == "blocked"
    assert instruction.step_type == "human_review"


@pytest.mark.parametrize("fact", list(GOOD))
def test_missing_fact_fails_closed_at_gate(fact):
    facts = dict(GOOD)
    facts.pop(fact)
    if fact == "exact_handoff_readback_verified":
        step = interpreter().instruction(step_id="readback_gate", facts=facts)
    else:
        step = advance_gate(facts)
    assert step.step_id == "blocked"


def test_successful_readback_and_missing_readback():
    engine = interpreter()
    assert engine.instruction(step_id="readback_gate", facts=GOOD).step_id == "handoff_complete"
    assert engine.instruction(step_id="readback_gate", facts=dict(GOOD, exact_handoff_readback_verified=False)).step_id == "blocked"


def test_missing_bound_ticket_does_not_execute():
    with pytest.raises(KeyError, match="PLAYBOOK_REQUIRED_FACT_MISSING"):
        interpreter().instruction(step_id="handoff_update", facts={})


def test_forbidden_inline_code_and_disruptive_without_approval_rejected():
    doc = payload()
    doc["steps"][0]["shell"] = "whoami"
    with pytest.raises(PlaybookValidationError):
        validate_playbook_document(doc)
    doc = payload()
    step = next(x for x in doc["steps"] if x["id"] == "handoff_update")
    step["approval_classification"] = "disruptive"
    step["approval_required"] = False
    with pytest.raises(PlaybookValidationError):
        validate_playbook_document(doc)


def test_synthetic_registry_stage_restart_without_activation(tmp_path):
    store_path = tmp_path / "isolated.sqlite3"
    store = SQLitePlaybookRegistry(store_path)
    stored = store.stage(payload(), actor="migration-test")
    assert stored.state == "draft"
    assert store.active("unsupported_triage_human_review") is None
    assert store.generation() == 1
    store.close()
    store = SQLitePlaybookRegistry(store_path)
    try:
        assert store.generation() == 1
        assert store.active("unsupported_triage_human_review") is None
        assert store.get("unsupported_triage_human_review", "1.0.0-migration.1").state == "draft"
    finally:
        store.close()

@pytest.mark.parametrize("operator,value", [
    ("ne", "approved"), ("not_in", ["approved"]), ("falsy", None),
])
def test_absent_fact_never_satisfies_negative_decision(operator, value):
    """An absent grant/fact cannot be treated as a negative evidence match."""
    decision = {"branches": [{"when": {"fact": "approval", "operator": operator,
                                       "value": value}, "next": "handoff_update"}],
                "default": "blocked"}
    assert JsonPlaybookInterpreter._decision_target(decision, {}) == "blocked"
    assert JsonPlaybookInterpreter._decision_target(decision, {"approval": False}) == "handoff_update"

READONLY_NOTE = ROOT / "docs/playbooks/json/migration/candidates/unsupported_readonly_triage_note.v1.json"
NOTE_GOOD = {
    "ticket_id": 143305,
    "source_version_current": True,
    "company_identity_verified": True,
    "assigned_elsewhere": False,
    "valid_nontransient_note_draft": True,
    "exact_note_promotion_verified": True,
    "note_fingerprint_already_verified": False,
    "existing_managed_note": False,
    "note_body": "JASON READ-ONLY INVESTIGATION - exact verified finding",
}


def note_engine():
    return JsonPlaybookInterpreter(validate_playbook_document(json.loads(READONLY_NOTE.read_text())))


def test_readonly_first_candidate_schema_and_no_provider_execution():
    doc = json.loads(READONLY_NOTE.read_text())
    jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text())).validate(doc)
    assert doc["autonomy"]["activation"] == "shadow"
    assert doc["scope"]["direct_provider_access"] is False
    assert doc["migration"]["production_activation_authorized"] is False


def test_readonly_note_create_is_exact_approval_bound_proposal_only():
    instruction = note_engine().instruction(step_id="pilot_gate", facts=NOTE_GOOD)
    assert instruction.step_id == "note_create"
    assert instruction.capability == "service.ticket.note.create"
    assert instruction.approval_required is True
    assert instruction.arguments["payload"] == {
        "ticketID": 143305,
        "title": "Jason - Governed Read-Only Investigation",
        "description": NOTE_GOOD["note_body"], "noteType": 3, "publish": 2,
    }


@pytest.mark.parametrize("change", [
    {"ticket_id": 143073},
    {"source_version_current": False},
    {"company_identity_verified": False},
    {"assigned_elsewhere": True},
    {"valid_nontransient_note_draft": False},
    {"exact_note_promotion_verified": False},
    {"existing_managed_note": True,
     "existing_note_content_matches_last_owned_fingerprint": False},
])
def test_readonly_note_rejects_unapproved_or_unowned_writes(change):
    facts = dict(NOTE_GOOD)
    facts.update(change)
    step = note_engine().instruction(step_id="pilot_gate", facts=facts)
    assert step.step_id == "blocked"


def test_readonly_note_suppresses_duplicate_and_proposes_safe_update():
    once = note_engine().instruction(
        step_id="pilot_gate", facts=dict(NOTE_GOOD, note_fingerprint_already_verified=True))
    assert once.step_id == "documented"
    update = note_engine().instruction(step_id="pilot_gate", facts=dict(
        NOTE_GOOD, existing_managed_note=True,
        existing_note_content_matches_last_owned_fingerprint=True,
        managed_note_id=9001))
    assert update.step_id == "note_update"
    assert update.approval_required is True
    assert update.arguments["payload"]["id"] == 9001


def test_readonly_note_readback_requires_exact_body_evidence():
    engine = note_engine()
    assert engine.instruction(step_id="note_readback_gate", facts={
        "exact_note_body_readback_verified": True}).step_id == "documented"
    assert engine.instruction(step_id="note_readback_gate", facts={
        "exact_note_body_readback_verified": False}).step_id == "blocked"


@pytest.mark.parametrize("op", ["in", "not_in"])
def test_membership_predicates_reject_non_array_to_prevent_string_substring_match(op):
    doc = payload()
    gate = next(step for step in doc["steps"] if step["id"] == "pilot_gate")
    gate["branches"][0]["when"] = {"fact": "ticket_id", "operator": op,
                                      "value": "143305"}
    with pytest.raises(PlaybookValidationError, match="BRANCH_MEMBERSHIP_ARRAY_REQUIRED"):
        validate_playbook_document(doc)


def test_both_candidates_stage_into_isolated_registry_without_activation(tmp_path):
    store_path = tmp_path / "migration-isolated-registry.sqlite3"
    store = SQLitePlaybookRegistry(store_path)
    try:
        docs = [payload(), json.loads(READONLY_NOTE.read_text())]
        for entry in docs:
            staged = store.stage(entry, actor="migration-isolated-test")
            assert staged.state == "draft"
        assert store.generation() == 2
        assert store.active_snapshot()[1] == ()
        assert len(store.lifecycle_events()) == 2
    finally:
        store.close()
    reopened = SQLitePlaybookRegistry(store_path)
    try:
        assert reopened.generation() == 2
        assert reopened.active_snapshot()[1] == ()
        assert len(reopened.list_all()) == 2
    finally:
        reopened.close()
