from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from jason_runtime.client_information_requests import (
    CLIENT_QUESTION_APPROVED_PROFILE,
    CLIENT_QUESTION_PROFILE_ENV,
    ClientQuestionError,
    ClientQuestionWorkflow,
    SQLiteClientQuestionLedger,
    load_round1_catalog,
    render_question,
    select_question_from_diagnostic,
)
from jason_runtime.approved_client_messages import (
    ApprovedClientMessageRegistryError,
    resolve_approved_client_message,
)
from jason_runtime.autotask_client_notification import (
    AUTOTASK_CLIENT_NOTIFICATION_APPROVED_WORKFLOW_PROFILE,
    AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV,
    AutotaskClientNotificationScopeError,
    validate_approved_workflow_scope,
)


TICKET = {"id": 1001, "ticketNumber": "T20261028.0048",
          "companyID": 42, "contactID": 88, "status": "New"}
CONTACT = {"id": 88, "companyID": 42,
           "emailAddress": "customer@example.com",
           "receivesEmailNotifications": True}
EVIDENCE = hashlib.sha256(b"missing error text from governed diagnostic").hexdigest()


class FakeReads:
    def __init__(self):
        self.ticket = dict(TICKET)
        self.contact = dict(CONTACT)
        self.notes = []
        self.history = []
        self.calls = []

    def execute(self, capability, arguments):
        self.calls.append((capability, dict(arguments)))
        if capability == "service.ticket.read":
            data = {"item": dict(self.ticket)}
        elif capability == "service.contact.read":
            data = {"item": dict(self.contact)}
        elif capability == "service.ticket.notes.search":
            data = {"items": list(self.notes)}
        elif capability == "service.notification.history.search":
            data = {"items": list(self.history)}
        else:
            raise AssertionError("Unapproved read capability " + capability)
        return {"status": "succeeded", "evidence": {"data": data}}


class FakeActions:
    def __init__(self, reads):
        self.reads = reads
        self.calls = []
        self.fail_before_write = False
        self.readback = True

    def execute(self, scope, capability, arguments):
        self.calls.append((scope, capability, dict(arguments)))
        if self.fail_before_write:
            raise TimeoutError("write outcome unknown")
        assert capability == "service.ticket.client.notification.create"
        q = load_round1_catalog().by_template_id(arguments["template_id"])
        self.reads.notes.append({
            "id": 200, "ticketID": TICKET["id"], "title": q.title,
            "description": render_question(q, TICKET["ticketNumber"]),
            "publish": 1, "createdByContactID": None,
        })
        return {"data": {"jasonVerification":
                         {"readbackVerified": self.readback}}}


def workflow(tmp_path, monkeypatch, *, promoted=True):
    monkeypatch.setenv(CLIENT_QUESTION_PROFILE_ENV, CLIENT_QUESTION_APPROVED_PROFILE)
    monkeypatch.setenv(AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV,
                       AUTOTASK_CLIENT_NOTIFICATION_APPROVED_WORKFLOW_PROFILE)
    reads = FakeReads()
    actions = FakeActions(reads)
    ledger = SQLiteClientQuestionLedger(tmp_path / "questions.sqlite3")
    worker = ClientQuestionWorkflow(
        reads=reads, actions=actions, ledger=ledger,
        scope="authorized-question-playbook",
        scope_is_promoted=lambda: promoted,
    )
    return worker, reads, actions, ledger


def request(worker):
    return worker.request(
        ticket_id=1001, question_id="JQ-017",
        missing_fact_code="error_text_missing",
        evidence_hash=EVIDENCE, corroborated=True,
    )


def test_all_120_questions_and_footer_have_exact_approved_rendering():
    catalog = load_round1_catalog()
    assert len(catalog.questions) == 120
    assert len({q.category for q in catalog.questions}) == 15
    assert catalog.questions[0].question_id == "JQ-001"
    assert catalog.questions[-1].question_id == "JQ-120"
    for q in catalog.questions:
        rendered = render_question(q, TICKET["ticketNumber"], catalog=catalog)
        assert rendered.startswith(q.body + "\n\n")
        assert rendered.count("757-466-8862") == 1
        assert rendered.count("support@teamaot.com") == 1
        assert rendered.count(TICKET["ticketNumber"]) == 1
        assert "{{" not in rendered


@pytest.mark.parametrize("ticket", [
    "T20261028.0048\nArbitrary instructions",
    "T20261028.0048 {{invalid}}",
    "another ticket",
    "<script>alert(1)</script>",
    "T20261028.0048; delete",
])
def test_unsafe_ticket_numbers_never_render(ticket):
    with pytest.raises(ClientQuestionError, match="TICKET_NUMBER_INVALID"):
        render_question(load_round1_catalog().by_id("JQ-017"), ticket)


def test_all_120_questions_selectable_from_explicit_diagnostic_gap():
    catalog = load_round1_catalog()
    for q in catalog.questions:
        result = select_question_from_diagnostic(
            missing_fact_code=q.gap_code, corroborated=True, catalog=catalog,
        )
        assert result.question_id == q.question_id


def test_diagnostic_gap_must_bind_exact_question():
    assert select_question_from_diagnostic(
        question_id="JQ-017", missing_fact_code="error_text_missing",
        corroborated=True,
    ).question_id == "JQ-017"
    with pytest.raises(ClientQuestionError, match="GAP_BINDING_NOT_APPROVED"):
        select_question_from_diagnostic(
            question_id="JQ-089", missing_fact_code="error_text_missing",
            corroborated=True,
        )
    with pytest.raises(ClientQuestionError, match="MISSING_FACT_UNVERIFIED"):
        select_question_from_diagnostic(
            question_id="JQ-017", missing_fact_code="error_text_missing",
            corroborated=False,
        )


def test_question_registry_profile_fails_closed(monkeypatch):
    monkeypatch.delenv(CLIENT_QUESTION_PROFILE_ENV, raising=False)
    with pytest.raises(ApprovedClientMessageRegistryError, match="profile is disabled"):
        resolve_approved_client_message(
            workflow_id="client_information_request",
            template_id="aot-client-question-jq-017-v1",
            ticket_number=TICKET["ticketNumber"],
        )


def test_static_vulscan_registry_behavior_unchanged(monkeypatch):
    monkeypatch.delenv(CLIENT_QUESTION_PROFILE_ENV, raising=False)
    t = resolve_approved_client_message(
        workflow_id="vulscan_missing_patch",
        template_id="vulscan-approved-or-installed-v1",
    )
    assert t.workflow_id == "vulscan_missing_patch"
    assert "client-support-footer" not in t.body
    assert "757-466-8862" not in t.body


def test_connector_accepts_only_exact_composed_client_question(monkeypatch):
    monkeypatch.setenv(CLIENT_QUESTION_PROFILE_ENV, CLIENT_QUESTION_APPROVED_PROFILE)
    monkeypatch.setenv(AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV,
                       AUTOTASK_CLIENT_NOTIFICATION_APPROVED_WORKFLOW_PROFILE)
    msg = resolve_approved_client_message(
        workflow_id="client_information_request",
        template_id="aot-client-question-jq-017-v1",
        ticket_number=TICKET["ticketNumber"],
    )
    kwargs = dict(
        ticket_company_id=42, contact_company_id=42,
        contact_email="customer@example.com", receives_email_notifications=True,
        workflow_id=msg.workflow_id, template_id=msg.template_id,
        ticket_number=TICKET["ticketNumber"],
        note_title=msg.title, note_body=msg.body,
    )
    result = validate_approved_workflow_scope(**kwargs)
    assert result.ticket_company_id == 42
    with pytest.raises(AutotaskClientNotificationScopeError, match="BODY_MISMATCH"):
        validate_approved_workflow_scope(**{**kwargs, "note_body": msg.body + " extra"})
    with pytest.raises(AutotaskClientNotificationScopeError, match="COMPANY_MISMATCH"):
        validate_approved_workflow_scope(**{**kwargs, "contact_company_id": 99})
    with pytest.raises(AutotaskClientNotificationScopeError, match="EMAIL_NOTIFICATIONS_DISABLED"):
        validate_approved_workflow_scope(
            **{**kwargs, "receives_email_notifications": False}
        )
    with pytest.raises(AutotaskClientNotificationScopeError, match="RECIPIENT_MUST_MATCH_CONTACT"):
        validate_approved_workflow_scope(
            **{**kwargs, "requested_recipient": "outsider@example.com"}
        )


def test_sensitive_questions_not_autonomously_sendable(monkeypatch):
    monkeypatch.setenv(CLIENT_QUESTION_PROFILE_ENV, CLIENT_QUESTION_APPROVED_PROFILE)
    with pytest.raises(ApprovedClientMessageRegistryError, match="not approved"):
        resolve_approved_client_message(
            workflow_id="client_information_request",
            template_id="aot-client-question-jq-097-v1",
            ticket_number=TICKET["ticketNumber"],
        )


def test_request_requires_exact_promotion(tmp_path, monkeypatch):
    worker, _, actions, _ = workflow(tmp_path, monkeypatch, promoted=False)
    with pytest.raises(ClientQuestionError, match="NOT_PROMOTED"):
        request(worker)
    assert not actions.calls


def test_request_rejects_cross_company_or_disabled_contact(tmp_path, monkeypatch):
    worker, reads, actions, _ = workflow(tmp_path, monkeypatch)
    reads.contact["companyID"] = 99
    with pytest.raises(ClientQuestionError, match="COMPANY_MISMATCH"):
        request(worker)
    assert not actions.calls
    reads.contact["companyID"] = 42
    reads.contact["receivesEmailNotifications"] = False
    with pytest.raises(ClientQuestionError, match="NOTIFICTIONS_DISABLED"):
        request(worker)
    assert not actions.calls


def test_request_and_reply_resume_only_once(tmp_path, monkeypatch):
    worker, reads, actions, ledger = workflow(tmp_path, monkeypatch)
    assert request(worker) == "delivery_pending"
    assert request(worker) in {"already_present", "already_reserved"}
    assert len(actions.calls) == 1
    record = ledger.find(1001, "JQ-017", EVIDENCE)
    assert record.state == "delivery_pending"
    assert record.outbound_note_id == 200
    assert worker.reconcile() == ((1001, "JQ-017", "delivery_pending"),)
    reads.history.append({
        "id": 12, "ticketID": 1001,
        "recipientEmailAddress": "stranger@example.com",
    })
    assert worker.reconcile() == ((1001, "JQ-017", "delivery_pending"),)
    reads.history.append({
        "id": 13, "ticketID": 1001,
        "recipientEmailAddress": "customer@example.com",
    })
    assert worker.reconcile() == ((1001, "JQ-017", "awaiting_reply"),)
    reads.notes.append({
        "id": 202, "ticketID": 1001, "title": "Client response",
        "description": "I can reproduce the problem.",
        "createdByContactID": 99,
    })
    assert worker.reconcile() == ((1001, "JQ-017", "awaiting_reply"),)
    reads.notes.append({
        "id": 203, "ticketID": 1001, "title": "Client response",
        "description": "The exact error is 0x123.",
        "createdByContactID": 88,
    })
    assert worker.reconcile() == ((1001, "JQ-017", "resume_pending"),)
    observed = []
    assert worker.reconcile(
        on_verified_reply=lambda row: observed.append(row.reply_note_id) or True
    ) == ((1001, "JQ-017", "resumed"),)
    assert observed == [203]
    assert worker.reconcile() == ()
    assert ledger.find(1001, "JQ-017", EVIDENCE).state == "resumed"


def test_uncertain_send_never_retries(tmp_path, monkeypatch):
    worker, reads, actions, ledger = workflow(tmp_path, monkeypatch)
    actions.fail_before_write = True
    with pytest.raises(TimeoutError, match="unknown"):
        request(worker)
    assert ledger.find(1001, "JQ-017", EVIDENCE).state == "send_uncertain"
    assert request(worker) == "already_reserved"
    assert len(actions.calls) == 1
    assert worker.reconcile() == ((1001, "JQ-017", "send_uncertain"),)


def test_source_note_search_failure_stops_before_write(tmp_path, monkeypatch):
    worker, reads, actions, _ = workflow(tmp_path, monkeypatch)
    reads.notes = [{"id": 1, "title": "Existing", "description": "text"}]
    reads.ticket["contactID"] = 0
    with pytest.raises(ClientQuestionError, match="CONTACT_REQUIRED"):
        request(worker)
    assert not actions.calls




def test_worker_reconciles_reply_to_correct_waiting_diagnostic_phase(tmp_path):
    from types import SimpleNamespace
    from jason_runtime.autonomy_worker_runtime import (
        OperationalAutonomyMaintenance,
        OperationalWork,
        SQLiteOperationalWorkStore,
    )
    from jason_runtime.client_information_requests import ClientQuestionRecord

    store = SQLiteOperationalWorkStore(tmp_path / "operational.sqlite3")
    paused = OperationalWork(
        ticket_id=1001, ticket_number=TICKET["ticketNumber"], title="DNS issue",
        playbook_id="dns_agent_diagnostic", source_queue="Jason",
        company_id=42, configuration_item_id=100, device_uid="datto-id",
        hostname="PC-1",
        phase="waiting_client_information:dns_diagnostic_dispatch",
    )
    store.put(paused)
    assert store.list_open() == ()
    worker = OperationalAutonomyMaintenance.__new__(OperationalAutonomyMaintenance)
    worker.store = store
    worker._scope_is_promoted = lambda scope: True
    reply = ClientQuestionRecord(
        ticket_id=1001, ticket_number=TICKET["ticketNumber"], company_id=42,
        contact_id=88, contact_email="customer@example.com",
        question_id="JQ-017", evidence_hash=EVIDENCE,
        resume_phase="dns_diagnostic_dispatch",
        state="reply_verified", baseline_notification_id=0,
        outbound_note_id=200, reply_note_id=203, resumed_at="",
    )
    candidate = SimpleNamespace(
        source_queue="Jason", context={"companyID": 42}
    )
    assert worker._resume_client_question_work(reply, {1001: candidate}) is True
    assert store.get(1001).phase == "dns_diagnostic_dispatch"
    assert len(store.list_open()) == 1
    # A crash after the work-store commit and before ledger commit is safe.
    assert worker._resume_client_question_work(reply, {1001: candidate}) is True
    assert store.get(1001).phase == "dns_diagnostic_dispatch"
    assert worker._resume_client_question_work(
        reply, {1001: SimpleNamespace(source_queue="Other",
                                       context={"companyID": 42})}
    ) is False


def test_worker_never_resumes_different_company_or_unapproved_scope(tmp_path):
    from types import SimpleNamespace
    from jason_runtime.autonomy_worker_runtime import (
        OperationalAutonomyMaintenance, OperationalWork, SQLiteOperationalWorkStore
    )
    from jason_runtime.client_information_requests import ClientQuestionRecord

    store = SQLiteOperationalWorkStore(tmp_path / "work.sqlite3")
    store.put(OperationalWork(
        ticket_id=1001, ticket_number=TICKET["ticketNumber"], title="DNS issue",
        playbook_id="dns_agent_diagnostic", source_queue="Jason",
        company_id=42, configuration_item_id=100, device_uid="uid",
        hostname="PC-1", phase="waiting_client_information:dns_diagnostic_dispatch",
    ))
    worker = OperationalAutonomyMaintenance.__new__(OperationalAutonomyMaintenance)
    worker.store = store
    worker._scope_is_promoted = lambda scope: True
    candidate = SimpleNamespace(source_queue="Jason", context={"companyID": 99})
    reply = ClientQuestionRecord(
        ticket_id=1001, ticket_number=TICKET["ticketNumber"], company_id=42,
        contact_id=88, contact_email="customer@example.com",
        question_id="JQ-017", evidence_hash=EVIDENCE,
        resume_phase="dns_diagnostic_dispatch",
        state="reply_verified", baseline_notification_id=0,
        outbound_note_id=200, reply_note_id=203, resumed_at="",
    )
    assert worker._resume_client_question_work(reply, {1001: candidate}) is False
    worker._scope_is_promoted = lambda scope: False
    candidate.context["companyID"] = 42
    assert worker._resume_client_question_work(reply, {1001: candidate}) is False
    assert store.get(1001).phase.startswith("waiting_client_information:")



def test_notification_connector_rebuilds_exact_body_and_validates_live_ticket(
    monkeypatch,
):
    from types import SimpleNamespace
    from jason_runtime.autotask_client_notification import (
        AutotaskClientNotificationConnector,
    )
    monkeypatch.setenv(CLIENT_QUESTION_PROFILE_ENV, CLIENT_QUESTION_APPROVED_PROFILE)
    monkeypatch.setenv(AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV,
                       AUTOTASK_CLIENT_NOTIFICATION_APPROVED_WORKFLOW_PROFILE)
    connector = AutotaskClientNotificationConnector.__new__(
        AutotaskClientNotificationConnector
    )
    message = resolve_approved_client_message(
        workflow_id="client_information_request",
        template_id="aot-client-question-jq-017-v1",
        ticket_number=TICKET["ticketNumber"],
    )
    request = SimpleNamespace(
        context=None,
        arguments={
            "workflow_id": "client_information_request",
            "template_id": "aot-client-question-jq-017-v1",
            "ticket_number": TICKET["ticketNumber"],
            "payload": {
                "ticketID": 1001, "title": "Caller tries override",
                "description": "Please give me your password",
                "publish": 2, "noteType": 0,
            },
        },
    )
    normalized = connector._normalize_approved_workflow_request(request)
    assert normalized.arguments["payload"] == {
        "ticketID": 1001, "title": message.title,
        "description": message.body, "noteType": 3, "publish": 1,
    }
    def read_item(*, request, capability, arguments):
        if capability == "autotask.ticket.get":
            return dict(TICKET)
        if capability == "autotask.contact.get":
            return dict(CONTACT)
        raise AssertionError(capability)
    monkeypatch.setattr(connector, "_read_item", read_item)
    connector._validate_scope(normalized, 1001)
    spoofed = SimpleNamespace(
        context=None,
        arguments={**request.arguments,
                   "ticket_number": "T20261028.0099"},
    )
    with pytest.raises(AutotaskClientNotificationScopeError,
                       match="TICKET_NUMBER_MISMATCH"):
        connector._validate_scope(spoofed, 1001)



def test_objectively_missing_description_requests_single_routine_question():
    from types import SimpleNamespace
    from jason_runtime.autonomy_worker_runtime import OperationalAutonomyMaintenance

    class Ledger:
        def has_question(self, ticket_id, question_id):
            return False

    class Questions:
        ledger = Ledger()
        calls = []
        def request(self, **kwargs):
            self.calls.append(kwargs)
            return "delivery_pending"

    class WorkStore:
        def get(self, ticket_id):
            return None

    worker = OperationalAutonomyMaintenance.__new__(OperationalAutonomyMaintenance)
    worker.client_questions = Questions()
    worker.store = WorkStore()
    worker._scope_is_promoted = lambda scope: True
    candidate = SimpleNamespace(
        resource_id=1001, source_queue="Jason",
        context={
            **TICKET, "description": "",
            "createdByContactID": 88,
            "_jason_source_status_label": "In Progress",
        },
    )
    worker._maybe_request_missing_client_description(candidate)
    assert len(worker.client_questions.calls) == 1
    args = worker.client_questions.calls[0]
    assert args["question_id"] == "JQ-001"
    assert args["missing_fact_code"] == "problem_description_missing"
    assert args["resume_phase"] == "queue_reassessment"
    assert len(args["evidence_hash"]) == 64
    # A monitoring alert, technician-created ticket, or ticket with details
    # must never be selected by the initial-intake rule.
    candidate.context["createdByContactID"] = 0
    worker._maybe_request_missing_client_description(candidate)
    candidate.context["createdByContactID"] = 88
    candidate.context["description"] = "Already described."
    worker._maybe_request_missing_client_description(candidate)
    candidate.context["description"] = ""
    candidate.source_queue = "Monitoring Alert"
    worker._maybe_request_missing_client_description(candidate)
    assert len(worker.client_questions.calls) == 1


def test_original_client_information_disables_redundant_initial_question(
    tmp_path, monkeypatch,
):
    worker, reads, actions, _ = workflow(tmp_path, monkeypatch)
    reads.ticket["description"] = "The entire issue is already described."
    assert worker.request(
        ticket_id=1001, missing_fact_code="problem_description_missing",
        evidence_hash=EVIDENCE, corroborated=True,
        resume_phase="queue_reassessment",
    ) == "information_already_available"
    assert not actions.calls
    reads.ticket["description"] = ""
    reads.notes.append({
        "id": 15, "createdByContactID": 88,
        "description": "This is a complete detail from the client.",
    })
    assert worker.request(
        ticket_id=1001, missing_fact_code="problem_description_missing",
        evidence_hash=EVIDENCE, corroborated=True,
        resume_phase="queue_reassessment",
    ) == "information_already_available"
    assert not actions.calls


def test_verified_reply_reactivates_existing_queue_reassessment():
    from types import SimpleNamespace
    from jason_runtime.autonomy_worker_runtime import OperationalAutonomyMaintenance
    from jason_runtime.client_information_requests import ClientQuestionRecord

    class WorkStore:
        def get(self, ticket_id):
            return None

    worker = OperationalAutonomyMaintenance.__new__(OperationalAutonomyMaintenance)
    worker.store = WorkStore()
    reply = ClientQuestionRecord(
        ticket_id=1001, ticket_number=TICKET["ticketNumber"], company_id=42,
        contact_id=88, contact_email="customer@example.com",
        question_id="JQ-001", evidence_hash=EVIDENCE,
        resume_phase="queue_reassessment",
        state="reply_verified", baseline_notification_id=0,
        outbound_note_id=200, reply_note_id=203, resumed_at="",
    )
    candidate = SimpleNamespace(
        source_queue="Jason", context={"companyID": 42,
                                       "ticketNumber": TICKET["ticketNumber"]}
    )
    assert worker._resume_client_question_work(reply, {1001: candidate}) is True
    candidate.context["companyID"] = 99
    assert worker._resume_client_question_work(reply, {1001: candidate}) is False
    candidate.context["companyID"] = 42
    candidate.context["ticketNumber"] = "T20261028.9999"
    assert worker._resume_client_question_work(reply, {1001: candidate}) is False
