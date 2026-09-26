from __future__ import annotations

import pytest

from jason_runtime.autotask_client_notification import (
    AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV,
    AUTOTASK_CLIENT_NOTIFICATION_TEST_COMPANY_ID,
    AUTOTASK_CLIENT_NOTIFICATION_TEST_PROFILE,
    AutotaskClientNotificationScopeError,
    validate_client_notification_test_scope,
)


def _enable(monkeypatch):
    monkeypatch.setenv(
        AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV,
        AUTOTASK_CLIENT_NOTIFICATION_TEST_PROFILE,
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
