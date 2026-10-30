"""Preproduction acceptance tests: governed patch approval reminder only.

No real Datto, Autotask, Microsoft, or Teams credentials/network are used.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from jason_runtime.autonomy_worker_runtime import SQLiteOperationalWorkStore
from jason_runtime.vulscan_patch_approval_aging import PatchApprovalObservation
from jason_runtime.vulscan_patch_approval_notification import (
    CanonicalPatchTeamsNotifier, MicrosoftKBMetadata, prepare_patch_notifications,
    verified_microsoft_kb_url,
)
from jason_runtime.vulscan_patch_approval_outbox import (
    drain_patch_approval_notifications,
)


RELEASE = date(2026, 10, 1)
NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)


def obs(*, age=16, policy="policy-a", company="client-a", device="pc-1", **changes):
    arguments = dict(
        kb="KB5123456", release_date=RELEASE,
        observed_date=RELEASE + timedelta(days=age),
        policy_id=policy, client_id=company, device_id=device,
        approval_state="NOT_APPROVED", source_verified=True,
    )
    arguments.update(changes)
    return PatchApprovalObservation(**arguments)


def meta(**changes):
    arguments = dict(
        kb="KB5123456", release_date=RELEASE,
        title="2026-10 Cumulative Update for Windows",
        summary="Addresses Windows security and reliability issues.",
        url="https://support.microsoft.com/help/5123456",
        source_checked_at=NOW - timedelta(hours=1),
        source_verified=True, known_issues="A documented installation issue is under review.",
    )
    arguments.update(changes)
    return MicrosoftKBMetadata(**arguments)


def plan(items, *, metadata=None):
    items = tuple(items)
    evaluation_time = datetime.combine(
        items[0].observed_date, datetime.min.time(), timezone.utc
    ) + timedelta(hours=12)
    return prepare_patch_notifications(
        items,
        {"KB5123456": metadata or meta(
            source_checked_at=evaluation_time - timedelta(hours=1))},
        now=evaluation_time,
    )


def test_15_day_grace_and_day16_day21():
    assert plan([obs(age=15)]) == ()
    first = plan([obs(age=16)])[0]
    assert first.stage == "day16_notice"
    assert "Microsoft KB: https://support.microsoft.com/help/5123456" in first.text
    assert "Addresses Windows security" in first.text
    assert "documented installation issue" in first.text
    followup = plan([obs(age=21)])[0]
    assert followup.stage == "day21_escalation"
    assert first.idempotency_key != followup.idempotency_key


def test_one_kb_message_across_policies_clients_devices_and_duplicate_tickets():
    notices = plan([
        obs(policy="workstations", company="client-a", device="pc1"),
        obs(policy="workstations", company="client-a", device="pc1"),
        obs(policy="servers", company="client-b", device="srv1"),
    ])
    assert len(notices) == 1
    assert notices[0].affected_clients == 2
    assert notices[0].affected_devices == 2
    assert notices[0].policy_ids == ("servers", "workstations")
    other = plan([obs(device="pc9")])
    assert other[0].idempotency_key == notices[0].idempotency_key


def test_urgent_review_is_review_only_and_no_approval_action():
    notice = plan([obs(age=1, actively_exploited=True, exploitation_verified=True)])[0]
    assert notice.stage == "urgent_review"
    assert plan([obs(age=1, actively_exploited=True)]) == ()
    assert "does not approve or install" in notice.text


@pytest.mark.parametrize("state", ["APPROVED", "INSTALLED"])
def test_approved_patches_are_silent(state):
    assert plan([obs(approval_state=state)]) == ()


def test_deferred_or_superseded_patches_are_silent():
    assert plan([obs(intentional_deferral=True)]) == ()
    assert plan([obs(superseded=True)]) == ()


def test_missing_conflicting_or_unverified_source_fails_closed():
    assert plan([obs(release_date=None)]) == ()
    assert plan([obs(), obs(release_date=date(2026, 9, 30))]) == ()
    assert plan([obs()], metadata=meta(source_verified=False)) == ()
    assert plan([obs()], metadata=meta(release_date=date(2026, 9, 30))) == ()
    assert plan([obs()], metadata=meta(source_checked_at=NOW - timedelta(days=8))) == ()


def test_official_kb_url_validation_rejects_spoofed_and_unrelated_links():
    assert verified_microsoft_kb_url(
        "KB5123456", "https://support.microsoft.com/help/5123456")
    for url in (
        "http://support.microsoft.com/help/5123456",
        "https://support.microsoft.com.evil.example/help/5123456",
        "https://support.microsoft.com/help/1234567",
        "https://support.microsoft.com@malicious.example/help/5123456",
        "https://example.org/help/5123456",
    ):
        assert not verified_microsoft_kb_url("KB5123456", url)


def test_unverified_article_link_is_not_rendered_as_verified():
    message = plan([obs()], metadata=meta(
        url="https://example.org/5123456"))[0].text
    assert "Official KB article not verified" in message
    assert "https://example.org" not in message


def test_canonical_sender_uses_governed_teams_request_not_raw_provider():
    sender = Mock()
    sender.send.return_value = SimpleNamespace(
        message_id="teams-provider-123", message_id_synthetic=False,
        delivery_state="provider_accepted")
    adapter = CanonicalPatchTeamsNotifier(
        communication_service=sender, owner_identity_id="person-entra-verified")
    result = adapter.send_prepared(plan([obs()])[0])
    request = sender.send.call_args.args[0]
    assert request.workflow == "vulscan_patch_approval_aging"
    assert request.recipient_identity_id == "person-entra-verified"
    assert request.client_id is None
    assert request.approval_id is None
    assert request.kind == "notification"
    assert result["delivery_state"] == "provider_accepted"


def test_existing_outbox_single_event_at_most_once_and_no_ticket_note(tmp_path):
    store = SQLiteOperationalWorkStore(tmp_path / "operation.sqlite3")
    notice = plan([obs()])[0]
    key = store.queue_patch_approval_notification(notification=notice, now=NOW)
    assert store.queue_patch_approval_notification(notification=notice, now=NOW) == key
    assert store.due_teams_notifications(now=NOW) == ()
    assert len(store.due_patch_approval_notifications(now=NOW)) == 1
    notifier = SimpleNamespace(send_prepared=Mock(return_value={
        "message_id": "provider-123", "message_id_synthetic": False}))
    assert drain_patch_approval_notifications(
        store=store, notifier=notifier, verify_current=lambda _: True, now=NOW) == 1
    notifier.send_prepared.assert_called_once()
    assert drain_patch_approval_notifications(
        store=store, notifier=notifier, verify_current=lambda _: True, now=NOW) == 0
    row = store._connection.execute(
        "SELECT state,attempts,message_id FROM autonomy_teams_notification_outbox"
    ).fetchone()
    assert tuple(row) == ("unverified", 1, "provider-123")
    # A patch-level event must never masquerade as ticket 0 notes.
    assert store._connection.execute(
        "SELECT count(*) FROM autonomy_ticket_note_state").fetchone()[0] == 0


def test_authoritative_change_prevents_stale_delivery(tmp_path):
    store = SQLiteOperationalWorkStore(tmp_path / "operation.sqlite3")
    store.queue_patch_approval_notification(notification=plan([obs()])[0], now=NOW)
    notifier = SimpleNamespace(send_prepared=Mock())
    assert drain_patch_approval_notifications(
        store=store, notifier=notifier, verify_current=lambda _: False, now=NOW) == 0
    notifier.send_prepared.assert_not_called()
    assert store._connection.execute(
        "SELECT state FROM autonomy_teams_notification_outbox").fetchone()[0] == "expired"


def test_missing_current_evidence_cannot_send(tmp_path):
    store = SQLiteOperationalWorkStore(tmp_path / "operation.sqlite3")
    store.queue_patch_approval_notification(notification=plan([obs()])[0], now=NOW)
    notifier = SimpleNamespace(send_prepared=Mock())
    assert drain_patch_approval_notifications(
        store=store, notifier=notifier, verify_current=None, now=NOW) == 0
    notifier.send_prepared.assert_not_called()


def test_ambiguous_teams_transport_failure_never_automatically_resends(tmp_path):
    store = SQLiteOperationalWorkStore(tmp_path / "operation.sqlite3")
    store.queue_patch_approval_notification(notification=plan([obs()])[0], now=NOW)
    notifier = SimpleNamespace(send_prepared=Mock(side_effect=TimeoutError("unknown")))
    assert drain_patch_approval_notifications(
        store=store, notifier=notifier, verify_current=lambda _: True, now=NOW) == 1
    assert drain_patch_approval_notifications(
        store=store, notifier=notifier, verify_current=lambda _: True, now=NOW) == 0
    notifier.send_prepared.assert_called_once()
    assert store._connection.execute(
        "SELECT state FROM autonomy_teams_notification_outbox").fetchone()[0] == "unverified"


def test_old_unsent_alert_expires_without_notification_flood(tmp_path):
    store = SQLiteOperationalWorkStore(tmp_path / "operation.sqlite3")
    store.queue_patch_approval_notification(
        notification=plan([obs()])[0], now=NOW - timedelta(days=2))
    notifier = SimpleNamespace(send_prepared=Mock())
    assert drain_patch_approval_notifications(
        store=store, notifier=notifier, verify_current=lambda _: True, now=NOW) == 0
    notifier.send_prepared.assert_not_called()
    assert store._connection.execute(
        "SELECT state FROM autonomy_teams_notification_outbox").fetchone()[0] == "expired"
