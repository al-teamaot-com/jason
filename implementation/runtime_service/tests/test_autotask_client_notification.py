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
