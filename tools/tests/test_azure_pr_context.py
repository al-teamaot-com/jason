import unittest
from tools.azure_pr_context import resolve_pr_id


class TestAzurePrContext(unittest.TestCase):
    def test_normal_pr(self):
        self.assertEqual(resolve_pr_id("18", "refs/pull/18/merge"), 18)

    def test_manual_queue_unresolved_expression(self):
        self.assertEqual(resolve_pr_id("$(System.PullRequest.PullRequestId)", "refs/pull/18/merge"), 18)

    def test_mismatched_pr_is_blocked(self):
        with self.assertRaises(ValueError):
            resolve_pr_id("17", "refs/pull/18/merge")

    def test_non_pr_branch_is_blocked(self):
        with self.assertRaises(ValueError):
            resolve_pr_id("$(System.PullRequest.PullRequestId)", "refs/heads/main")

    def test_invalid_zero_and_injection_are_blocked(self):
        for value in ("0", "-1", "18\n19", "abc"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                resolve_pr_id(value, "refs/heads/main")


if __name__ == "__main__":
    unittest.main()
