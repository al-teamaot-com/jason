"""Exact immutable candidate checks must fail closed without changing scheduled CCC."""
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools import ccc_runner

CANDIDATE = "8cc5da52478899c73d475e50086c0b02fdfb37bf"
MAIN = "65a105d3411f33c2ca95e41d38cf26962d6ad1d7"


class TestImmutableCCCScope(unittest.TestCase):
    def setUp(self):
        self.runner = ccc_runner.CCCRunner(
            SimpleNamespace(repository_root=Path("/test-repo"), enabled=True),
            checker_revision=CANDIDATE
        )

    def test_scheduled_checker_still_selects_current_protected_main(self):
        with patch.object(ccc_runner, "_run", return_value=subprocess.CompletedProcess([], 0)), \
             patch.object(ccc_runner, "_git", return_value=MAIN) as git:
            self.assertEqual(self.runner._authoritative_source_revision(), MAIN)
            git.assert_called_once_with(Path("/test-repo"), "rev-parse", "origin/main")

    def test_release_checker_selects_only_exact_ancestor_candidate(self):
        observed = []
        def execute(args, **kwargs):
            observed.append(tuple(args))
            return subprocess.CompletedProcess(args, 0)
        def git(_repo, *args):
            if args == ("rev-parse", "origin/main"):
                return MAIN
            if args == ("rev-parse", f"{CANDIDATE}^{{commit}}"):
                return CANDIDATE
            raise AssertionError("unexpected git invocation")
        with patch.object(ccc_runner, "_run", side_effect=execute), \
             patch.object(ccc_runner, "_git", side_effect=git):
            self.assertEqual(self.runner._authoritative_source_revision(CANDIDATE), CANDIDATE)
        self.assertIn(("git", "merge-base", "--is-ancestor", CANDIDATE, MAIN), observed)

    def test_reject_unmerged_candidate_and_never_substitute_main(self):
        def execute(args, **kwargs):
            return subprocess.CompletedProcess(args, 1 if "merge-base" in args else 0)
        with patch.object(ccc_runner, "_run", side_effect=execute), \
             patch.object(ccc_runner, "_git", return_value=MAIN):
            with self.assertRaisesRegex(ccc_runner.CCCRunnerError, "not reachable"):
                self.runner._authoritative_source_revision(CANDIDATE)

    def test_reject_abbreviated_or_nonhex_candidate(self):
        for value in ("8cc5da52", "Z" * 40, "", " " + CANDIDATE):
            with self.subTest(value=value), \
                 patch.object(ccc_runner, "_run", return_value=subprocess.CompletedProcess([], 0)), \
                 patch.object(ccc_runner, "_git", return_value=MAIN):
                with self.assertRaisesRegex(ccc_runner.CCCRunnerError, "exact full SHA"):
                    self.runner._authoritative_source_revision(value)

    def test_reject_unforced_release_candidate_override(self):
        with self.assertRaisesRegex(ccc_runner.CCCRunnerError, "forced material-change"):
            self.runner.run(force=False, trigger="material_change", candidate_sha=CANDIDATE)
        with self.assertRaisesRegex(ccc_runner.CCCRunnerError, "forced material-change"):
            self.runner.run(force=True, trigger="scheduled", candidate_sha=CANDIDATE)

    def test_runner_remains_bound_to_independent_checker_and_material_review(self):
        repo = Path(__file__).resolve().parents[2]
        runner = (repo / "tools/release_manager_host_runner.py").read_text()
        self.assertIn('"/opt/jason/ccc-current/tools/run_ccc.py"', runner)
        self.assertIn('"--candidate-sha", candidate_sha', runner)
        source = (repo / "tools/ccc_runner.py").read_text()
        self.assertIn('review = self._material_review(source_revision)', source)
        self.assertIn('self._source_checks(worktree, run_dir)', source)
        self.assertIn('self._host_checks(runtime_revision)', source)


if __name__ == "__main__":
    unittest.main()
