"""Static regression contract for generated-documentation PR publication.

Run with: python3 -m unittest tests/test_documentation_single_flight.py
These checks do not substitute for integration tests with concurrent publishers.
"""
from pathlib import Path
import subprocess
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "publish_documentation_reconciliation.sh"


class DocumentationSingleFlightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = SCRIPT.read_text(encoding="utf-8")

    def test_bash_syntax(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)

    def test_publication_is_serialized(self):
        self.assertIn('flock -x 9', self.script)
        self.assertIn('documentation-reconciliation.lock', self.script)

    def test_fails_closed_on_ambiguous_pr_set(self):
        self.assertIn('if [ "$PR_COUNT" -gt 1 ]; then', self.script)
        self.assertIn('BLOCKED_MULTIPLE_CANDIDATES', self.script)

    def test_only_generated_paths_can_be_rewritten(self):
        self.assertIn('gh pr diff "$PR_NUMBER"', self.script)
        self.assertIn('BLOCKED_NON_GENERATED_CHANGE', self.script)

    def test_updates_current_pr_instead_of_always_creating(self):
        self.assertIn('PR_NUMBER="$(printf', self.script)
        self.assertIn('PR_NUMBER="${PR_NUMBER:-}"', self.script)
        self.assertIn('if [ -z "$PR_NUMBER" ]; then', self.script)

    def test_existing_pr_branch_fetched_before_rebuild(self):
        self.assertIn('refs/heads/$BRANCH:refs/remotes/origin/$BRANCH', self.script)
        self.assertIn('git worktree add -B "$BRANCH" "$WORKTREE" origin/main', self.script)

    def test_stale_or_divergent_release_is_blocked(self):
        self.assertIn('git merge-base --is-ancestor "$PRIOR_REVISION" "$SOURCE_REVISION"', self.script)
        self.assertIn('BLOCKED_STALE_OR_DIVERGENT_REVISION', self.script)
        self.assertIn('BLOCKED_UNVERIFIABLE_PRIOR', self.script)

    def test_source_and_production_are_checked_independently(self):
        self.assertIn('.validated_source.revision', self.script)
        self.assertIn('.production.revision', self.script)

    def test_pending_cross_mode_evidence_is_preserved(self):
        self.assertIn('git show "origin/$BRANCH:docs/control/AUTOMATED-CHANGE-STATE.json" > docs/control/AUTOMATED-CHANGE-STATE.json', self.script)

    def test_push_uses_lease(self):
        self.assertIn('git push --force-with-lease', self.script)


if __name__ == "__main__":
    unittest.main()
