from __future__ import annotations

import os
from dataclasses import dataclass

from orchestrator.provider_mutation_capability_catalog import (
    SERVICE_TICKET_CLIENT_NOTIFICATION_CREATE,
)

AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV = (
    "JASON_AUTOTASK_CLIENT_NOTIFICATION_PROFILE"
)
AUTOTASK_CLIENT_NOTIFICATION_TEST_PROFILE = (
    "xyz-test-company-client-notification-v1"
)
AUTOTASK_CLIENT_NOTIFICATION_TEST_COMPANY_ID = 1158
AUTOTASK_CLIENT_NOTIFICATION_TEST_COMPANY_NAME = "XYZ Test Company"


class AutotaskClientNotificationScopeError(PermissionError):
    """Fail-closed client-notification pilot scope violation."""


@dataclass(frozen=True, slots=True)
class ClientNotificationTestScope:
    ticket_company_id: int
    contact_company_id: int
    contact_email: str


def client_notification_test_mode_enabled() -> bool:
    return (
        os.getenv(AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV, "")
        .strip()
        .casefold()
        == AUTOTASK_CLIENT_NOTIFICATION_TEST_PROFILE
    )


def validate_client_notification_test_scope(
    *,
    ticket_company_id: int,
    contact_company_id: int,
    contact_email: str,
    requested_recipient: str | None = None,
) -> ClientNotificationTestScope:
    """Enforce the constitutional pilot boundary before any send mutation.

    Both authoritative Autotask objects must belong to XYZ Test Company.
    The destination is derived from the Autotask contact record; a caller may
    optionally repeat it, but cannot substitute another recipient.
    """

    if not client_notification_test_mode_enabled():
        raise AutotaskClientNotificationScopeError(
            "CLIENT_NOTIFICATION_TEST_MODE_NOT_ENABLED"
        )

    try:
        ticket_company = int(ticket_company_id)
        contact_company = int(contact_company_id)
    except (TypeError, ValueError) as exc:
        raise AutotaskClientNotificationScopeError(
            "CLIENT_NOTIFICATION_COMPANY_ID_INVALID"
        ) from exc

    if ticket_company != AUTOTASK_CLIENT_NOTIFICATION_TEST_COMPANY_ID:
        raise AutotaskClientNotificationScopeError(
            "CLIENT_NOTIFICATION_TICKET_COMPANY_NOT_XYZ_TEST"
        )
    if contact_company != AUTOTASK_CLIENT_NOTIFICATION_TEST_COMPANY_ID:
        raise AutotaskClientNotificationScopeError(
            "CLIENT_NOTIFICATION_CONTACT_COMPANY_NOT_XYZ_TEST"
        )

    email = str(contact_email or "").strip().casefold()
    if not email or "@" not in email:
        raise AutotaskClientNotificationScopeError(
            "CLIENT_NOTIFICATION_CONTACT_EMAIL_REQUIRED"
        )

    requested = str(requested_recipient or "").strip().casefold()
    if requested and requested != email:
        raise AutotaskClientNotificationScopeError(
            "CLIENT_NOTIFICATION_RECIPIENT_MUST_MATCH_CONTACT"
        )

    return ClientNotificationTestScope(
        ticket_company_id=ticket_company,
        contact_company_id=contact_company,
        contact_email=email,
    )


__all__ = [
    "AUTOTASK_CLIENT_NOTIFICATION_PROFILE_ENV",
    "AUTOTASK_CLIENT_NOTIFICATION_TEST_PROFILE",
    "AUTOTASK_CLIENT_NOTIFICATION_TEST_COMPANY_ID",
    "AUTOTASK_CLIENT_NOTIFICATION_TEST_COMPANY_NAME",
    "AutotaskClientNotificationScopeError",
    "ClientNotificationTestScope",
    "SERVICE_TICKET_CLIENT_NOTIFICATION_CREATE",
    "client_notification_test_mode_enabled",
    "validate_client_notification_test_scope",
]
