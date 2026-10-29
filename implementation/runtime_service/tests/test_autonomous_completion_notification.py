from __future__ import annotations

import json
import tempfile
import unittest
import pytest
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from jason_runtime.autonomous_completion_notification import (
    AutonomousCompletionTeamsInvoker,
    AutonomousDeploymentCompletionNotificationMaintenance,
    AutonomousWorkLifecycleNotificationMaintenance,
    ReleaseManagerOwnerNotificationMaintenance,
    SelfHealEscalationNotificationMaintenance,
    _render,
)


class BindingStore:
    def __init__(self, binding=None):
        self.binding = binding

    def find_active_by_jason_identity(self, *, jason_identity_id: str):
        if jason_identity_id != "person-al":
            raise AssertionError("recipient substitution attempted")
        return self.binding


class EntraOwnerBindingStore:
    """Use the actual runtime binding-store interface, not an invented identity."""
    def __init__(self, *bindings):
        self.bindings = bindings
        self.email_reads = []

    def find_active_by_jason_identity(self, *, jason_identity_id):
        assert jason_identity_id == "person-al"
        return None

    def find_active_by_email(self, *, email_address):
        self.email_reads.append(email_address)
        matches = [
            x for x in self.bindings
            if x.status == "active" and x.email_address.casefold() == email_address
        ]
        return matches[0] if len(matches) == 1 else None


class TestEntraOwnerBinding:
    @staticmethod
    def request():
        return SimpleNamespace(
            capability_name="communication.teams.autonomy.completion.send",
            principal_id="jason-autonomy-worker", permission_mode="execute",
            organization_id="aot", client_id=None,
            arguments={
                "event_type": "production_queue_completed",
                "work_id": "release-" + "a" * 16,
                "summary": "Production verified",
                "candidate_sha": "a" * 40,
            },
        )

    @staticmethod
    def owner(*, email="al@teamaot.com", client_id=None, status="active",
              object_id="aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"):
        return SimpleNamespace(
            status=status,
            email_address=email,
            client_id=client_id,
            jason_identity_id="person-entra-" + object_id.replace("-", "").lower(),
            microsoft_tenant_id="f7054323-d52b-4863-8c2f-1898f0b6077c",
            microsoft_object_id=object_id,
        )

    def prepare(self, store, tmp_path):
        token = tmp_path / "token"
        token.write_text("synthetic-not-sent")
        invoker = AutonomousCompletionTeamsInvoker(
            gateway_url="http://example.invalid", token_file=token, bindings=store,
        )
        request = self.request()
        resolution = SimpleNamespace(
            selected_provider_id="microsoft_teams_gateway_autonomy_completion"
        )
        return invoker.prepare_execution_plan(request=request, resolution=resolution)

    def test_current_enta_owner_binding_resolves_exact_recipient(self, tmp_path):
        store = EntraOwnerBindingStore(self.owner())
        plan = self.prepare(store, tmp_path).plan
        assert store.email_reads == ["al@teamaot.com"]
        assert plan.symbolic_resolutions["recipient_jason_identity"] == (
            "person-entra-aaaaaaaabbbb4ccc8dddeeeeeeeeeeee"
        )
        assert plan.symbolic_resolutions["recipient_owner_alias"] == "person-al"
        assert plan.resource_identifier == (
            "f7054323-d52b-4863-8c2f-1898f0b6077c:"
            "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
        )

    def test_owner_binding_absent_ambiguous_revoked_or_wrong_account_denied(self, tmp_path):
        cases = (
            (),
            (self.owner(status="revoked"),),
            (self.owner(email="someone-else@teamaot.com"),),
            (self.owner(client_id="a-customer"),),
            (self.owner(), self.owner(object_id="bbbbbbbb-bbbb-4ccc-8ddd-eeeeeeeeeeee")),
        )
        for idx, records in enumerate(cases):
            with pytest.raises(PermissionError):
                self.prepare(EntraOwnerBindingStore(*records), tmp_path)

    def test_owner_binding_wrong_jason_identity_denied(self, tmp_path):
        owner = self.owner()
        owner.jason_identity_id = "person-other"
        with pytest.raises(PermissionError):
            self.prepare(EntraOwnerBindingStore(owner), tmp_path)

    def test_email_recipient_override_denied_even_with_valid_owner(self, tmp_path):
        store = EntraOwnerBindingStore(self.owner())
        # Invalid extra recipient is always rejected by bounded event arguments.
        token = tmp_path / "token"
        token.write_text("synthetic-not-sent")
        invoker = AutonomousCompletionTeamsInvoker(
            gateway_url="http://example.invalid", token_file=token, bindings=store,
        )
        req = self.request()
        req.arguments["recipient"] = "different@example.com"
        with pytest.raises(ValueError):
            invoker.prepare_execution_plan(
                request=req,
                resolution=SimpleNamespace(
                    selected_provider_id="microsoft_teams_gateway_autonomy_completion",
                ),
            )


class Notifier:
    def __init__(self):
        self.calls = []

    def send(self, event_type: str, **kwargs):
        self.calls.append((event_type, kwargs))
        return {"message_id": "message-1"}


class AutonomousCompletionNotificationTests(unittest.TestCase):
    def test_render_rejects_arbitrary_event(self):
        with self.assertRaises(ValueError):
            _render({"event_type": "freeform", "resolution_summary": "hello"})

    def test_render_rejects_arbitrary_arguments(self):
        with self.assertRaises(ValueError):
            _render(
                {
                    "event_type": "support_item_resolved",
                    "support_item": "SUPPORT-OPS-023",
                    "resolution_summary": "fixed",
                    "recipient": "someone-else",
                }
            )

    def test_invoker_requires_person_al_active_binding(self):
        invoker = AutonomousCompletionTeamsInvoker(
            gateway_url="http://example.invalid",
            token_file=Path("/does/not/matter"),
            bindings=BindingStore(None),
        )
        request = SimpleNamespace(
            capability_name="communication.teams.autonomy.completion.send",
            principal_id="jason-autonomy-worker",
            permission_mode="execute",
            organization_id="aot",
            client_id=None,
            arguments={
                "event_type": "support_item_resolved",
                "support_item": "SUPPORT-OPS-023",
                "resolution_summary": "verified",
            },
        )
        resolution = SimpleNamespace(
            selected_provider_id="microsoft_teams_gateway_autonomy_completion"
        )
        with self.assertRaises(PermissionError):
            invoker.prepare_execution_plan(
                request=request,
                resolution=resolution,
            )

    def test_autonomous_card_notifier_reuses_shared_gateway_once(self):
        with tempfile.TemporaryDirectory() as td:
            token_path = Path(td) / "token"
            token_path.write_text("synthetic-token", encoding="utf-8")
            binding = SimpleNamespace(
                status="active", jason_identity_id="person-al",
                microsoft_tenant_id="f7054323-d52b-4863-8c2f-1898f0b6077c",
                microsoft_object_id="aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
            )
            invoker = AutonomousCompletionTeamsInvoker(
                gateway_url="http://gateway.internal:3979",
                token_file=token_path, bindings=BindingStore(binding),
            )
            request = SimpleNamespace(
                capability_name="communication.teams.autonomy.completion.send",
                principal_id="jason-autonomy-worker", permission_mode="execute",
                organization_id="aot", client_id=None,
                arguments={
                    "event_type": "work_started",
                    "work_id": "DEV-1440",
                    "work_title": "Teams universal approver",
                    "summary": "Safe nonexecuting test started",
                },
            )
            resolution = SimpleNamespace(
                selected_provider_id="microsoft_teams_gateway_autonomy_completion",
            )
            prepared = invoker.prepare_execution_plan(
                request=request, resolution=resolution,
            )
            receipt = {
                "message_id": "accepted:receipt-1",
                "message_id_synthetic": True,
                "delivery_evidence_type": "provider_call_completed_without_message_id",
            }
            with patch(
                "jason_runtime.autonomous_completion_notification.post_existing_teams_gateway",
                return_value=receipt,
            ) as send:
                result = invoker.invoke_execution_plan(
                    request=request, resolution=resolution, prepared=prepared,
                )
            send.assert_called_once()
            self.assertEqual(send.call_args.kwargs["payload"]["card"]["type"], "AdaptiveCard")
            self.assertTrue(result.output["message_id_synthetic"])
            self.assertEqual(
                result.output["delivery_state"], "provider_accepted_delivery_unverified",
            )

    def test_verified_deployment_notifies_once(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            results = root / "results"
            results.mkdir(parents=True)
            candidate = "a" * 40
            payload = {
                "state": "succeeded",
                "candidate_sha": candidate,
                "live_revision": candidate,
                "rollback_sha": "b" * 40,
                "support_item": "SUPPORT-OPS-023",
                "verification_passed": True,
                "rollback_performed": False,
            }
            (results / "request-1.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
            notifier = Notifier()
            maintenance = AutonomousDeploymentCompletionNotificationMaintenance(
                notifier=notifier,
                spool_root=root,
                interval_seconds=30,
                now=lambda: datetime(2026, 9, 28, 15, 0, tzinfo=timezone.utc),
            )
            self.assertTrue(maintenance.tick())
            self.assertEqual(len(notifier.calls), 1)
            self.assertEqual(notifier.calls[0][0], "deployment_completed")
            self.assertTrue((root / "notifications" / "request-1.json").exists())

            maintenance._next_due_at = None
            self.assertFalse(maintenance.tick())
            self.assertEqual(len(notifier.calls), 1)

    def test_work_started_render_is_concise_adaptive_card(self):
        event, text, card = _render(
            {
                "event_type": "work_started",
                "work_id": "TODO-COMM-004",
                "work_title": "Governed Teams interaction and owner operations",
                "summary": "Owner-approved autonomous engineering has started.",
            }
        )
        self.assertEqual(event, "work_started")
        self.assertIn("TODO-COMM-004", text)
        self.assertEqual(card["type"], "AdaptiveCard")
        self.assertEqual(card["body"][0]["color"], "Accent")
        self.assertNotIn("health_metric:", json.dumps(card))

    def test_ticket_status_updated_uses_readable_adaptive_card(self):
        event, text, card = _render({
            "event_type": "ticket_status_updated",
            "work_id": "T20261009.0006",
            "work_title": "Datto AV alert for AOT-50282",
            "summary": "Ticket: T20261009.0006 | Device: AOT-50282 | Status: On Hold",
        })
        self.assertEqual(event, "ticket_status_updated")
        self.assertIn("T20261009.0006", text)
        self.assertEqual(card["type"], "AdaptiveCard")
        self.assertEqual(card["body"][0]["color"], "Accent")
        self.assertIn("ticket updated", json.dumps(card).lower())

    def test_work_completed_render_is_green(self):
        event, text, card = _render(
            {
                "event_type": "work_completed",
                "work_id": "SUPPORT-OPS-100",
                "work_title": "Example repair",
                "summary": "Production acceptance and support closure are verified complete.",
            }
        )
        self.assertEqual(event, "work_completed")
        self.assertIn("completed", text.casefold())
        self.assertEqual(card["body"][0]["color"], "Good")

    def test_lifecycle_event_notifies_once_and_persists_message_id(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            events = root / "lifecycle-events"
            events.mkdir(parents=True)
            payload = {
                "event_type": "work_blocked",
                "work_id": "TODO-OPS-009",
                "work_title": "Human-review handoff to Help Desk I",
                "summary": "Controlled acceptance found a generic status mismatch.",
                "owner_action": "No action required; Jason is correcting source.",
            }
            (events / "abc.json").write_text(json.dumps(payload), encoding="utf-8")
            notifier = Notifier()
            maintenance = AutonomousWorkLifecycleNotificationMaintenance(
                notifier=notifier,
                spool_root=root,
                interval_seconds=15,
                now=lambda: datetime(2026, 10, 4, 13, 0, tzinfo=timezone.utc),
            )
            self.assertTrue(maintenance.tick())
            self.assertEqual(notifier.calls[0][0], "work_blocked")
            marker = root / "lifecycle-notifications" / "abc.json"
            self.assertTrue(marker.exists())
            self.assertEqual(json.loads(marker.read_text())["message_id"], "message-1")
            maintenance._next_due_at = None
            self.assertFalse(maintenance.tick())
            self.assertEqual(len(notifier.calls), 1)


    def test_release_queue_notifications_are_start_owner_action_complete_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            events = root / "owner-notification-events"
            events.mkdir(parents=True)
            candidate = "c" * 40
            base = {
                "release_id": "release-candidate",
                "candidate_sha": candidate,
                "description": "Add production queue owner notifications with recovery silence.",
            }
            for name, extra in (
                ("production_queue_entered", {}),
                (
                    "production_owner_action_required",
                    {"owner_action": "Approve protected-core production promotion."},
                ),
                ("production_queue_completed", {}),
            ):
                payload = dict(base, event_type=name, **extra)
                (events / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")
            # Recoverable/internal events are intentionally ignored even if present.
            (events / "recoverable.json").write_text(
                json.dumps(dict(base, event_type="recoverable_error")), encoding="utf-8"
            )
            notifier = Notifier()
            maintenance = ReleaseManagerOwnerNotificationMaintenance(
                notifier=notifier,
                state_root=root,
                interval_seconds=15,
                now=lambda: datetime(2026, 10, 8, 17, 30, tzinfo=timezone.utc),
            )
            self.assertTrue(maintenance.tick())
            self.assertEqual(
                {call[0] for call in notifier.calls},
                {
                    "production_owner_action_required",
                    "production_queue_completed",
                    "production_queue_entered",
                },
            )
            self.assertEqual(len(notifier.calls), 3)
            maintenance._next_due_at = None
            self.assertFalse(maintenance.tick())
            self.assertEqual(len(notifier.calls), 3)

    def test_release_failure_does_not_starve_next_notice_and_remains_retryable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            events = root / "owner-notification-events"
            events.mkdir(parents=True)
            for name in ("a", "b"):
                (events / f"{name}.json").write_text(json.dumps({
                    "event_type": "production_queue_entered",
                    "release_id": name,
                    "candidate_sha": "a" * 40,
                    "description": "controlled production lifecycle test",
                }), encoding="utf-8")
            class FailFirst(Notifier):
                def send(self, event_type, **arguments):
                    if arguments["work_id"] == "a":
                        raise RuntimeError("simulated delivery failure")
                    return super().send(event_type, **arguments)
            maintenance = ReleaseManagerOwnerNotificationMaintenance(
                notifier=FailFirst(), state_root=root, interval_seconds=15,
                now=lambda: datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc),
            )
            self.assertTrue(maintenance.tick())
            self.assertTrue((root / "owner-notification-failed" / "a.json").exists())
            self.assertFalse((root / "owner-notification-delivered" / "a.json").exists())
            self.assertTrue((root / "owner-notification-delivered" / "b.json").exists())

    def test_accepted_receipt_is_not_recorded_as_delivered(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            events = root / "owner-notification-events"
            events.mkdir()
            (events / "release.json").write_text(json.dumps({
                "event_type": "production_queue_entered",
                "release_id": "release-receipt",
                "candidate_sha": "a" * 40,
                "description": "controlled uncertain Teams delivery",
            }), encoding="utf-8")

            class SyntheticNotifier(Notifier):
                def send(self, event_type, **arguments):
                    self.calls.append((event_type, arguments))
                    return {"message_id": "accepted:synthetic", "message_id_synthetic": True}

            notifier = SyntheticNotifier()
            maintenance = ReleaseManagerOwnerNotificationMaintenance(
                notifier=notifier, state_root=root, interval_seconds=15,
                now=lambda: datetime(2026, 10, 9, 18, 30, tzinfo=timezone.utc),
            )
            self.assertFalse(maintenance.tick())
            self.assertFalse((root / "owner-notification-delivered" / "release.json").exists())
            marker = root / "owner-notification-unverified" / "release.json"
            self.assertTrue(marker.exists())
            self.assertEqual(json.loads(marker.read_text())["status"], "provider_accepted_delivery_unverified")
            maintenance._next_due_at = None
            self.assertFalse(maintenance.tick())
            self.assertEqual(len(notifier.calls), 1)

    def test_release_queue_render_includes_description_and_candidate(self):
        candidate = "d" * 40
        event, text, card = _render(
            {
                "event_type": "production_queue_entered",
                "work_id": "release-deadbeef",
                "summary": "Deploy fixed owner lifecycle notifications.",
                "candidate_sha": candidate,
            }
        )
        self.assertEqual(event, "production_queue_entered")
        self.assertIn("Deploy fixed owner lifecycle notifications", text)
        self.assertIn(candidate[:12], text)
        self.assertEqual(card["body"][0]["color"], "Accent")

    def test_self_heal_escalation_render_is_bounded_and_actionable(self):
        event, text, card = _render(
            {
                "event_type": "self_heal_escalation",
                "degraded_function": "jason_mcp_status",
                "evidence_summary": "status surface failed twice",
                "attempt_summary": "restarted jason-mcp-pilot and rechecked",
                "owner_action": "review missing external dependency",
            }
        )
        self.assertEqual(event, "self_heal_escalation")
        self.assertIn("owner action", text.casefold())
        self.assertIn("jason_mcp_status", text)
        self.assertIn("status surface failed twice", text)
        self.assertIn("restarted jason-mcp-pilot and rechecked", text)
        self.assertEqual(card["type"], "AdaptiveCard")
        self.assertEqual(card["body"][0]["color"], "Attention")
        self.assertEqual(card["body"][2]["facts"][0]["title"], "Degraded function")
        self.assertEqual(card["body"][2]["facts"][3]["title"], "Owner action")

    def test_self_heal_escalation_notifies_once(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            escalations = root / "escalations"
            escalations.mkdir(parents=True)
            fingerprint = "abc123"
            (escalations / f"{fingerprint}.json").write_text(
                json.dumps(
                    {
                        "state": "owner_action_required",
                        "fingerprint": fingerprint,
                        "degraded_function": "mcp status",
                        "evidence_summary": "functional probe failed",
                        "attempt_summary": "two bounded restarts failed",
                        "owner_action": "review provider dependency",
                    }
                ),
                encoding="utf-8",
            )
            notifier = Notifier()
            maintenance = SelfHealEscalationNotificationMaintenance(
                notifier=notifier,
                spool_root=root,
                interval_seconds=30,
                now=lambda: datetime(2026, 9, 30, 7, 0, tzinfo=timezone.utc),
            )
            self.assertTrue(maintenance.tick())
            self.assertEqual(notifier.calls[0][0], "self_heal_escalation")
            self.assertTrue((root / "notifications" / f"{fingerprint}.json").exists())
            maintenance._next_due_at = None
            self.assertFalse(maintenance.tick())
            self.assertEqual(len(notifier.calls), 1)

    def test_failed_or_unverified_deployment_does_not_notify(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            results = root / "results"
            results.mkdir(parents=True)
            candidate = "a" * 40
            (results / "request-1.json").write_text(
                json.dumps(
                    {
                        "state": "failed",
                        "candidate_sha": candidate,
                        "live_revision": candidate,
                        "support_item": "SUPPORT-OPS-023",
                        "verification_passed": False,
                    }
                ),
                encoding="utf-8",
            )
            notifier = Notifier()
            maintenance = AutonomousDeploymentCompletionNotificationMaintenance(
                notifier=notifier,
                spool_root=root,
                interval_seconds=30,
                now=lambda: datetime(2026, 9, 28, 15, 0, tzinfo=timezone.utc),
            )
            self.assertFalse(maintenance.tick())
            self.assertEqual(notifier.calls, [])


    def test_self_heal_synthetic_gateway_receipt_is_unverified_not_notified(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            escalations = root / "escalations"
            escalations.mkdir()
            (escalations / "abc123.json").write_text(json.dumps({
                "state": "owner_action_required", "fingerprint": "abc123",
                "degraded_function": "jason-approver",
                "evidence_summary": "benign UAT card not confirmed",
                "attempt_summary": "one bounded test",
                "owner_action": "review safe test request",
            }), encoding="utf-8")

            class SyntheticNotifier(Notifier):
                def send(self, event_type, **kwargs):
                    self.calls.append((event_type, kwargs))
                    return {"message_id": "accepted:card-test", "message_id_synthetic": True}

            notifier = SyntheticNotifier()
            maintenance = SelfHealEscalationNotificationMaintenance(
                notifier=notifier, spool_root=root, interval_seconds=30,
                now=lambda: datetime(2026, 10, 22, 10, 0, tzinfo=timezone.utc),
            )
            self.assertFalse(maintenance.tick())
            self.assertFalse((root / "notifications" / "abc123.json").exists())
            marker = root / "notifications-unverified" / "abc123.json"
            self.assertTrue(marker.exists())
            self.assertEqual(json.loads(marker.read_text())["status"],
                             "provider_accepted_delivery_unverified")
            maintenance._next_due_at = None
            self.assertFalse(maintenance.tick())
            self.assertEqual(len(notifier.calls), 1)

    def test_deployment_synthetic_receipt_does_not_claim_owner_notified(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            results = root / "results"
            results.mkdir()
            sha = "c" * 40
            (results / "repair.json").write_text(json.dumps({
                "state": "succeeded", "verification_passed": True,
                "candidate_sha": sha, "live_revision": sha,
                "support_item": "SUPPORT-OPS-023",
            }), encoding="utf-8")

            class SyntheticNotifier(Notifier):
                def send(self, event_type, **kwargs):
                    self.calls.append((event_type, kwargs))
                    return {"message_id": "accepted:repair-test", "message_id_synthetic": True}

            notifier = SyntheticNotifier()
            maintenance = AutonomousDeploymentCompletionNotificationMaintenance(
                notifier=notifier, spool_root=root, interval_seconds=30,
                now=lambda: datetime(2026, 10, 22, 10, 0, tzinfo=timezone.utc),
            )
            self.assertFalse(maintenance.tick())
            self.assertFalse((root / "notifications" / "repair.json").exists())
            marker = root / "notifications-unverified" / "repair.json"
            self.assertEqual(json.loads(marker.read_text())["status"],
                             "provider_accepted_delivery_unverified")
            maintenance._next_due_at = None
            self.assertFalse(maintenance.tick())
            self.assertEqual(len(notifier.calls), 1)

    def test_lifecycle_synthetic_receipt_does_not_claim_owner_notified(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            events = root / "lifecycle-events"
            events.mkdir()
            (events / "work.json").write_text(json.dumps({
                "event_type": "work_started",
                "work_id": "DEV-1440", "work_title": "Teams universal approvals",
                "summary": "Benign callback test started",
            }), encoding="utf-8")

            class SyntheticNotifier(Notifier):
                def send(self, event_type, **kwargs):
                    self.calls.append((event_type, kwargs))
                    return {"message_id": "accepted:work-test", "message_id_synthetic": True}

            notifier = SyntheticNotifier()
            maintenance = AutonomousWorkLifecycleNotificationMaintenance(
                notifier=notifier, spool_root=root, interval_seconds=30,
                now=lambda: datetime(2026, 10, 22, 10, 0, tzinfo=timezone.utc),
            )
            self.assertFalse(maintenance.tick())
            self.assertFalse((root / "lifecycle-notifications" / "work.json").exists())
            marker = root / "lifecycle-notifications-unverified" / "work.json"
            self.assertEqual(json.loads(marker.read_text())["status"],
                             "provider_accepted_delivery_unverified")
            maintenance._next_due_at = None
            self.assertFalse(maintenance.tick())
            self.assertEqual(len(notifier.calls), 1)



if __name__ == "__main__":
    unittest.main()


def test_owner_notifications_expire_historical_backlog_without_sending(tmp_path):
    events = tmp_path / "owner-notification-events"
    events.mkdir()
    for name, created in (
        ("ancient-release", "2026-09-20T11:00:00+00:00"),
        ("recent-release", "2026-10-29T15:55:00+00:00"),
    ):
        (events / f"{name}.json").write_text(json.dumps({
            "event_type": "production_queue_entered",
            "release_id": name,
            "candidate_sha": "a" * 40,
            "description": "Controlled production release",
            "created_at": created,
        }))
    notifier = Notifier()
    maint = ReleaseManagerOwnerNotificationMaintenance(
        notifier=notifier, state_root=tmp_path,
        now=lambda: datetime(2026, 10, 29, 16, 5, tzinfo=timezone.utc),
    )
    assert maint.tick() is True
    assert [kw["work_id"] for _, kw in notifier.calls] == ["recent-release"]
    expired = tmp_path / "owner-notification-expired" / "ancient-release.json"
    assert json.loads(expired.read_text())["state"] == "expired_without_delivery"
    assert not (tmp_path / "owner-notification-delivered" / "ancient-release.json").exists()


def test_owner_notification_failure_has_durable_backoff_and_eventual_success(tmp_path):
    events = tmp_path / "owner-notification-events"
    events.mkdir()
    (events / "release.json").write_text(json.dumps({
        "event_type": "production_queue_completed",
        "release_id": "release-recent",
        "candidate_sha": "b" * 40,
        "description": "Production certified",
        "created_at": "2026-10-29T16:00:00+00:00",
    }))
    class RecoveringNotifier(Notifier):
        def send(self, event_type, **kwargs):
            self.calls.append((event_type, kwargs))
            if len(self.calls) == 1:
                raise RuntimeError("transient Teams transport failure")
            return {"message_id": "provider-receipt-1", "message_id_synthetic": False}
    now = [datetime(2026, 10, 29, 16, 2, tzinfo=timezone.utc)]
    notifier = RecoveringNotifier()
    maint = ReleaseManagerOwnerNotificationMaintenance(
        notifier=notifier, state_root=tmp_path, interval_seconds=15,
        now=lambda: now[0],
    )
    assert maint.tick() is False
    failed = tmp_path / "owner-notification-failed" / "release.json"
    error = json.loads(failed.read_text())
    assert error["attempts"] == 1
    assert error["error_type"] == "RuntimeError"
    assert error["next_due_at"] == "2026-10-29T16:07:00+00:00"
    assert len(notifier.calls) == 1
    now[0] = datetime(2026, 10, 29, 16, 3, tzinfo=timezone.utc)
    assert maint.tick() is False
    assert len(notifier.calls) == 1
    now[0] = datetime(2026, 10, 29, 16, 8, tzinfo=timezone.utc)
    assert maint.tick() is True
    assert len(notifier.calls) == 2
    assert json.loads((tmp_path / "owner-notification-delivered" / "release.json").read_text())["message_id"] == "provider-receipt-1"
    now[0] = datetime(2026, 10, 29, 16, 9, tzinfo=timezone.utc)
    assert maint.tick() is False
    assert len(notifier.calls) == 2
