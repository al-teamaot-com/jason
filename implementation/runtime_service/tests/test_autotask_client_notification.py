from __future__ import annotations

import pytest

from jason_runtime.autotask_client_notification import (
    AUTOTASK_CLIENT_NOTIFICATION_APPROVED_WORKFLOW_PROFILE,
    AUTOTASK_CLIENT_NOTIFICATION_GROMELSKI_VULSCAN_PROFILE,
    AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV,
    AUTOTASK_CLIENT_NOTIFICATION_TEST_COMPANY_ID,
    AUTOTASK_CLIENT_NOTIFICATION_TEST_PROFILE,
    AutotaskClientNotificationScopeError,
    validate_approved_workflow_scope,
    validate_client_notification_test_scope,
    validate_gromelski_vulscan_scope,
)
from jason_runtime.vulscan_client_policy import (
    GROMELSKI_COMPANY_ID,
    GROMELSKI_PRIMARY_CONTACT_ID,
    VULSCAN_CLIENT_NOTE_BODY,
    VULSCAN_CLIENT_NOTE_TEMPLATE_ID,
    VULSCAN_CLIENT_NOTE_TITLE,
)


def _enable(monkeypatch):
    monkeypatch.setenv(
        AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV,
        AUTOTASK_CLIENT_NOTIFICATION_TEST_PROFILE,
    )


def _enable_gromelski(monkeypatch):
    monkeypatch.setenv(
        AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV,
        AUTOTASK_CLIENT_NOTIFICATION_GROMELSKI_VULSCAN_PROFILE,
    )


def test_test_mode_accepts_only_xyz_ticket_and_contact(monkeypatch):
    _enable(monkeypatch)
    result = validate_client_notification_test_scope(
        ticket_company_id=AUTOTASK_CLIENT_NOTIFICATION_TEST_COMPANY_ID,
        contact_company_id=AUTOTASK_CLIENT_NOTIFICATION_TEST_COMPANY_ID,
        contact_email="xyz.client.test@gmail.com",
        requested_recipient="XYZ.Client.Test@gmail.com",
    )
    assert result.ticket_company_id == 1158
    assert result.contact_company_id == 1158
    assert result.contact_email == "xyz.client.test@gmail.com"


def test_test_mode_rejects_non_xyz_ticket(monkeypatch):
    _enable(monkeypatch)
    with pytest.raises(AutotaskClientNotificationScopeError, match="TICKET_COMPANY_NOT_XYZ"):
        validate_client_notification_test_scope(
            ticket_company_id=333,
            contact_company_id=1158,
            contact_email="xyz.client.test@gmail.com",
        )


def test_test_mode_rejects_non_xyz_contact(monkeypatch):
    _enable(monkeypatch)
    with pytest.raises(AutotaskClientNotificationScopeError, match="CONTACT_COMPANY_NOT_XYZ"):
        validate_client_notification_test_scope(
            ticket_company_id=1158,
            contact_company_id=333,
            contact_email="xyz.client.test@gmail.com",
        )


def test_test_mode_rejects_recipient_override(monkeypatch):
    _enable(monkeypatch)
    with pytest.raises(AutotaskClientNotificationScopeError, match="RECIPIENT_MUST_MATCH_CONTACT"):
        validate_client_notification_test_scope(
            ticket_company_id=1158,
            contact_company_id=1158,
            contact_email="xyz.client.test@gmail.com",
            requested_recipient="someoneelse@example.com",
        )


def test_test_mode_rejects_when_profile_is_not_enabled(monkeypatch):
    monkeypatch.delenv(AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV, raising=False)
    with pytest.raises(AutotaskClientNotificationScopeError, match="TEST_MODE_NOT_ENABLED"):
        validate_client_notification_test_scope(
            ticket_company_id=1158,
            contact_company_id=1158,
            contact_email="xyz.client.test@gmail.com",
        )


def test_gromelski_scope_accepts_only_primary_contact_and_exact_template(monkeypatch):
    _enable_gromelski(monkeypatch)
    result = validate_gromelski_vulscan_scope(
        ticket_company_id=GROMELSKI_COMPANY_ID,
        contact_id=GROMELSKI_PRIMARY_CONTACT_ID,
        contact_company_id=GROMELSKI_COMPANY_ID,
        contact_email="chris.benton@e-gai.com",
        primary_contact=True,
        receives_email_notifications=True,
        note_title=VULSCAN_CLIENT_NOTE_TITLE,
        note_body=VULSCAN_CLIENT_NOTE_BODY,
        template_id=VULSCAN_CLIENT_NOTE_TEMPLATE_ID,
    )
    assert result.ticket_company_id == 597
    assert result.contact_company_id == 597
    assert result.contact_email == "chris.benton@e-gai.com"


@pytest.mark.parametrize(
    ("field", "value", "error"),
    (
        ("ticket_company_id", 1158, "TICKET_COMPANY_NOT_GROMELSKI"),
        ("contact_id", 1, "CONTACT_NOT_GROMELSKI_PRIMARY"),
        ("contact_company_id", 1158, "CONTACT_COMPANY_NOT_GROMELSKI"),
        ("contact_email", "other@e-gai.com", "CONTACT_EMAIL_MISMATCH"),
        ("primary_contact", False, "CONTACT_NOT_MARKED_PRIMARY"),
        (
            "receives_email_notifications",
            False,
            "CONTACT_EMAIL_NOTIFICATIONS_DISABLED",
        ),
        ("note_title", "Different", "VULSCAN_TITLE_MISMATCH"),
        ("note_body", "Different", "VULSCAN_BODY_MISMATCH"),
        ("template_id", "different-template", "VULSCAN_TEMPLATE_ID_MISMATCH"),
    ),
)
def test_gromelski_scope_fails_closed_on_scope_or_template_drift(
    monkeypatch,
    field,
    value,
    error,
):
    _enable_gromelski(monkeypatch)
    arguments = {
        "ticket_company_id": GROMELSKI_COMPANY_ID,
        "contact_id": GROMELSKI_PRIMARY_CONTACT_ID,
        "contact_company_id": GROMELSKI_COMPANY_ID,
        "contact_email": "chris.benton@e-gai.com",
        "primary_contact": True,
        "receives_email_notifications": True,
        "note_title": VULSCAN_CLIENT_NOTE_TITLE,
        "note_body": VULSCAN_CLIENT_NOTE_BODY,
        "template_id": VULSCAN_CLIENT_NOTE_TEMPLATE_ID,
    }
    arguments[field] = value
    with pytest.raises(AutotaskClientNotificationScopeError, match=error):
        validate_gromelski_vulscan_scope(**arguments)


def test_exact_profile_activates_only_client_notification(monkeypatch):
    from datetime import datetime, timezone
    from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
    from kernel.execution_providers import ExecutionProviderRegistryService, InMemoryExecutionProviderRegistry
    from jason_runtime.autotask_client_notification import (
        AUTOTASK_CLIENT_NOTIFICATION_PROVIDER,
        register_autotask_client_notification_runtime_foundation,
    )

    monkeypatch.setenv(
        AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV,
        AUTOTASK_CLIENT_NOTIFICATION_GROMELSKI_VULSCAN_PROFILE,
    )
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
    state = register_autotask_client_notification_runtime_foundation(
        capabilities=capabilities,
        providers=providers,
        now=datetime.now(timezone.utc),
    )
    assert state.enabled is True
    assert capabilities.get(
        capability_name="service.ticket.client.notification.create",
        version="1.0",
    ).lifecycle_status.value == "active"
    assert providers.get(
        AUTOTASK_CLIENT_NOTIFICATION_PROVIDER
    ).lifecycle_status.value == "available"


def _enable_approved_workflow(monkeypatch):
    monkeypatch.setenv(
        AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV,
        AUTOTASK_CLIENT_NOTIFICATION_APPROVED_WORKFLOW_PROFILE,
    )


def test_approved_workflow_accepts_exact_registered_template(monkeypatch):
    _enable_approved_workflow(monkeypatch)
    result = validate_approved_workflow_scope(
        ticket_company_id=597,
        contact_company_id=597,
        contact_email="client@example.com",
        receives_email_notifications=True,
        workflow_id="vulscan_missing_patch",
        template_id=VULSCAN_CLIENT_NOTE_TEMPLATE_ID,
        note_title=VULSCAN_CLIENT_NOTE_TITLE,
        note_body=VULSCAN_CLIENT_NOTE_BODY,
        requested_recipient="CLIENT@example.com",
    )
    assert result.ticket_company_id == 597
    assert result.contact_company_id == 597
    assert result.contact_email == "client@example.com"


def test_approved_workflow_rejects_template_bound_to_other_workflow(monkeypatch):
    _enable_approved_workflow(monkeypatch)
    with pytest.raises(
        AutotaskClientNotificationScopeError,
        match="WORKFLOW_TEMPLATE_NOT_APPROVED",
    ):
        validate_approved_workflow_scope(
            ticket_company_id=597,
            contact_company_id=597,
            contact_email="client@example.com",
            receives_email_notifications=True,
            workflow_id="different_workflow",
            template_id=VULSCAN_CLIENT_NOTE_TEMPLATE_ID,
            note_title=VULSCAN_CLIENT_NOTE_TITLE,
            note_body=VULSCAN_CLIENT_NOTE_BODY,
        )


def test_approved_workflow_rejects_modified_canned_body(monkeypatch):
    _enable_approved_workflow(monkeypatch)
    with pytest.raises(
        AutotaskClientNotificationScopeError,
        match="APPROVED_BODY_MISMATCH",
    ):
        validate_approved_workflow_scope(
            ticket_company_id=597,
            contact_company_id=597,
            contact_email="client@example.com",
            receives_email_notifications=True,
            workflow_id="vulscan_missing_patch",
            template_id=VULSCAN_CLIENT_NOTE_TEMPLATE_ID,
            note_title=VULSCAN_CLIENT_NOTE_TITLE,
            note_body="Changed by caller",
        )


def test_approved_workflow_rejects_cross_company_contact(monkeypatch):
    _enable_approved_workflow(monkeypatch)
    with pytest.raises(
        AutotaskClientNotificationScopeError,
        match="TICKET_CONTACT_COMPANY_MISMATCH",
    ):
        validate_approved_workflow_scope(
            ticket_company_id=597,
            contact_company_id=598,
            contact_email="client@example.com",
            receives_email_notifications=True,
            workflow_id="vulscan_missing_patch",
            template_id=VULSCAN_CLIENT_NOTE_TEMPLATE_ID,
            note_title=VULSCAN_CLIENT_NOTE_TITLE,
            note_body=VULSCAN_CLIENT_NOTE_BODY,
        )


def test_approved_workflow_requires_contact_email_notifications(monkeypatch):
    _enable_approved_workflow(monkeypatch)
    with pytest.raises(
        AutotaskClientNotificationScopeError,
        match="EMAIL_NOTIFICATIONS_DISABLED",
    ):
        validate_approved_workflow_scope(
            ticket_company_id=597,
            contact_company_id=597,
            contact_email="client@example.com",
            receives_email_notifications=False,
            workflow_id="vulscan_missing_patch",
            template_id=VULSCAN_CLIENT_NOTE_TEMPLATE_ID,
            note_title=VULSCAN_CLIENT_NOTE_TITLE,
            note_body=VULSCAN_CLIENT_NOTE_BODY,
        )


def test_xyz_notification_acceptance_exact_ticket_and_contact(monkeypatch):
    from jason_runtime.autotask_client_notification import (
        validate_xyz_notification_acceptance_scope as validate,
        XYZ_NOTIFICATION_ACCEPTANCE_WORKFLOW as workflow,
        XYZ_NOTIFICATION_ACCEPTANCE_TEMPLATE as template,
    )
    baseline = {
        "ticket_id": 141431,
        "ticket_number": "T20260926.0088",
        "ticket_company_id": 1158,
        "contact_id": 30683022,
        "contact_company_id": 1158,
        "contact_email": "al.bccomputers@gmail.com",
        "receives_email_notifications": True,
        "workflow_id": workflow,
        "template_id": template,
        "requested_recipient": "AL.BCCOMPUTERS@gmail.com",
    }
    assert validate(**baseline) is None
    for key, wrong in (
        ("ticket_id", 7701),
        ("ticket_id", True),
        ("ticket_number", "T20240821.0001"),
        ("ticket_company_id", 597),
        ("contact_id", 30683493),
        ("contact_company_id", 597),
        ("contact_email", "not-the-authorized-user@gmail.com"),
        ("receives_email_notifications", False),
        ("workflow_id", "vulscan_missing_patch"),
        ("template_id", "vulscan-approved-or-installed-v1"),
        ("requested_recipient", "chris.benton@e-gai.com"),
    ):
        bad = {**baseline, key: wrong}
        with pytest.raises(
            AutotaskClientNotificationScopeError,
            match="CLIENT_NOTIFICATION_XYZ_ACCEPTANCE_EXACT_SCOPE_REQUIRED",
        ):
            validate(**bad)


def test_xyz_notification_acceptance_approved_message_is_test_only():
    from jason_runtime.approved_client_messages import (
        resolve_approved_client_message,
    )
    from jason_runtime.autotask_client_notification import (
        XYZ_NOTIFICATION_ACCEPTANCE_WORKFLOW as workflow,
        XYZ_NOTIFICATION_ACCEPTANCE_TEMPLATE as template,
    )
    approved = resolve_approved_client_message(
        workflow_id=workflow, template_id=template,
    )
    assert approved.title.startswith("JASON TEST ONLY")
    assert "No action is required" in approved.body
    assert "vulnerability" in approved.body
    assert "No service request" in approved.body
    assert approved.recipient_policy == "ticket_contact"
    assert approved.require_email_notifications is True


def test_xyz_notification_scope_is_enforced_in_connector_before_provider_send(monkeypatch):
    from types import SimpleNamespace
    from jason_runtime.autotask_client_notification import (
        AutotaskClientNotificationConnector as Connector,
        AUTOTASK_CLIENT_NOTIFICATION_APPROVED_WORKFLOW_PROFILE,
        XYZ_NOTIFICATION_ACCEPTANCE_WORKFLOW,
        XYZ_NOTIFICATION_ACCEPTANCE_TEMPLATE,
    )
    monkeypatch.setenv(
        AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV,
        AUTOTASK_CLIENT_NOTIFICATION_APPROVED_WORKFLOW_PROFILE,
    )
    calls = []
    test_ticket = {
        "companyID": 1158, "contactID": 30683022,
        "ticketNumber": "T20260926.0088",
    }
    test_contact = {
        "companyID": 1158, "emailAddress": "al.bccomputers@gmail.com",
        "receivesEmailNotifications": True,
    }

    class AuthoritativeReads:
        def _read_item(self, *, request, capability, arguments):
            calls.append((capability, dict(arguments)))
            if capability == "autotask.ticket.get":
                return dict(test_ticket)
            if capability == "autotask.contact.get":
                return dict(test_contact)
            raise AssertionError("unexpected provider capability")

    from jason_runtime.approved_client_messages import resolve_approved_client_message
    message = resolve_approved_client_message(
        workflow_id=XYZ_NOTIFICATION_ACCEPTANCE_WORKFLOW,
        template_id=XYZ_NOTIFICATION_ACCEPTANCE_TEMPLATE,
    )
    request = SimpleNamespace(arguments={
        "workflow_id": XYZ_NOTIFICATION_ACCEPTANCE_WORKFLOW,
        "template_id": XYZ_NOTIFICATION_ACCEPTANCE_TEMPLATE,
        "payload": {
            "ticketID": 141431,
            "title": message.title,
            "description": message.body,
        },
        "recipient": "al.bccomputers@gmail.com",
    })
    Connector._validate_scope(
        AuthoritativeReads(), request, 141431,
    )
    assert [x[0] for x in calls] == [
        "autotask.ticket.get", "autotask.contact.get",
    ]
    # A different ticket cannot be accepted by merely sending the same
    # workflow/template pair.
    with pytest.raises(
        AutotaskClientNotificationScopeError,
        match="CLIENT_NOTIFICATION_XYZ_ACCEPTANCE_EXACT_SCOPE_REQUIRED",
    ):
        Connector._validate_scope(AuthoritativeReads(), request, 7701)
    # An Autotask contact override does not confer a new recipient.
    test_contact["emailAddress"] = "attacker@example.com"
    with pytest.raises(
        AutotaskClientNotificationScopeError,
        match="CLIENT_NOTIFICATION_XYZ_ACCEPTANCE_EXACT_SCOPE_REQUIRED",
    ):
        Connector._validate_scope(AuthoritativeReads(), request, 141431)

def test_approved_client_note_is_exactly_ticket_bound_and_client_visibility_is_distinct(monkeypatch):
    from connectors.core.contracts import ConnectorContext, ConnectorRequest
    from jason_runtime.autotask_client_notification import (
        AutotaskClientNotificationConnector,
    )
    from jason_runtime.autotask_internal_note import AutotaskInternalNoteConnector
    from jason_runtime.approved_client_messages import resolve_approved_client_message

    _enable_approved_workflow(monkeypatch)
    template = resolve_approved_client_message(
        workflow_id="vulscan_missing_patch",
        template_id=VULSCAN_CLIENT_NOTE_TEMPLATE_ID,
    )
    context = ConnectorContext(
        correlation_id="corr-ticketbound", principal_id="person-al",
        organization_id="aot", client_id=None,
        capability="autotask.ticket.note.create", mode="execute",
    )

    def payload(ticket_id):
        return ConnectorRequest(context=context, arguments={
            "workflow_id": "vulscan_missing_patch",
            "template_id": VULSCAN_CLIENT_NOTE_TEMPLATE_ID,
            "payload": {
                "ticketID": ticket_id, "title": template.title,
                "description": template.body,
            },
        })

    # Existing note transport binds the actual ticket ID into the immutable
    # provider plan, rather than sending free-form email.
    client_request = AutotaskClientNotificationConnector._normalize_approved_workflow_request(
        None, payload(71443)
    )
    expected = AutotaskClientNotificationConnector._expected_payload(client_request)
    assert expected["ticketID"] == 71443
    assert expected["noteType"] == 3
    assert expected["publish"] == 1
    assert AutotaskInternalNoteConnector.required_note_publish == 2

    # Ticketless or nonpositive targets are blocked before scope lookup, POST,
    # or any client delivery attempt.
    for invalid_id in (None, 0, -1, "not-a-ticket"):
        invalid_request = AutotaskClientNotificationConnector._normalize_approved_workflow_request(
            None, payload(invalid_id)
        )
        with pytest.raises(Exception):
            AutotaskClientNotificationConnector._expected_payload(invalid_request)

    # The client-visible and internal-only note contracts are disjoint.
    with pytest.raises(Exception, match="publish=2"):
        AutotaskInternalNoteConnector._expected_payload(client_request)
    internal_request = ConnectorRequest(context=context, arguments={
        "payload": {**expected, "publish": 2},
    })
    with pytest.raises(Exception, match="publish=1"):
        AutotaskClientNotificationConnector._expected_payload(internal_request)

def test_approved_client_note_provider_plan_is_bound_to_one_ticket_and_never_sends_during_prepare(
    monkeypatch,
):
    from connectors.autotask.mutation_connector import AUTOTASK_MUTATION_ENABLED_ENV
    from connectors.core.connector_base import PreparedRequest
    from connectors.core.contracts import ConnectorContext, ConnectorRequest
    from jason_runtime.autotask_client_notification import AutotaskClientNotificationConnector
    from jason_runtime.approved_client_messages import resolve_approved_client_message

    _enable_approved_workflow(monkeypatch)
    monkeypatch.setenv(AUTOTASK_MUTATION_ENABLED_ENV, "true")
    requested_ticket = 71443
    scopes = []

    class Secrets:
        def resolve(self, *_):
            return {}

    class Transport:
        def request(self, **kwargs):
            raise AssertionError("no provider write/read during synthetic prepare test")

    class Audit:
        def record(self, *_):
            pass

    def fake_scope(self, request, ticket_id):
        scopes.append(ticket_id)

    def fake_prepare(self, request, credentials):
        return PreparedRequest(
            method="POST", url="https://psa.example/V1.0/TicketNotes",
            headers={}, params=None, json=request.arguments["payload"],
            audit_operation="/V1.0/TicketNotes",
        )

    monkeypatch.setattr(AutotaskClientNotificationConnector, "_validate_scope", fake_scope)
    monkeypatch.setattr(AutotaskClientNotificationConnector, "prepare_request", fake_prepare)
    connector = AutotaskClientNotificationConnector(
        secrets=Secrets(), transport=Transport(), audit=Audit(), bindings=None
    )
    message = resolve_approved_client_message(
        workflow_id="vulscan_missing_patch",
        template_id=VULSCAN_CLIENT_NOTE_TEMPLATE_ID,
    )

    def req(ticket_id):
        return ConnectorRequest(
            context=ConnectorContext(
                correlation_id="corr-plan", principal_id="person-al",
                organization_id="aot", client_id=None,
                capability="autotask.ticket.note.create", mode="execute",
            ),
            arguments={
                "workflow_id": "vulscan_missing_patch",
                "template_id": VULSCAN_CLIENT_NOTE_TEMPLATE_ID,
                "payload": {"ticketID": ticket_id,
                            "title": "untrusted title is not used",
                            "description": "untrusted body is not used"},
            },
        )

    plan = connector.prepare_governed_execution(req(requested_ticket))
    assert scopes == [requested_ticket]
    assert plan.resource_identifier == str(requested_ticket)
    assert plan.payload == {
        "ticketID": requested_ticket,
        "title": message.title,
        "description": message.body,
        "noteType": 3,
        "publish": 1,
    }
    with pytest.raises(Exception):
        connector.prepare_governed_execution(req(None))
    assert scopes == [requested_ticket]

def test_owner_approved_xyz_fixture_uses_one_standard_workflow_not_legacy_send_mode(
    monkeypatch,
):
    """Approved client != approval for a separate generic Gmail sender."""
    from datetime import datetime, timezone
    from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
    from kernel.execution_providers import (
        ExecutionProviderRegistryService, InMemoryExecutionProviderRegistry,
    )
    from jason_runtime.autotask_client_notification import (
        AUTOTASK_CLIENT_NOTIFICATION_APPROVED_WORKFLOW_PROFILE,
        AUTOTASK_CLIENT_NOTIFICATION_TEST_PROFILE,
        AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV,
        XYZ_NOTIFICATION_ACCEPTANCE_WORKFLOW,
        XYZ_NOTIFICATION_ACCEPTANCE_TEMPLATE,
        XYZ_NOTIFICATION_ACCEPTANCE_CONTACT_ID,
        XYZ_NOTIFICATION_ACCEPTANCE_EMAIL,
        XYZ_NOTIFICATION_ACCEPTANCE_TICKET_ID,
        XYZ_NOTIFICATION_ACCEPTANCE_TICKET_NUMBER,
        AUTOTASK_CLIENT_NOTIFICATION_TEST_COMPANY_ID,
        validate_xyz_notification_acceptance_scope,
        register_autotask_client_notification_runtime_foundation,
    )
    from jason_runtime.approved_client_messages import resolve_approved_client_message

    assert XYZ_NOTIFICATION_ACCEPTANCE_TICKET_ID == 141431
    assert XYZ_NOTIFICATION_ACCEPTANCE_TICKET_NUMBER == "T20260926.0088"
    assert XYZ_NOTIFICATION_ACCEPTANCE_CONTACT_ID == 30683022
    assert XYZ_NOTIFICATION_ACCEPTANCE_EMAIL == "al.bccomputers@gmail.com"
    assert AUTOTASK_CLIENT_NOTIFICATION_TEST_COMPANY_ID == 1158
    monkeypatch.setenv(
        AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV,
        AUTOTASK_CLIENT_NOTIFICATION_TEST_PROFILE,
    )
    with pytest.raises(RuntimeError, match="unsupported.*profile"):
        register_autotask_client_notification_runtime_foundation(
            capabilities=CapabilityRegistryService(
                registry=InMemoryCapabilityRegistry()
            ),
            providers=ExecutionProviderRegistryService(
                registry=InMemoryExecutionProviderRegistry()
            ),
            now=datetime.now(timezone.utc),
        )
    monkeypatch.setenv(
        AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV,
        AUTOTASK_CLIENT_NOTIFICATION_APPROVED_WORKFLOW_PROFILE,
    )
    template = resolve_approved_client_message(
        workflow_id=XYZ_NOTIFICATION_ACCEPTANCE_WORKFLOW,
        template_id=XYZ_NOTIFICATION_ACCEPTANCE_TEMPLATE,
    )
    assert template.recipient_policy == "ticket_contact"
    assert template.title.startswith("JASON TEST ONLY")
    assert validate_xyz_notification_acceptance_scope(
        ticket_id=XYZ_NOTIFICATION_ACCEPTANCE_TICKET_ID,
        ticket_number=XYZ_NOTIFICATION_ACCEPTANCE_TICKET_NUMBER,
        ticket_company_id=AUTOTASK_CLIENT_NOTIFICATION_TEST_COMPANY_ID,
        contact_id=XYZ_NOTIFICATION_ACCEPTANCE_CONTACT_ID,
        contact_company_id=AUTOTASK_CLIENT_NOTIFICATION_TEST_COMPANY_ID,
        contact_email=XYZ_NOTIFICATION_ACCEPTANCE_EMAIL,
        receives_email_notifications=True,
        workflow_id=XYZ_NOTIFICATION_ACCEPTANCE_WORKFLOW,
        template_id=XYZ_NOTIFICATION_ACCEPTANCE_TEMPLATE,
        requested_recipient="AL.BCCOMPUTERS@gmail.com",
    ) is None
