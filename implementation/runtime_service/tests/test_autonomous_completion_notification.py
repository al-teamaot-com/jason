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

    def test_self_heal_escalation_render_is_bounded_and_actionable(self):
        event, text = _render(
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
