from pathlib import Path
import json
import tempfile
import unittest

from pm_v2.release_sync import reconcile_release_bridge, verify_release_evidence
from pm_v2.store import PMV2Store


SHA = "a" * 40
RID = "release-" + SHA[:16]


def release_record():
    return {
        "release_id": RID,
        "state": "closed",
        "release_candidate": {"candidate_sha": SHA},
        "owner_approval": {
            "approved": True,
            "candidate_sha": SHA,
            "source": "authenticated_mobile_teams_owner:relapproval-test",
        },
        "ccc_post_mutation_gate": {
            "status": "PASS",
            "run_id": "ccc-1",
            "candidate_sha": SHA,
        },
        "production": {
            "live_sha": SHA,
            "verified_at": "2026-10-31T10:00:00+00:00",
            "health_passed": True,
            "functional_smoke_tests_passed": True,
            "desired_state_converged": True,
            "production_manifest_complete": True,
            "documentation_reconciliation": "pass",
            "control_board_publication": "pass",
        },
    }


def delivered(root: Path, event: str):
    folder = root / "owner-notification-delivered"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{RID}-{event}.json").write_text(json.dumps({
        "event_type": event,
        "release_id": RID,
        "message_id": "msg-" + event,
        "delivery_state": "provider_message_reference_recorded",
    }))


class PMV2ReleaseSyncTests(unittest.TestCase):
    def _state(self, root: Path):
        state_root = root / "release"
        (state_root / "records").mkdir(parents=True)
        (state_root / "records" / f"{RID}.json").write_text(
            json.dumps(release_record()), encoding="utf-8"
        )
        delivered(state_root, "production_push_started")
        delivered(state_root, "production_push_result")
        return state_root

    def test_verified_release_requires_teams_approval_start_and_result(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_root = self._state(root)
            checks = verify_release_evidence(
                state_root=state_root, release_id=RID, expected_sha=SHA
            )
            self.assertTrue(all(x["status"] == "pass" for x in checks.values()))
            (state_root / "owner-notification-delivered" /
             f"{RID}-production_push_started.json").unlink()
            checks = verify_release_evidence(
                state_root=state_root, release_id=RID, expected_sha=SHA
            )
            self.assertEqual(checks["teams_start_delivery"]["status"], "pending")

    def test_bridge_complete_is_not_pm_complete_without_full_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_root = self._state(root)
            spool = root / "spool"
            spool.mkdir()
            store = PMV2Store(root / "state.sqlite3")
            store.initialize()
            store.upsert_assignment(
                assignment_id="roadmap:TODO-OPS-001",
                source="roadmap", source_ref="TODO-OPS-001",
                title="test", priority=1, work_type="development",
                runnable=True, scope_hash="sha256:scope", metadata={},
            )
            (spool / "todo-release-state.json").write_text(json.dumps({
                "items": {
                    "TODO-OPS-001": {
                        "phase": "complete",
                        "release_id": RID,
                        "merge_sha": SHA,
                    }
                }
            }))
            result = reconcile_release_bridge(
                store=store, spool=spool, state_root=state_root
            )
            self.assertEqual(result["completed"], 1)
            self.assertEqual(store.list_assignments()[0].completion_percent, 100)

            # Remove one required real-world proof and reconcile again on a fresh store.
            (state_root / "owner-notification-delivered" /
             f"{RID}-production_push_result.json").unlink()
            store2 = PMV2Store(root / "state2.sqlite3")
            store2.initialize()
            store2.upsert_assignment(
                assignment_id="roadmap:TODO-OPS-001",
                source="roadmap", source_ref="TODO-OPS-001",
                title="test", priority=1, work_type="development",
                runnable=True, scope_hash="sha256:scope", metadata={},
            )
            reconcile_release_bridge(
                store=store2, spool=spool, state_root=state_root
            )
            row = store2.list_assignments()[0]
            self.assertEqual(row.state, "validation_pending")
            self.assertEqual(row.completion_percent, 95)
