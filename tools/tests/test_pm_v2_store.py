from pathlib import Path
import tempfile
import unittest

from pm_v2.store import PMV2Store


class PMV2StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = PMV2Store(Path(self.tmp.name) / "state.sqlite3")
        self.store.initialize()

    def tearDown(self):
        self.tmp.cleanup()

    def _add(self, assignment_id="a1", scope="sha256:1"):
        return self.store.upsert_assignment(
            assignment_id=assignment_id, source="test", source_ref=assignment_id,
            title="one", priority=1, work_type="development", runnable=True,
            scope_hash=scope, metadata={},
        )

    def test_claim_is_atomic_and_single_owner(self):
        self._add()
        first = self.store.claim_next(instance_id="one", lease_seconds=300)
        second = self.store.claim_next(instance_id="two", lease_seconds=300)
        self.assertEqual(first.assignment_id, "a1")
        self.assertIsNone(second)

    def test_scope_change_blocks_inflight_work(self):
        self._add()
        self.store.claim_next(instance_id="one", lease_seconds=300)
        changed = self.store.upsert_assignment(
            assignment_id="a1", source="test", source_ref="a1", title="changed",
            priority=1, work_type="development", runnable=True,
            scope_hash="sha256:2", metadata={},
        )
        self.assertEqual(changed.state, "blocked")
        self.assertFalse(changed.runnable)
        self.assertEqual(changed.blocked_reason, "source_scope_changed")

    def test_idempotency_suppresses_duplicate_start(self):
        self._add()
        self.assertTrue(self.store.begin_idempotent_action(
            key="k", assignment_id="a1", action="deploy"))
        self.assertFalse(self.store.begin_idempotent_action(
            key="k", assignment_id="a1", action="deploy"))

    def test_complete_requires_one_hundred_percent(self):
        self._add()
        with self.assertRaises(ValueError):
            self.store.update_state(
                "a1", state="complete", runnable=False, completion_percent=90)
