from pathlib import Path
import tempfile
import unittest

from pm_v2.improvements import reconcile_improvement_proposals
from pm_v2.store import PMV2Store


class PMV2ImprovementTests(unittest.TestCase):
    def test_repeated_failure_creates_proposal_only_not_authority(self):
        with tempfile.TemporaryDirectory() as td:
            store = PMV2Store(Path(td) / "state.sqlite3")
            store.initialize()
            store.upsert_assignment(
                assignment_id="a1", source="test", source_ref="1",
                title="failing", priority=1, work_type="development",
                runnable=True, scope_hash="sha256:1", metadata={},
            )
            store.claim_next(instance_id="x", lease_seconds=10)
            store.schedule_retry(
                "a1", completion_percent=0,
                reason="same_failure", delay_seconds=1,
            )
            # Simulate the second bounded failure attempt.
            row = store.get_assignment("a1")
            store.update_state(
                "a1", state="blocked", runnable=False,
                completion_percent=0, reason="same_failure",
            )
            with store.connect() as conn:
                conn.execute(
                    "UPDATE assignments SET attempt_count=2 WHERE assignment_id='a1'"
                )
            result = reconcile_improvement_proposals(
                store=store, minimum_recurrences=2
            )
            self.assertEqual(result["proposal_count"], 1)
            proposals = [
                row for row in store.list_assignments()
                if row.source == "self_improvement"
            ]
            self.assertEqual(len(proposals), 1)
            self.assertEqual(proposals[0].state, "proposal_only")
            self.assertFalse(proposals[0].runnable)
            self.assertEqual(
                proposals[0].metadata["authority"],
                "proposal_requires_owner_approved_todo",
            )

    def test_single_failure_does_not_create_proposal(self):
        with tempfile.TemporaryDirectory() as td:
            store = PMV2Store(Path(td) / "state.sqlite3")
            store.initialize()
            store.upsert_assignment(
                assignment_id="a1", source="test", source_ref="1",
                title="one failure", priority=1, work_type="development",
                runnable=False, scope_hash="sha256:1", metadata={},
                blocked_reason="one_failure",
            )
            self.assertEqual(
                reconcile_improvement_proposals(
                    store=store, minimum_recurrences=2
                )["proposal_count"],
                0,
            )
