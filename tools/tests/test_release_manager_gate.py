import importlib.util
import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "release_manager_gate.py"
SPEC = importlib.util.spec_from_file_location("release_manager_gate", MODULE_PATH)
gate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)

POLICY_PATH = Path(__file__).resolve().parents[2] / "config" / "release-manager-policy.json"
SHA_A = "a" * 40
SHA_B = "b" * 40


class ReleaseManagerGateTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        self.support = [
            {"id": "SUPPORT-OPS-001", "priority": "P1", "status": "Open", "title": "Broken"},
            {"id": "SUPPORT-OPS-002", "priority": "P2", "status": "Open", "title": "Degraded"},
        ]
        self.todos = [
            {"id": "TODO-OPS-001", "priority": "P1", "status": "Planned", "title": "Feature"}
        ]

    def evaluate(self, record, target):
        return gate.evaluate_transition(
            record,
            target,
            self.policy,
            support_items=self.support,
            todos=self.todos,
        )

    def test_support_work_preempts_new_todo_when_repair_slot_available(self):
        plan = gate.work_priority_plan(
            self.support,
            self.todos,
            active_support_ids=["SUPPORT-OPS-001"],
            max_active_support_repairs=2,
        )
        self.assertFalse(plan["todo_start_allowed"])
        self.assertEqual(plan["support_to_start"], ["SUPPORT-OPS-002"])

    def test_blocked_support_does_not_starve_feature_release(self):
        result = self.evaluate(
            {
                "state": "requested",
                "change_class": "feature",
                "active_support_repairs": [],
                "blocked_support_repairs": [
                    "SUPPORT-OPS-001",
                    "SUPPORT-OPS-002",
                ],
            },
            "development",
        )
        self.assertTrue(result["allowed"])

    def test_actionable_support_still_preempts_feature_release(self):
        result = self.evaluate(
            {
                "state": "requested",
                "change_class": "feature",
                "active_support_repairs": [],
                "blocked_support_repairs": ["SUPPORT-OPS-001"],
            },
            "development",
        )
        self.assertFalse(result["allowed"])
        self.assertTrue(any("Support-first scheduling" in item for item in result["reasons"]))

    def test_release_blocker_can_start_while_support_work_remains(self):
        result = self.evaluate(
            {"state": "requested", "change_class": "release_blocker"},
            "development",
        )
        self.assertTrue(result["allowed"])

    def test_state_skipping_fails_closed(self):
        result = self.evaluate(
            {"state": "development", "change_class": "support"},
            "release_candidate",
        )
        self.assertFalse(result["allowed"])

    def test_preprod_requires_isolation_and_mutation_disable(self):
        result = self.evaluate(
            {
                "state": "preproduction",
                "release_candidate": {
                    "candidate_sha": SHA_A,
                    "artifact_digest": "sha256:image",
                    "immutable": True,
                },
                "preproduction": {
                    "deployed_sha": SHA_A,
                    "artifact_digest": "sha256:image",
                    "acceptance_passed": True,
                    "failure_path_tests_passed": True,
                    "rollback_readiness_passed": True,
                    "writable_state_isolated": False,
                    "provider_mutations_disabled": True,
                },
            },
            "preprod_verified",
        )
        self.assertFalse(result["allowed"])
        self.assertTrue(any("writable state" in item for item in result["reasons"]))

    def test_production_eligible_requires_support_clearance_and_same_artifact(self):
        result = self.evaluate(
            {
                "state": "preprod_verified",
                "release_candidate": {
                    "candidate_sha": SHA_A,
                    "artifact_digest": "sha256:image",
                    "immutable": True,
                },
                "preproduction": {
                    "deployed_sha": SHA_A,
                    "artifact_digest": "sha256:image",
                    "acceptance_passed": True,
                },
                "support_impact": {
                    "checked": True,
                    "blocking_items": ["SUPPORT-OPS-099"],
                },
            },
            "production_eligible",
        )
        self.assertFalse(result["allowed"])
        self.assertTrue(any("SUPPORT-OPS-099" in item for item in result["reasons"]))

    def test_protected_core_requires_owner_approval_bound_to_candidate(self):
        base = {
            "state": "production_eligible",
            "rollback_sha": SHA_B,
            "changed_files": ["tools/release_manager_host_runner.py"],
            "release_candidate": {
                "candidate_sha": SHA_A,
                "artifact_digest": "sha256:image",
                "immutable": True,
            },
        }
        denied = self.evaluate(base, "production")
        self.assertFalse(denied["allowed"])
        approved = deepcopy(base)
        approved["owner_approval"] = {
            "approved": True,
            "candidate_sha": SHA_A,
        }
        accepted = self.evaluate(approved, "production")
        self.assertTrue(accepted["allowed"])
        self.assertTrue(accepted["protected_core"])

    def test_normal_release_can_promote_without_owner_override(self):
        result = self.evaluate(
            {
                "state": "production_eligible",
                "rollback_sha": SHA_B,
                "changed_files": ["docs/operations/example.md"],
                "release_candidate": {
                    "candidate_sha": SHA_A,
                    "artifact_digest": "sha256:image",
                    "immutable": True,
                },
            },
            "production",
        )
        self.assertTrue(result["allowed"])
        self.assertFalse(result["protected_core"])

    def test_production_verification_requires_exact_preprod_artifact(self):
        result = self.evaluate(
            {
                "state": "production",
                "release_candidate": {
                    "candidate_sha": SHA_A,
                    "artifact_digest": "sha256:image-a",
                    "immutable": True,
                },
                "production": {
                    "live_sha": SHA_A,
                    "artifact_digest": "sha256:image-b",
                    "health_passed": True,
                    "deployment_script_passed": True,
                },
            },
            "production_verified",
        )
        self.assertFalse(result["allowed"])
        self.assertTrue(any("artifact" in item for item in result["reasons"]))


if __name__ == "__main__":
    unittest.main()
