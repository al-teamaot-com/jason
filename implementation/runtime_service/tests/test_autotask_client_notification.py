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
        AUTOTASK_CLIENT_NOTIFICATION_TEST_PROFILE,
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
