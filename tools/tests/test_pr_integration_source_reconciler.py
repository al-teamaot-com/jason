import importlib.util
import os
import sys
import unittest
from pathlib import Path


os.environ["JASON_REPOSITORY"] = "example/jason"

MODULE_PATH = Path(__file__).resolve().parents[1] / "pr_integration_source_reconciler.py"
SPEC = importlib.util.spec_from_file_location(
    "pr_integration_source_reconciler",
    MODULE_PATH,
)
host = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = host
SPEC.loader.exec_module(host)


def policy():
    return host.IntegrationPolicy(
        base_branch="main",
        required_checks=("runtime-service", "repository-hygiene"),
        additional_required_checks=("governed-security-regressions",),
        max_prs_per_run=3,
    )


def pr_fixture(**overrides):
    item = {
        "number": 12,
        "state": "open",
        "draft": False,
        "author_association": "OWNER",
        "body": "Integration automation: enabled",
        "mergeable": True,
        "mergeable_state": "clean",
        "base": {"ref": "main"},
        "head": {
            "ref": "feature/example",
            "sha": "head-sha",
            "repo": {"full_name": "example/jason"},
        },
    }
    item.update(overrides)
    return item


class HostIntegrationReconcilerTests(unittest.TestCase):
    def test_eligibility_is_explicit_trusted_same_repo(self):
        self.assertTrue(host.eligible_pr(pr_fixture(), policy()))
        self.assertFalse(
            host.eligible_pr(
                pr_fixture(body="Integration automation: disabled"),
                policy(),
            )
        )
        self.assertFalse(
            host.eligible_pr(
                pr_fixture(author_association="CONTRIBUTOR"),
                policy(),
            )
        )
        external = pr_fixture()
        external["head"] = dict(external["head"])
        external["head"]["repo"] = {"full_name": "someone/fork"}
        self.assertFalse(host.eligible_pr(external, policy()))

    def test_required_check_state_uses_branch_protection_view(self):
        original = host.pr_required_checks
        try:
            host.pr_required_checks = lambda number: [
                {"name": "runtime-service", "bucket": "pass"},
                {"name": "repository-hygiene", "bucket": "pass"},
            ]
            self.assertEqual(host.required_check_state(12), ("passed", ()))

            host.pr_required_checks = lambda number: [
                {"name": "runtime-service", "bucket": "pass"},
                {"name": "repository-hygiene", "bucket": "pending"},
            ]
            self.assertEqual(
                host.required_check_state(12),
                ("pending", ("repository-hygiene",)),
            )
        finally:
            host.pr_required_checks = original

    def test_stale_pr_updates_branch_and_does_not_merge_same_cycle(self):
        calls = []
        original_read = host.read_pr
        original_compare = host.compare_to_base
        original_update = host.native_update_branch
        original_merge = host.merge_pr
        try:
            host.read_pr = lambda number: pr_fixture()
            host.compare_to_base = lambda pr, policy: {"behind_by": 3}
            host.native_update_branch = lambda number: calls.append(("update", number))
            host.merge_pr = lambda number: calls.append(("merge", number))
            self.assertEqual(
                host.outcome_for_pr(pr_fixture(), policy()),
                "updated_to_main",
            )
            self.assertEqual(calls, [("update", 12)])
        finally:
            host.read_pr = original_read
            host.compare_to_base = original_compare
            host.native_update_branch = original_update
            host.merge_pr = original_merge

    def test_green_current_pr_merges(self):
        calls = []
        original_read = host.read_pr
        original_compare = host.compare_to_base
        original_required = host.required_check_state
        original_additional = host.additional_check_state
        original_merge = host.merge_pr
        try:
            host.read_pr = lambda number: pr_fixture()
            host.compare_to_base = lambda pr, policy: {"behind_by": 0}
            host.required_check_state = lambda number: ("passed", ())
            host.additional_check_state = lambda pr, policy: ("passed", ())
            host.merge_pr = lambda number: calls.append(number)
            self.assertEqual(
                host.outcome_for_pr(pr_fixture(), policy()),
                "merged",
            )
            self.assertEqual(calls, [12])
        finally:
            host.read_pr = original_read
            host.compare_to_base = original_compare
            host.required_check_state = original_required
            host.additional_check_state = original_additional
            host.merge_pr = original_merge

    def test_failed_required_check_never_merges(self):
        calls = []
        original_read = host.read_pr
        original_compare = host.compare_to_base
        original_required = host.required_check_state
        original_merge = host.merge_pr
        try:
            host.read_pr = lambda number: pr_fixture()
            host.compare_to_base = lambda pr, policy: {"behind_by": 0}
            host.required_check_state = lambda number: (
                "failed",
                ("repository-hygiene",),
            )
            host.merge_pr = lambda number: calls.append(number)
            outcome = host.outcome_for_pr(pr_fixture(), policy())
            self.assertEqual(
                outcome,
                "required_failed:repository-hygiene",
            )
            self.assertEqual(calls, [])
        finally:
            host.read_pr = original_read
            host.compare_to_base = original_compare
            host.required_check_state = original_required
            host.merge_pr = original_merge


if __name__ == "__main__":
    unittest.main()
