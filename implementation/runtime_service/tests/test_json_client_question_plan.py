"""Exact 120-template Client Question pure source reconciliation."""
from hashlib import sha256
import pytest

from jason_runtime.client_information_requests import (
    load_round1_catalog, render_question,
)
from jason_runtime.json_client_question_plan import (
    JsonClientQuestionBoundaryError, plan_client_question,
)

CATALOG = load_round1_catalog()
TICKET = {
    "id": 123, "companyID": 777, "contactID": 50,
    "ticketNumber": "T20261119.0001", "status": "In Progress",
    "description": "",
}
CONTACT = {
    "id": 50, "companyID": 777,
    "emailAddress": "synthetic-recipient@example.invalid",
    "receivesEmailNotifications": True,
}


def plan(question=None, *, ticket=TICKET, contact=CONTACT,
         notes=(), history=(), **changes):
    question = question or CATALOG.questions[0]
    params = {
        "ticket_id": 123, "exact_ticket": ticket,
        "exact_contact": contact, "question_id": question.question_id,
        "missing_fact_code": question.gap_code,
        "missing_fact_corroborated": True,
        "evidence_sha256": "a" * 64,
        "note_read": {"status": "succeeded", "evidence": {
            "data": {"items": list(notes)}}},
        "notification_history_read": {"status": "succeeded", "evidence": {
            "data": {"items": list(history)}}},
        "catalog": CATALOG,
    }
    params.update(changes)
    return plan_client_question(**params)


@pytest.mark.parametrize("question", CATALOG.questions, ids=lambda q:q.question_id)
def test_all_120_source_templates_are_exact_and_only_routine_intents_proposed(question):
    if question.review_class != "routine":
        with pytest.raises(JsonClientQuestionBoundaryError,
                           match="EXACT_TECHNICIAN_REVIEW_REQUIRED"):
            plan(question)
        return
    result = plan(question)
    assert result.disposition == "proposed_not_authorized"
    assert result.capability == "service.ticket.client.notification.create"
    assert result.arguments["template_id"] == question.template_id
    assert result.arguments["payload"] == {"ticketID": 123}
    assert result.arguments["workflow_id"] == "client_information_request"
    body = render_question(question, "T20261119.0001", catalog=CATALOG)
    assert result.body_sha256 == sha256(body.encode()).hexdigest()
    assert result.evidence_sha256 == "a" * 64


@pytest.mark.parametrize("change", [
    {"ticket": {**TICKET, "companyID": 778}},
    {"contact": {**CONTACT, "companyID": 778}},
    {"contact": {**CONTACT, "receivesEmailNotifications": False}},
    {"contact": {**CONTACT, "emailAddress": "badrecipient"}},
    {"ticket": {**TICKET, "contactID": 99}},
    {"ticket": {**TICKET, "status": "Complete"}},
    {"missing_fact_corroborated": False},
    {"evidence_sha256": "wrong"},
    {"question_id": "JQ-999"},
])
def test_invalid_scope_or_diagnostic_never_proposes_external_message(change):
    routine = next(q for q in CATALOG.questions if q.review_class == "routine")
    with pytest.raises(JsonClientQuestionBoundaryError):
        plan(routine, **change)


def test_existing_exact_question_is_no_action_and_preserves_baseline():
    q = next(q for q in CATALOG.questions
             if q.review_class == "routine" and q.question_id != "JQ-001")
    body = render_question(q, "T20261119.0001", catalog=CATALOG)
    result = plan(
        q, notes=[{"id": 50, "title": q.title, "description": body}],
        history=[{"id": 3}, {"id": 9}],
    )
    assert result.disposition == "already_present"
    assert result.baseline_notification_id == 9
    assert result.capability is None


def test_initial_description_already_available_never_sends_jq001():
    q = CATALOG.by_id("JQ-001")
    result = plan(q, ticket={**TICKET, "description": "Already described"})
    assert result.disposition == "information_already_available"


def test_initial_contact_authored_description_already_available_never_sends_jq001():
    q = CATALOG.by_id("JQ-001")
    result = plan(q, notes=[{
        "id": 1, "createdByContactID": 50, "description": "Client explained issue",
    }])
    assert result.disposition == "information_already_available"


def test_pagination_or_unavailable_governed_evidence_denied():
    q = next(q for q in CATALOG.questions if q.review_class == "routine")
    with pytest.raises(JsonClientQuestionBoundaryError, match="LIST_INCOMPLETE"):
        plan(q, note_read={"status": "succeeded", "evidence": {
            "data": {"items": [], "has_more": True}}},
        )


def test_intent_does_not_include_recipient_override_or_external_freeform_body():
    q = next(q for q in CATALOG.questions if q.review_class == "routine")
    args = plan(q).arguments
    assert set(args) == {"workflow_id", "template_id", "ticket_number", "payload"}
    assert "email" not in str(args).lower()
    assert "description" not in str(args).lower()


def test_source_client_question_json_denies_unverified_external_send():
    import json
    from pathlib import Path
    from autonomous_remediation.playbook_document import validate_playbook_document
    from autonomous_remediation.playbook_runtime import JsonPlaybookInterpreter
    file = (Path(__file__).resolve().parents[3] /
            "docs/playbooks/json/migration/candidates/client_information_request.v1.json")
    doc = validate_playbook_document(json.loads(file.read_text()))
    interpreter = JsonPlaybookInterpreter(doc)
    assert interpreter.instruction(step_id="ticket_gate", facts={}).step_id == "human_review"
    assert interpreter.instruction(step_id="question_gate", facts={}).step_id == "human_review"
    assert interpreter.instruction(step_id="promotion_gate", facts={}).step_id == "human_review"
    assert interpreter.instruction(
        step_id="question_gate",
        facts={"verified_question_disposition": "already_present"},
    ).step_id == "already_present"
    assert interpreter.instruction(
        step_id="question_gate",
        facts={"verified_question_disposition": "proposed_not_authorized"},
    ).step_id == "human_review"
    proposed = plan(next(q for q in CATALOG.questions if q.review_class == "routine"))
    intent = interpreter.instruction(
        step_id="question_gate",
        facts={
            "verified_question_disposition": proposed.disposition,
            "exact_current_owner_promotion_and_profile_and_reservation": True,
            "trusted_exact_catalog_notification_arguments": proposed.arguments,
        },
    )
    assert intent.step_id == "send_question"
    assert intent.approval_required is True
    assert intent.approval_classification == "modifying"
    assert intent.arguments == proposed.arguments
    assert interpreter.instruction(step_id="outbound_gate", facts={}).step_id == "human_review"
    assert interpreter.instruction(step_id="delivery_gate", facts={}).step_id == "human_review"
    assert interpreter.instruction(step_id="reply_gate", facts={}).step_id == "human_review"
