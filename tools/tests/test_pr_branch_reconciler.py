import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "pr_branch_reconciler.py"
SPEC = importlib.util.spec_from_file_location("pr_branch_reconciler", MODULE_PATH)
reconciler = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = reconciler
SPEC.loader.exec_module(reconciler)


def pr_fixture(**overrides):
    pr = {
        "number": 10,
        "state": "open",
        "draft": False,
        "author_association": "OWNER",
        "body": "Integration automation: enabled",
        "base": {"ref": "main"},
        "head": {
            "ref": "feature/example",
            "sha": "abc",
            "repo": {"full_name": "al-teamaot-com/jason"},
        },
    }
    pr.update(overrides)
    return pr


class PrBranchReconcilerTests(unittest.TestCase):
    def test_automation_marker_is_explicit(self):
        self.assertTrue(
            reconciler.automation_enabled(
                "## Integration\n- Integration automation: enabled\n"
            )
        )
        self.assertFalse(
            reconciler.automation_enabled(
                "## Integration\n- Integration automation: disabled\n"
            )
        )

    def test_eligible_pr_requires_trusted_same_repo_non_draft(self):
        self.assertTrue(
            reconciler.eligible_pr(
                pr_fixture(),
                repository="al-teamaot-com/jason",
                base_branch="main",
            )
        )
        self.assertFalse(
            reconciler.eligible_pr(
                pr_fixture(draft=True),
                repository="al-teamaot-com/jason",
                base_branch="main",
            )
        )
        external = pr_fixture()
        external["head"] = dict(external["head"])
        external["head"]["repo"] = {"full_name": "someone/fork"}
        self.assertFalse(
            reconciler.eligible_pr(
                external,
                repository="al-teamaot-com/jason",
                base_branch="main",
            )
        )
        untrusted = pr_fixture(author_association="CONTRIBUTOR")
        self.assertFalse(
            reconciler.eligible_pr(
                untrusted,
                repository="al-teamaot-com/jason",
                base_branch="main",
            )
        )

    def test_latest_check_run_wins(self):
        runs = [
            {"id": 1, "name": "runtime-service", "status": "completed", "conclusion": "failure"},
            {"id": 2, "name": "runtime-service", "status": "completed", "conclusion": "success"},
        ]
        latest = reconciler.latest_checks(runs)
        self.assertEqual(latest["runtime-service"]["id"], 2)

    def test_required_checks_fail_closed(self):
        required = ("runtime-service", "repository-hygiene")
        state, detail = reconciler.required_check_state(
            required,
            [
                {
                    "id": 1,
                    "name": "runtime-service",
                    "status": "completed",
                    "conclusion": "success",
                }
            ],
        )
        self.assertEqual(state, "missing")
        self.assertEqual(detail, ["repository-hygiene"])

        state, detail = reconciler.required_check_state(
            required,
            [
                {
                    "id": 1,
                    "name": "runtime-service",
                    "status": "completed",
                    "conclusion": "success",
                },
                {
                    "id": 2,
                    "name": "repository-hygiene",
                    "status": "completed",
                    "conclusion": "failure",
                },
            ],
        )
        self.assertEqual(state, "failed")
        self.assertEqual(detail, ["repository-hygiene"])

    def test_all_required_checks_pass(self):
        state, detail = reconciler.required_check_state(
            ("a", "b"),
            [
                {"id": 1, "name": "a", "status": "completed", "conclusion": "success"},
                {"id": 2, "name": "b", "status": "completed", "conclusion": "success"},
            ],
        )
        self.assertEqual(state, "passed")
        self.assertEqual(detail, [])


if __name__ == "__main__":
    unittest.main()
