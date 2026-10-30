"""VulScan V2 preproduction flow through Jason's real canonical Teams boundary.

The transport is mocked. No provider call, client message, or release occurs.
"""
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from communication.audience.engine import AudiencePolicyEngine
from jason_runtime.autonomy_worker_runtime import SQLiteOperationalWorkStore
from jason_runtime.teams_communication_service import (
    JasonTeamsCommunicationService, TeamsDeliveryReceipt,
)
from jason_runtime.vulscan_patch_approval_aging import PatchApprovalObservation
from jason_runtime.vulscan_patch_approval_notification import (
    CanonicalPatchTeamsNotifier, MicrosoftKBMetadata,
    prepare_patch_notifications,
)
from jason_runtime.vulscan_patch_approval_outbox import drain_patch_approval_notifications

NOW = datetime(2026, 10, 30, 16, tzinfo=timezone.utc)


def notice():
    observation = PatchApprovalObservation(
        kb="KB5123456", release_date=date(2026, 10, 13),
        observed_date=date(2026, 10, 30), policy_id="weekly",
        client_id="company-12", device_id="ci-10", approval_state="NOT_APPROVED",
        source_verified=True,
    )
    metadata = MicrosoftKBMetadata(
        kb="KB5123456", release_date=date(2026, 10, 13),
        title="Windows cumulative update",
        summary="Microsoft security and reliability fixes",
        url="https://support.microsoft.com/help/5123456",
        source_checked_at=NOW, source_verified=True,
        known_issues="One verified issue documented",
    )
    return prepare_patch_notifications((observation,), {"KB5123456": metadata}, now=NOW)[0]


def canonical_sender(*, allowed=True, identity_active=True):
    binding = SimpleNamespace(
        status="active",
        jason_identity_id="person-entra-verified",
        microsoft_tenant_id="f7054323-d52b-4863-8c2f-1898f0b6077c",
        microsoft_object_id="aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
    )
    fake_transport = SimpleNamespace(send=Mock(return_value=TeamsDeliveryReceipt(
        message_id="provider-123", conversation_id="conversation-xyz",
        recipient_identity_id="person-entra-verified",
        delivery_state="provider_accepted",
    )))
    service = JasonTeamsCommunicationService(
        transport=fake_transport,
        bindings=SimpleNamespace(find_active_by_jason_identity=lambda **kw: binding),
        identities=SimpleNamespace(get=lambda key: SimpleNamespace(
            identity_id=key, status="active" if identity_active else "revoked",
            organization_id="aot")),
        workflow_authority=SimpleNamespace(can_communicate=Mock(return_value=allowed)),
        approval_requests=SimpleNamespace(get=lambda _: None),
        audience=AudiencePolicyEngine(),
    )
    return CanonicalPatchTeamsNotifier(
        communication_service=service,
        owner_identity_id="person-entra-verified",
    ), fake_transport


def test_shared_teams_service_delivers_only_verified_mock_provider_receipt(tmp_path):
    store = SQLiteOperationalWorkStore(tmp_path / "shared.sqlite3")
    store.queue_patch_approval_notification(notification=notice(), now=NOW)
    sender, transport = canonical_sender()
    assert drain_patch_approval_notifications(
        store=store, notifier=sender, verify_current=lambda _: True, now=NOW) == 1
    transport.send.assert_called_once()
    assert "support.microsoft.com/help/5123456" in transport.send.call_args.kwargs["text"]
    row = store._connection.execute(
        "SELECT state,attempts,message_id FROM autonomy_teams_notification_outbox"
    ).fetchone()
    assert tuple(row) == ("unverified", 1, "provider-123")
    # The existing canonical sender reports provider acceptance only.
    assert drain_patch_approval_notifications(
        store=store, notifier=sender, verify_current=lambda _: True, now=NOW) == 0


def test_sender_requires_workflow_authority_and_valid_owner_identity(tmp_path):
    for granted, active in ((False, True), (True, False)):
        store = SQLiteOperationalWorkStore(tmp_path / f"shared-{granted}-{active}.sqlite3")
        store.queue_patch_approval_notification(notification=notice(), now=NOW)
        sender, transport = canonical_sender(allowed=granted, identity_active=active)
        assert drain_patch_approval_notifications(
            store=store, notifier=sender,
            verify_current=lambda _: True, now=NOW) == 1
        transport.send.assert_not_called()
        row = store._connection.execute(
            "SELECT state FROM autonomy_teams_notification_outbox"
        ).fetchone()
        assert row[0] == "unverified"
