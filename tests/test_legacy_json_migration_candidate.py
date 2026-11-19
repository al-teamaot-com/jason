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
    assert step.arguments == {"ticket_id": 143305, "queue_id": 29682833, "status_id": 37}


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
