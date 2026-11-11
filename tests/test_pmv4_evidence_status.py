"""Preprod-only acceptance of the existing J-Man status script replacement."""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"config/openclaw-specialists/reporting/status_report.py"
spec=importlib.util.spec_from_file_location("proposed_jman_status_report",SRC)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
NOW=datetime(2026,11,11,12,0,tzinfo=timezone.utc)


class EvidenceFirstTests(unittest.TestCase):
    def test_missing_record_not_called_complete(self):
        with tempfile.TemporaryDirectory() as temp:
            report=module.build_report(Path(temp)/"TASKS.md",when=NOW)
            self.assertIn("Overall Status: UNKNOWN",report)
            self.assertIn("Whole-Task Completion: Unknown",report)
            self.assertNotIn("Overall Status: COMPLETE",report)

    def test_stated_complete_without_proof_is_not_a_completed_outcome(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"TASKS.md"
            p.write_text("## PMv4.x — objective\n- Status: COMPLETE\n- Whole PMv4 program completion: estimated 100%\n")
            report=module.build_report(p,when=NOW)
            self.assertIn("UNVERIFIED COMPLETION CLAIM",report)
            self.assertIn("100% (J-Man task-record estimate;",report)
            self.assertIn("not operational proof",report)
            self.assertNotIn("Overall Status: COMPLETE",report)

    def test_nonproven_source_work_is_not_labeled_operational(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"TASKS.md"
            p.write_text("## PMv4.x — owner source-only engineering\n"
                         "- Current status: READ-ONLY DISCOVERY COMPLETE; PMv4 IMPLEMENTATION/RELEASE NOT VERIFIED.\n"
                         "- Whole PMv4 program completion: estimated 10%.\n")
            report=module.build_report(p,when=NOW)
            self.assertIn("Overall Status: IN PROGRESS / OPERATIONAL ACCEPTANCE UNVERIFIED",report)
            self.assertIn("Whole-Task Completion: 10% (J-Man task-record estimate;",report)
            for field in ["Verified:", "Problems/Blockers:", "Next Action:", "Needed From Me:"]:
                self.assertIn(field,report)

    def test_routine_scheduled_send_is_suppressed_regardless_of_target(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"TASKS.md"
            p.write_text("## PMv4.x\n- Status: in progress\n")
            old=module.os.environ.pop("JMAN_TEAMS_TARGET",None)
            try:
                rc=module.main(["--send","--task-file",str(p)])
                self.assertEqual(rc,0)
            finally:
                if old is not None:module.os.environ["JMAN_TEAMS_TARGET"]=old

    def test_trusted_native_event_hook_integrates_existing_reporter(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"TASKS.md"
            p.write_text("# J-Man Objective Register\n")
            old=module.os.environ.get("JMAN_TEAMS_TARGET")
            module.os.environ["JMAN_TEAMS_TARGET"]="user:bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
            try:
                ev={
                  "event_id":"PMv4:source:milestone-1",
                  "objective_id":"PMv4.11112026.1",
                  "kind":"milestone_verified",
                  "material":True,
                  "headline":"PMv4 source milestone",
                  "summary":"Reviewed tests passed; production not deployed",
                  "stage":"tested",
                  "evidence_ref":"git SHA reviewed and CI",
                  "next_action":"Continue to live runtime acceptance",
                  "owner_action":"Nothing",
                  "whole_percent":20,
                }
                sender=Mock(return_value="teams-verified-1")
                verifier=Mock(return_value=True)
                first=module.send_meaningful_event(ev,trusted_evidence_check=verifier,
                     sender=sender,task_file=p)
                second=module.send_meaningful_event(ev,trusted_evidence_check=verifier,
                     sender=sender,task_file=p)
                self.assertEqual(first,"SENT_WITH_PROVIDER_RECEIPT")
                self.assertEqual(second,"ALREADY_HANDLED")
                sender.assert_called_once()
                self.assertEqual(verifier.call_count,2)
            finally:
                if old is None:module.os.environ.pop("JMAN_TEAMS_TARGET",None)
                else:module.os.environ["JMAN_TEAMS_TARGET"]=old

    def test_blocked_status_is_not_buried_beneath_positive_news(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"TASKS.md"
            p.write_text("## PMv4.x\n- Status: BLOCKED by missing approval\n"
                         "- Needed From Owner: exact action review\n")
            report=module.build_report(p,when=NOW)
            self.assertIn("Overall Status: BLOCKED / DEGRADED",report)
            self.assertIn("Needed From Me: Action indicated in the task record",report)
            self.assertNotIn("Overall Status: IN PROGRESS",report)

    def test_later_objective_status_takes_precedence_over_stale_prior_status(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"TASKS.md"
            p.write_text("## PMv4.x — early\n- Status: COMPLETE\n"
                         "- Whole PMv4 program completion: estimated 100%\n"
                         "## unrelated\ntext\n"
                         "## PMv4.x — latest\n- Status: in progress\n"
                         "- Whole PMv4 program completion: estimated 25%\n")
            report=module.build_report(p,when=NOW)
            self.assertIn("Overall Status: IN PROGRESS",report)
            self.assertIn("25% (J-Man task-record estimate;",report)
            self.assertNotIn("UNVERIFIED COMPLETION CLAIM",report)

    def test_missing_percentage_not_fabricated(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"TASKS.md"
            p.write_text("## PMv4.x\n- Status: implemented\n")
            report=module.build_report(p,when=NOW)
            self.assertIn("Whole-Task Completion: Unknown",report)


if __name__=="__main__":
    unittest.main()
