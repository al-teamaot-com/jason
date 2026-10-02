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

    def test_support_work_comes_before_todo_when_capacity_available(self):
        plan = gate.work_priority_plan(
            self.support,
            self.todos,
            active_support_ids=["SUPPORT-OPS-001"],
            max_active_support_repairs=2,
        )
        self.assertFalse(plan["todo_start_allowed"])
        self.assertEqual(plan["support_to_start"], ["SUPPORT-OPS-002"])

    def test_todo_can_continue_when_support_capacity_is_full(self):
        plan = gate.work_priority_plan(
            self.support,
            self.todos,
            active_support_ids=["SUPPORT-OPS-001", "SUPPORT-OPS-002"],
            max_active_support_repairs=2,
        )
        self.assertTrue(plan["todo_start_allowed"])

    def test_new_todo_development_is_blocked_before_unused_support_capacity(self):
        result = gate.evaluate_transition(
            {
                "state": "requested",
                "change_class": "todo",
                "active_support_repairs": ["SUPPORT-OPS-001"],
            },
            "development",
            self.policy,
            support_items=self.support,
            todos=self.todos,
        )
        self.assertFalse(result["allowed"])
        self.assertTrue(any("Support-first" in reason for reason in result["reasons"]))

    def test_support_item_can_enter_development(self):
        result = gate.evaluate_transition(
            {
                "state": "requested",
                "change_class": "support",
                "support_item": "SUPPORT-OPS-001",
            },
            "development",
            self.policy,
            support_items=self.support,
            todos=self.todos,
        )
        self.assertTrue(result["allowed"])

    def test_state_skipping_fails_closed(self):
        result = gate.evaluate_transition(
            {"state": "development", "change_class": "support"},
            "release_candidate",
            self.policy,
            support_items=self.support,
            todos=self.todos,
        )
        self.assertFalse(result["allowed"])

    def test_release_candidate_requires_exact_dev_verified_sha(self):
        result = gate.evaluate_transition(
            {
                "state": "dev_verified",
                "development": {
                    "source_sha": "aaa",
                    "tests_passed": True,
                    "required_checks_passed": True,
                },
                "release_candidate": {
                    "candidate_sha": "bbb",
                    "artifact_digest": "sha256:1",
                    "immutable": True,
                },
            },
            "release_candidate",
            self.policy,
            support_items=self.support,
            todos=self.todos,
        )
        self.assertFalse(result["allowed"])
        self.assertIn(
            "release candidate SHA does not equal dev-verified source SHA",
            result["reasons"],
        )

    def test_preproduction_fails_closed_until_environment_is_configured(self):
        result = gate.evaluate_transition(
            {
                "state": "release_candidate",
                "release_candidate": {
                    "candidate_sha": "aaa",
                    "artifact_digest": "sha256:1",
                    "immutable": True,
                },
            },
            "preproduction",
            self.policy,
            support_items=self.support,
            todos=self.todos,
        )
        self.assertFalse(result["allowed"])
        self.assertTrue(any("not configured" in reason for reason in result["reasons"]))

    def test_preprod_verification_requires_same_candidate_and_artifact(self):
        policy = deepcopy(self.policy)
        policy["preproduction"]["configured"] = True
        result = gate.evaluate_transition(
            {
                "state": "preproduction",
                "release_candidate": {
                    "candidate_sha": "aaa",
                    "artifact_digest": "sha256:1",
                    "immutable": True,
                },
                "preproduction": {
                    "deployed_sha": "bbb",
                    "artifact_digest": "sha256:2",
                    "acceptance_passed": True,
                    "failure_path_tests_passed": True,
                    "rollback_readiness_passed": True,
                },
            },
            "preprod_verified",
            policy,
            support_items=self.support,
            todos=self.todos,
        )
        self.assertFalse(result["allowed"])
        self.assertTrue(any("deployed SHA differs" in reason for reason in result["reasons"]))
        self.assertTrue(any("artifact digest differs" in reason for reason in result["reasons"]))

    def test_production_eligibility_requires_support_impact_clearance(self):
        policy = deepcopy(self.policy)
        policy["preproduction"]["configured"] = True
        result = gate.evaluate_transition(
            {
                "state": "preprod_verified",
                "release_candidate": {
                    "candidate_sha": "aaa",
                    "artifact_digest": "sha256:1",
                    "immutable": True,
                },
                "preproduction": {
                    "deployed_sha": "aaa",
                    "artifact_digest": "sha256:1",
                    "acceptance_passed": True,
                    "failure_path_tests_passed": True,
                    "rollback_readiness_passed": True,
                },
                "support_impact": {
                    "checked": True,
                    "blocking_items": ["SUPPORT-OPS-099"],
                },
            },
            "production_eligible",
            policy,
            support_items=self.support,
            todos=self.todos,
        )
        self.assertFalse(result["allowed"])
        self.assertTrue(any("SUPPORT-OPS-099" in reason for reason in result["reasons"]))

    def test_production_transition_is_impossible_in_nonproduction_pilot(self):
        result = gate.evaluate_transition(
            {"state": "production_eligible"},
            "production",
            self.policy,
            support_items=self.support,
            todos=self.todos,
        )
        self.assertFalse(result["allowed"])
        self.assertFalse(result["production_execution_permitted"])


if __name__ == "__main__":
    unittest.main()
