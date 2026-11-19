"""Existing deployed GPT Insights pure classifier and note planner parity."""
from hashlib import sha256

import pytest

from jason_runtime.gpt_insights import (
    InsightEvidence, classify_ticket, material_fingerprint, render_insight,
)
from jason_runtime.json_gpt_insights_projection import (
    JsonGptInsightsBoundaryError, plan_gpt_insights,
)

TICKET = {"id": 321, "companyID": 777,
          "ticketNumber": "T-SYNTHETIC", "title": "Network wifi disconnected",
          "description": "Internet unreliable"}
EVIDENCE = InsightEvidence(
    category="network", ticket_number="T-SYNTHETIC",
    ticket_title=TICKET["title"], device_name=None,
    unresolved_reason="No exact CI association")
NOTE = {"id": 55, "ticketID": 321, "creatorResourceID": 950,
        "title": "GPT Insights", "noteType": 3, "publish": 2,
        "description": "Prior advisory note"}


def plan(*, ticket=TICKET, evidence=EVIDENCE, notes=(), prior=None, **kwargs):
    options = {
        "ticket": ticket, "ticket_id": 321, "client_id": "777",
        "source_queue": "Help Desk I", "source_status": "New",
        "source_label": "Phone", "device_identity_verified": False,
        "evidence": evidence,
        "notes_response": {"status": "succeeded",
                           "evidence": {"data": {"items": list(notes)}}},
        "prior_fingerprint": prior, "jason_creator_id": 950,
    }
    options.update(kwargs)
    return plan_gpt_insights(**options)


def test_classifier_note_text_fingerprint_and_first_internal_note_match_legacy():
    result = plan()
    assert result.disposition == "create"
    assert result.category == classify_ticket(TICKET["title"], TICKET["description"])
    assert result.fingerprint == material_fingerprint(EVIDENCE)
    assert result.body == render_insight(EVIDENCE)
    assert result.arguments["payload"]["description"] == result.body
    assert result.arguments["payload"]["noteType"] == 3
    assert result.arguments["payload"]["publish"] == 2
    assert result.revised_sha256 == sha256(result.body.encode()).hexdigest()


@pytest.mark.parametrize("category,title", [
    ("network", "WiFi stopped"),
    ("printing", "Printer not printing"),
    ("performance", "Computer running slow"),
    ("login", "User cannot sign in"),
    ("application", "Program crash at launch"),
    ("unknown", "Help requested with item"),
])
def test_same_deployed_classifier_for_eligible_synthetic_tickets(category, title):
    source = {**TICKET, "title": title, "description": ""}
    evidence = InsightEvidence(
        category=classify_ticket(title, ""),
        ticket_number="T-SYNTHETIC", ticket_title=title)
    assert plan(ticket=source, evidence=evidence).category == category


@pytest.mark.parametrize("scope", [
    {"source_queue": "Help Desk II"},
    {"source_status": "In Progress"},
    {"source_label": "Recurring"},
])
def test_ineligible_ticket_never_proposes_provider_action(scope):
    result = plan(**scope)
    assert result.disposition == "ineligible"
    assert result.capability is None


def test_existing_note_without_local_fingerprint_seeds_no_duplicate():
    result = plan(notes=[NOTE], prior=None)
    assert result.disposition == "seed_existing"
    assert result.capability is None


def test_exact_unchanged_fingerprint_never_rewrites_note():
    result = plan(notes=[NOTE], prior=material_fingerprint(EVIDENCE))
    assert result.disposition == "current"
    assert result.capability is None


def test_changed_evidence_updates_only_current_jason_internal_note():
    earlier = InsightEvidence(
        category="network", ticket_number="T-SYNTHETIC",
        ticket_title=TICKET["title"], device_name=None,
        unresolved_reason="Old evidence")
    result = plan(notes=[NOTE], prior=material_fingerprint(earlier))
    assert result.disposition == "update"
    assert result.capability == "service.ticket.note.update"
    assert result.arguments["payload"]["id"] == 55
    assert result.arguments["payload"]["ticketID"] == 321
    assert result.previous_sha256 == sha256(NOTE["description"].encode()).hexdigest()


@pytest.mark.parametrize("changed", [
    {"creatorResourceID": 56},
    {"ticketID": 322},
    {"publish": 1},
    {"noteType": 1},
])
def test_non_jason_internal_note_cannot_be_updated(changed):
    with pytest.raises(JsonGptInsightsBoundaryError,
                       match="BASE_NOTE_NOT_JASON_INTERNAL"):
        plan(notes=[{**NOTE, **changed}], prior="older-fingerprint")


def test_duplicate_current_note_is_not_permission_to_overwrite():
    with pytest.raises(JsonGptInsightsBoundaryError,
                       match="DUPLICATE_BASE_NOTE"):
        plan(notes=[NOTE, {**NOTE, "id": 56}], prior="older-fingerprint")


def test_missing_provider_note_when_local_cache_claims_current_is_uncertain():
    with pytest.raises(JsonGptInsightsBoundaryError,
                       match="MISSING_BASE_STATE_CONFLICT"):
        plan(prior=material_fingerprint(EVIDENCE))


@pytest.mark.parametrize("options", [
    {"ticket": {**TICKET, "companyID": 999}},
    {"client_id": "other"},
    {"evidence": InsightEvidence(category="printing",
                                ticket_number="T-SYNTHETIC",
                                ticket_title=TICKET["title"])},
])
def test_untrusted_client_or_category_blocked(options):
    with pytest.raises(JsonGptInsightsBoundaryError):
        plan(**options)


def test_unverified_device_identity_blocks_inferred_endpoint_facts():
    evidence = InsightEvidence(
        category="network", ticket_number="T-SYNTHETIC",
        ticket_title=TICKET["title"], device_name="UNKNOWN-COMPUTER")
    with pytest.raises(JsonGptInsightsBoundaryError,
                       match="DEVICE_IDENTITY_NOT_VERIFIED"):
        plan(evidence=evidence)


def test_incomplete_note_page_fails_closed():
    with pytest.raises(JsonGptInsightsBoundaryError,
                       match="PAGINATED"):
        plan(notes_response={
            "status": "succeeded",
            "evidence": {"data": {"items": [], "has_more": True}},
        })


def test_gpt_insights_json_branches_are_approval_bound_and_fail_closed():
    import json
    from pathlib import Path
    from autonomous_remediation.playbook_document import validate_playbook_document
    from autonomous_remediation.playbook_runtime import JsonPlaybookInterpreter
    path = (Path(__file__).resolve().parents[3] /
            "docs/playbooks/json/migration/candidates/gpt_insights_tech_assist.v1.json")
    doc = validate_playbook_document(json.loads(path.read_text()))
    interpreter = JsonPlaybookInterpreter(doc)
    assert interpreter.instruction(step_id="eligibility_gate", facts={}).step_id == "human_review"
    assert interpreter.instruction(step_id="classify", facts={}).step_id == "human_review"
    for disposition, approval_fact, action in [
        ("create", "exact_promoted_jason_internal_note_create", "create_note"),
        ("update", "exact_promoted_jason_owned_internal_note_update", "update_note"),
    ]:
        assert interpreter.instruction(
            step_id="classify",
            facts={"verified_material_disposition": disposition},
        ).step_id == "human_review"
        output = interpreter.instruction(
            step_id="classify",
            facts={"verified_material_disposition": disposition,
                   approval_fact: True,
                   "trusted_exact_note_mutation_arguments": {"payload": {
                       "ticketID": 321, "title": "GPT Insights",
                       "description": "Synthetic only",
                       "noteType": 3, "publish": 2,
                   }}},
        )
        assert output.step_id == action
        assert output.approval_required is True
        assert output.approval_classification == "modifying"
    assert interpreter.instruction(
        step_id="classify", facts={"verified_material_disposition": "current"},
    ).step_id == "current"
    assert interpreter.instruction(step_id="readback_gate", facts={}).step_id == "human_review"
