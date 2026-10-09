from __future__ import annotations

import json
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
