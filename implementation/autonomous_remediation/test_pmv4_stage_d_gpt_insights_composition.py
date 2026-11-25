"""Source-only GPT Insights composition proof; no provider calls or activation."""
import pytest

from .playbook_document import validate_playbook_document
from .playbook_runtime import JsonPlaybookInterpreter


def sample():
    return {
        "schema_version": 1,
        "playbook": {
            "id": "gpt_insights_stage_d_shadow",
            "name": "GPT Insights Stage D composition proof",
            "version": "0.0.1",
            "lifecycle": "pilot",
            "target_type": "ticket",
        },
        "trigger": {
            "queue_in": ["Help Desk I"],
            "status_in": ["New"],
            "excluded_ticket_source_labels": ["Recurring"],
            "pilot_only": True,
        },
        "scope": {"direct_provider_access": False},
        "expected_state": {"one_internal_note": True},
        "state_model": {"entry_step": "read_ticket"},
        "steps": [
            {"id": "read_ticket", "type": "diagnostic",
             "capability": "service.ticket.read",
             "arguments": {"ticket_id": {"$fact": "ticket_id"}},
             "next": "read_notes"},
            {"id": "read_notes", "type": "diagnostic",
             "capability": "service.ticket.notes.search",
             "arguments": {"ticket_id": {"$fact": "ticket_id"}},
             "next": "material_change"},
            {"id": "material_change", "type": "decision",
             "branches": [
                 {"when": {"fact": "material_change", "operator": "truthy"},
                  "next": "propose_internal_note"},
             ], "default": "complete"},
            {"id": "propose_internal_note", "type": "document",
             "capability": "service.ticket.note.create",
             "arguments": {"ticket_id": {"$fact": "ticket_id"},
                           "title": "GPT Insights",
                           "description": {"$fact": "insight_body"},
                           "noteType": 3, "publish": 2},
             "next": "verify_note"},
            {"id": "verify_note", "type": "verification",
             "capability": "service.ticket.notes.search",
             "arguments": {"ticket_id": {"$fact": "ticket_id"}},
             "next": "complete"},
            {"id": "complete", "type": "complete"},
        ],
        "verification": {
            "authoritative_source": "service.ticket.notes.search",
            "success_condition": "one exact Jason-owned internal note",
        },
        "completion": {"terminal_disposition": "shadow-only evidence"},
        "autonomy": {
            "activation": "shadow",
            "allowed_capabilities": [
                "service.ticket.read", "service.ticket.notes.search",
                "service.ticket.note.create",
            ],
        },
    }


def test_gpt_insights_shadow_composes_existing_capabilities_without_execution():
    document = validate_playbook_document(
        sample(), known_capabilities={
            "service.ticket.read", "service.ticket.notes.search",
            "service.ticket.note.create",
        },
    )
    runtime = JsonPlaybookInterpreter(document)
    facts = {"ticket_id": 123, "material_change": True,
             "insight_body": "Evidence-backed internal advisory"}
    read = runtime.instruction(facts=facts)
    assert read.capability == "service.ticket.read"
    assert read.arguments == {"ticket_id": 123}
    assert runtime.next_step(read.step_id) == "read_notes"
    assert runtime.next_step("material_change", facts=facts) == "propose_internal_note"
    note = runtime.instruction(step_id="propose_internal_note", facts=facts)
    assert note.capability == "service.ticket.note.create"
    assert note.arguments["description"] == "Evidence-backed internal advisory"
    assert note.arguments["publish"] == 2
    assert runtime.instruction(step_id="verify_note", facts=facts).capability == (
        "service.ticket.notes.search"
    )


def test_unchanged_evidence_skips_mutation_instruction():
    runtime = JsonPlaybookInterpreter(validate_playbook_document(sample()))
    assert runtime.next_step("material_change", facts={"material_change": False}) == "complete"


def test_missing_trusted_ticket_identity_denies_binding():
    runtime = JsonPlaybookInterpreter(validate_playbook_document(sample()))
    with pytest.raises(KeyError, match="PLAYBOOK_REQUIRED_FACT_MISSING"):
        runtime.instruction(facts={})


def test_shadow_never_grants_execution_authority():
    document = validate_playbook_document(sample())
    assert document.autonomy_activation == "shadow"
    assert document.payload["scope"]["direct_provider_access"] is False
