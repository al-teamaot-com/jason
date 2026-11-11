"""Source-only PMv4 Teams event threshold, evidence, and at-most-once tests."""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "config/openclaw-specialists/reporting/meaningful_events.py"
spec = importlib.util.spec_from_file_location("pmv4_meaningful_events", SRC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

NOW = datetime(2026, 11, 11, 16, 0, tzinfo=timezone.utc)


def event(kind="milestone_verified", **changes):
    item = {
        "event_id": "PMv4:release-lane:source-accepted-20261111",
        "objective_id": "PMv4.11112026.1",
        "kind": kind,
        "material": True,
        "headline": "Shadow-release source accepted",
        "summary": "Independent tests passed on the reviewed source; no deployment",
        "stage": "tested",
        "evidence_ref": "PR #2429 / SHA 752b55c21672",
        "next_action": "Reconcile source and perform operational acceptance",
        "owner_action": "Nothing",
        "whole_percent": 20,
    }
    if kind == "material_problem":
        item.update(stage="blocked", summary="Verified repeated worker stall", event_id="PMv4:worker:stall-01")
    if kind == "owner_decision_required":
        item.update(stage="blocked", summary="Release is prepared but requires exact Owner authority",
                    event_id="PMv4:release:decision-01",
                    owner_action="Approve release SHA and rollback after authentication")
    item.update(changes)
    return item


class PMv4MeaningfulTeamsEvents(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tasks = Path(self.tmp.name) / "TASKS.md"
        self.tasks.write_text("# J-Man Objective Register\n## PMv4.11112026.1\n")
        self.sender = Mock(return_value="msteams-message-123")
        self.evidence = Mock(return_value=True)

    def send(self, item):
        return mod.publish_once(item, task_register=self.tasks,
                                independent_evidence_check=self.evidence,
                                sender=self.sender, at=NOW)

    def test_material_verified_source_milestone_sent_once_not_complete(self):
        output = self.send(event())
        self.assertEqual(output, "SENT_WITH_PROVIDER_RECEIPT")
        self.assertEqual(self.sender.call_count, 1)
        message = self.sender.call_args.args[0]
        self.assertIn("Verified milestone", message)
        self.assertIn("Status: tested", message)
        self.assertIn("overall acceptance not implied", message)
        self.assertIn("Needed from Owner: Nothing", message)
        self.assertNotIn("PMv4 completed", message)
        self.assertEqual(self.send(event()), "ALREADY_HANDLED")
        self.assertEqual(self.sender.call_count, 1)
        self.assertIn("PMV4_TEAMS_EVENT_RECEIPT", self.tasks.read_text())

    def test_problem_is_sent_with_evidence_and_no_owner_action(self):
        self.send(event("material_problem"))
        message = self.sender.call_args.args[0]
        self.assertIn("Material problem", message)
        self.assertIn("Status: blocked", message)
        self.assertIn("Needed from Owner: Nothing", message)

    def test_decision_requires_specific_action_and_plain_message(self):
        self.send(event("owner_decision_required"))
        msg = self.sender.call_args.args[0]
        self.assertIn("Owner decision required", msg)
        self.assertIn("Approve release SHA", msg)
        self.assertNotIn("Approve button", msg)

    def test_routine_events_are_suppressed_without_evidence_or_send(self):
        for kind in ["task_started", "test_passed", "activity", "progress", "daily_digest"]:
            self.assertEqual(self.send(event(kind)), "SUPPRESSED_ROUTINE_EVENT")
        self.assertEqual(self.evidence.call_count, 0)
        self.sender.assert_not_called()
        self.assertNotIn("PMV4_TEAMS_EVENT_RECEIPT", self.tasks.read_text())

    def test_nonmaterial_event_is_suppressed(self):
        self.assertEqual(self.send(event(material=False)), "SUPPRESSED_ROUTINE_EVENT")
        self.sender.assert_not_called()

    def test_unverified_claim_fails_closed(self):
        self.evidence.return_value = False
        with self.assertRaisesRegex(mod.EventRejected, "independent_evidence_unverified"):
            self.send(event())
        self.sender.assert_not_called()
        self.assertNotIn("PMV4_TEAMS_EVENT_RECEIPT", self.tasks.read_text())

    def test_disagreement_on_duplicate_id_is_rejected(self):
        self.send(event())
        with self.assertRaisesRegex(mod.EventRejected, "conflicting_duplicate_event"):
            self.send(event(summary="Different result and evidence"))
        self.assertEqual(self.sender.call_count, 1)

    def test_uncertain_delivery_is_not_resent(self):
        self.sender.side_effect = RuntimeError("unknown delivery")
        with self.assertRaisesRegex(RuntimeError, "unknown delivery"):
            self.send(event())
        self.sender.side_effect = None
        self.assertEqual(self.send(event()), "ALREADY_HANDLED")
        self.assertEqual(self.sender.call_count, 1)
        self.assertIn("delivery_unverified", self.tasks.read_text())

    def test_synthetic_receipt_never_claims_sent(self):
        self.sender.return_value = "accepted:test-not-real"
        with self.assertRaisesRegex(mod.EventRejected, "synthetic_receipt"):
            self.send(event())
        self.assertEqual(self.send(event()), "ALREADY_HANDLED")
        self.assertNotIn('"state":"sent"', self.tasks.read_text())

    def test_invalid_owner_actions_are_not_silently_accepted(self):
        with self.assertRaisesRegex(mod.EventRejected, "owner_action_invalid"):
            self.send(event("owner_decision_required", owner_action=""))
        self.sender.assert_not_called()
        with self.assertRaisesRegex(mod.EventRejected, "owner_action_only"):
            self.send(event(owner_action="approve all production"))
        self.sender.assert_not_called()

    def test_stages_must_fit_event_kind(self):
        for e in [event(stage="in_progress"),
                  event("material_problem", stage="deployed"),
                  event(stage="complete")]:
            with self.assertRaises(mod.EventRejected):
                self.send(e)
        self.sender.assert_not_called()

    def test_percent_is_nullable_but_never_fabricated(self):
        self.send(event(whole_percent=None))
        self.assertIn("Whole PMv4: not measured", self.sender.call_args.args[0])

    def test_missing_register_cannot_create_parallel_storage(self):
        self.tasks.unlink()
        with self.assertRaisesRegex(mod.EventRejected, "canonical_task_register_missing"):
            self.send(event())
        self.sender.assert_not_called()

    def test_existing_sender_reuses_msteams_channel_with_receipt(self):
        result = Mock(returncode=0, stdout=json.dumps({
            "payload": {"deliveryStatus": "sent"}, "messageId": "1234567890"
        }))
        runner = Mock(return_value=result)
        mid = mod.existing_teams_sender("Test notification", target="user:bee80bdc-ffb0-4c50-b453-c09d4d411f5f",
                                        runner=runner)
        self.assertEqual(mid, "1234567890")
        argv = runner.call_args.args[0]
        self.assertEqual(argv[:5], ["openclaw", "message", "send", "--channel", "msteams"])
        self.assertIn("--message", argv)
        self.assertNotIn("approve", argv)

    def test_numeric_provider_message_reference_is_accepted(self):
        runner = Mock(return_value=Mock(returncode=0, stdout=json.dumps({
            "payload": {"deliveryStatus": "sent"}, "messageId": 1794227790542,
        })))
        self.assertEqual(mod.existing_teams_sender(
            "text", target="user:bee80bdc-ffb0-4c50-b453-c09d4d411f5f",
            runner=runner), "1794227790542")

    def test_existing_register_without_final_newline_keeps_receipt_readable(self):
        self.tasks.write_text("# J-Man Objective Register")
        self.assertEqual(self.send(event()), "SENT_WITH_PROVIDER_RECEIPT")
        self.assertEqual(self.send(event()), "ALREADY_HANDLED")
        self.assertIn(chr(10) + "- PMV4_TEAMS_EVENT_RECEIPT:", self.tasks.read_text())
        self.assertEqual(self.sender.call_count, 1)

    def test_existing_sender_rejects_missing_route_and_indeterminate_receipt(self):
        runner = Mock(return_value=Mock(returncode=0, stdout=json.dumps({"payload": {"deliveryStatus": "accepted"}})))
        with self.assertRaisesRegex(mod.EventRejected, "route_unverified"):
            mod.existing_teams_sender("text", target="al_admin@teamaot.com", runner=runner)
        with self.assertRaisesRegex(mod.EventRejected, "route_unverified"):
            mod.existing_teams_sender("text", target="user:00000000-0000-0000-0000-000000000001", runner=runner)
        with self.assertRaisesRegex(mod.EventRejected, "delivery_unverified"):
            mod.existing_teams_sender("text", target="user:bee80bdc-ffb0-4c50-b453-c09d4d411f5f",
                                      runner=runner)
        self.assertEqual(runner.call_count, 1)


if __name__ == "__main__":
    unittest.main()
