from __future__ import annotations

from jason_runtime.vulscan_client_policy import (
    GROMELSKI_COMPANY_ID,
    VulScanDispositionPolicy,
    VulScanPolicyOverride,
    resolve_vulscan_policy,
)


def test_gromelski_now_uses_standard_vulscan_disposition():
    policy = resolve_vulscan_policy(client_id=GROMELSKI_COMPANY_ID)
    assert policy.terminal_status == "Complete"
    assert policy.primary_contact_id is None
    assert policy.client_notification_required is False
    assert policy.client_notification_template_id is None
    assert policy.continue_patch_monitoring is False


def test_non_gromelski_uses_global_default():
    policy = resolve_vulscan_policy(client_id=507)
    assert policy.terminal_status == "Complete"
    assert policy.primary_contact_id is None
    assert policy.client_notification_required is False


def test_more_specific_scope_overrides_client_policy():
    client = VulScanDispositionPolicy(
        terminal_status="Close Pending",
        primary_contact_id=10,
        client_notification_required=True,
    )
    site = VulScanDispositionPolicy(
        terminal_status="Complete",
        primary_contact_id=20,
        client_notification_required=False,
    )
    device = VulScanDispositionPolicy(
        terminal_status="Human Review",
        primary_contact_id=30,
        client_notification_required=False,
    )
    user = VulScanDispositionPolicy(
        terminal_status="Waiting Client",
        primary_contact_id=40,
        client_notification_required=True,
    )
    ticket = VulScanDispositionPolicy(
        terminal_status="Close Pending",
        primary_contact_id=50,
        client_notification_required=True,
    )
    overrides = (
        VulScanPolicyOverride("client", "597", client),
        VulScanPolicyOverride("site", "425", site),
        VulScanPolicyOverride("device", "device-1", device),
        VulScanPolicyOverride("user", "30684489", user),
        VulScanPolicyOverride("ticket", "141183", ticket),
    )

    assert resolve_vulscan_policy(
        client_id=597,
        site_id=425,
        device_id="device-1",
        user_id=30684489,
        ticket_id=141183,
        overrides=overrides,
    ) == ticket

    assert resolve_vulscan_policy(
        client_id=597,
        site_id=425,
        device_id="device-1",
        user_id=30684489,
        ticket_id=999,
        overrides=overrides,
    ) == user

    assert resolve_vulscan_policy(
        client_id=597,
        site_id=425,
        device_id="device-1",
        user_id=999,
        ticket_id=999,
        overrides=overrides,
    ) == device

    assert resolve_vulscan_policy(
        client_id=597,
        site_id=425,
        device_id="other",
        user_id=999,
        ticket_id=999,
        overrides=overrides,
    ) == site
