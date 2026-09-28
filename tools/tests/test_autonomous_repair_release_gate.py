import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "autonomous_repair_release_gate.py"
SPEC = importlib.util.spec_from_file_location("autonomous_repair_release_gate", MODULE_PATH)
gate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = gate
SPEC.loader.exec_module(gate)


def policy():
    return {
        "enabled": True,
        "automatic_authorization_enabled": True,
        "automatic_production_execution_enabled": False,
        "required_support_prefix": "SUPPORT-",
        "production_evidence_max_age_minutes": 30,
        "max_changed_files": 25,
        "max_changed_lines": 800,
        "required_checks": ["a", "b"],
        "required_metadata": {
            "release_class": "autonomous-repair-candidate",
            "new_capability": "no",
            "security_impact": "none",
            "new_authority_or_permission": "no",
            "provider_api_contract_change": "no",
            "schema_or_migration": "no",
            "new_dependency": "no",
            "infrastructure_or_topology_change": "no",
            "client_scope_expansion": "no",
            "disruptive_operational_behavior": "no",
        },
        "required_nonempty_metadata": [
            "support_item",
            "previously_approved_behavior",
            "regression_test",
            "post_deploy_verification",
        ],
        "denied_path_prefixes": [".github/workflows/", "infrastructure/"],
        "denied_path_fragments": ["/secrets/"],
        "denied_exact_paths": ["CONTRIBUTING.md"],
        "denied_path_terms": ["security", "authorization", "policy"],
        "denied_filenames": ["requirements.txt", "Dockerfile"],
        "test_path_prefixes": ["tools/tests/"],
        "test_path_fragments": ["/tests/"],
    }


BODY = """## Autonomous repair release

- Release class: autonomous-repair-candidate
- Support item: SUPPORT-OPS-023
- Previously approved behavior: Existing orchestration audit writes complete without false SQLite lock failures.
- New capability: no
- Security impact: none
- New authority or permission: no
- Provider/API contract change: no
- Schema or migration: no
- New dependency: no
- Infrastructure or topology change: no
- Client scope expansion: no
- Disruptive operational behavior: no
- Regression test: implementation/orchestrator/tests/test_event_store_locking.py
- Post-deploy verification: Run a full autonomous scan and verify no audit-lock-induced failures.
"""


def pr(body=BODY):
    return {
        "number": 123,
        "merged_at": "2026-09-28T14:00:00Z",
        "merge_commit_sha": "merge123",
        "body": body,
        "head": {"sha": "head123"},
    }


def files():
    return [
        {
            "filename": "implementation/orchestrator/event_store.py",
            "additions": 20,
            "deletions": 4,
        },
        {
            "filename": "implementation/orchestrator/tests/test_event_store_locking.py",
            "additions": 45,
            "deletions": 0,
        },
    ]


def checks():
    return [
        {"id": 1, "name": "a", "status": "completed", "conclusion": "success"},
        {"id": 2, "name": "b", "status": "completed", "conclusion": "success"},
    ]


def production(observed_at="2026-09-28T13:50:00+00:00"):
    return {
        "production": {
            "status": "aligned_and_healthy",
            "observed_at": observed_at,
            "revision": "known-good",
        }
    }


class AutonomousRepairReleaseGateTests(unittest.TestCase):
    def test_metadata_parser_normalizes_labels(self):
        metadata = gate.parse_metadata(BODY)
        self.assertEqual(metadata["release_class"], "autonomous-repair-candidate")
        self.assertEqual(metadata["support_item"], "SUPPORT-OPS-023")
        self.assertEqual(metadata["security_impact"], "none")

    def test_eligible_repair_needs_no_human_approval_but_waits_for_runner(self):
        original = gate.datetime
        try:
            class FixedDateTime(datetime):
                @classmethod
                def now(cls, tz=None):
                    return cls(2026, 9, 28, 14, 0, tzinfo=timezone.utc)

            gate.datetime = FixedDateTime
            result = gate.classify(
                pr=pr(),
                files=files(),
                check_runs=checks(),
                support_items={
                    "SUPPORT-OPS-023": {
                        "id": "SUPPORT-OPS-023",
                        "priority": "P1",
                        "status": "Open",
                        "title": "SQLite locking",
                    }
                },
                production_state=production(),
                policy=policy(),
                main_sha="main456",
                merge_is_on_main=True,
            )
        finally:
            gate.datetime = original

        self.assertTrue(result["source_repair_eligible"])
        self.assertFalse(result["human_approval_required"])
        self.assertFalse(result["execution_ready"])
        self.assertEqual(result["classification"], "autonomous_repair_authorized_blocked")
        self.assertTrue(
            any("deployment capability" in reason for reason in result["execution_reasons"])
        )

    def test_security_sensitive_path_forces_human_approval(self):
        changed = files() + [
            {
                "filename": "implementation/kernel/security/policy.py",
                "additions": 3,
                "deletions": 1,
            }
        ]
        result = gate.classify(
            pr=pr(),
            files=changed,
            check_runs=checks(),
            support_items={
                "SUPPORT-OPS-023": {
                    "id": "SUPPORT-OPS-023",
                    "priority": "P1",
                    "status": "Open",
                    "title": "SQLite locking",
                }
            },
            production_state=production(),
            policy=policy(),
            main_sha="main456",
            merge_is_on_main=True,
        )
        self.assertFalse(result["source_repair_eligible"])
        self.assertTrue(result["human_approval_required"])
        self.assertEqual(result["classification"], "approval_required")

    def test_new_capability_declaration_forces_human_approval(self):
        body = BODY.replace("- New capability: no", "- New capability: yes")
        result = gate.classify(
            pr=pr(body),
            files=files(),
            check_runs=checks(),
            support_items={
                "SUPPORT-OPS-023": {
                    "id": "SUPPORT-OPS-023",
                    "priority": "P1",
                    "status": "Open",
                    "title": "SQLite locking",
                }
            },
            production_state=production(),
            policy=policy(),
            main_sha="main456",
            merge_is_on_main=True,
        )
        self.assertTrue(result["human_approval_required"])

    def test_missing_regression_test_forces_human_approval(self):
        changed = [files()[0]]
        result = gate.classify(
            pr=pr(),
            files=changed,
            check_runs=checks(),
            support_items={
                "SUPPORT-OPS-023": {
                    "id": "SUPPORT-OPS-023",
                    "priority": "P1",
                    "status": "Open",
                    "title": "SQLite locking",
                }
            },
            production_state=production(),
            policy=policy(),
            main_sha="main456",
            merge_is_on_main=True,
        )
        self.assertTrue(result["human_approval_required"])
        self.assertTrue(any("regression test" in reason for reason in result["source_reasons"]))

    def test_stale_production_evidence_blocks_execution_not_repair_class(self):
        original = gate.datetime
        try:
            class FixedDateTime(datetime):
                @classmethod
                def now(cls, tz=None):
                    return cls(2026, 9, 28, 15, 0, tzinfo=timezone.utc)

            gate.datetime = FixedDateTime
            result = gate.classify(
                pr=pr(),
                files=files(),
                check_runs=checks(),
                support_items={
                    "SUPPORT-OPS-023": {
                        "id": "SUPPORT-OPS-023",
                        "priority": "P1",
                        "status": "Open",
                        "title": "SQLite locking",
                    }
                },
                production_state=production("2026-09-28T13:00:00+00:00"),
                policy=policy(),
                main_sha="main456",
                merge_is_on_main=True,
            )
        finally:
            gate.datetime = original

        self.assertTrue(result["source_repair_eligible"])
        self.assertFalse(result["human_approval_required"])
        self.assertFalse(result["execution_ready"])
        self.assertTrue(any("stale" in reason for reason in result["execution_reasons"]))

    def test_comment_marker_is_stable(self):
        result = {
            "classification": "autonomous_repair_authorized_blocked",
            "source_repair_eligible": True,
            "human_approval_required": False,
            "execution_ready": False,
            "support_item": "SUPPORT-OPS-023",
            "merge_sha": "abc",
            "rollback_sha": "def",
            "source_reasons": [],
            "execution_reasons": ["runner unavailable"],
        }
        comment = gate.render_comment(result)
        self.assertTrue(comment.startswith(gate.COMMENT_MARKER))


if __name__ == "__main__":
    unittest.main()
