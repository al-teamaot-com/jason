"""End-to-end documentation publisher tests with disposable Git repositories.

No production calls: gh is a local stub, origin is a bare temporary repo,
and the reconciliation/board commands are harmless fixtures. The real
publication shell script and real git/flock are exercised.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


PUBLISHER = Path(__file__).resolve().parents[1] / "tools" / "publish_documentation_reconciliation.sh"
BRANCH = "automation/documentation-reconcile-current"
JSON_PATH = "docs/control/AUTOMATED-CHANGE-STATE.json"
MD_PATH = "docs/control/AUTOMATED-CHANGE-STATE.md"

MOCK_RECONCILER = r'''
import json
from pathlib import Path
import sys

mode = sys.argv[1]
args = sys.argv
revision = args[args.index("--source-revision") + 1]
path = Path("docs/control/AUTOMATED-CHANGE-STATE.json")
state = json.loads(path.read_text())
if mode == "source":
    state["validated_source"] = {
        "revision": revision, "status": "ci_passed",
        "workflow_run_id": args[args.index("--workflow-run-id") + 1],
        "workflow_url": args[args.index("--workflow-url") + 1],
    }
else:
    state["production"] = {"revision": revision, "status": "aligned_and_healthy"}
path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
Path("docs/control/AUTOMATED-CHANGE-STATE.md").write_text(
    "# Automated Change State\n\n" + json.dumps(state, sort_keys=True) + "\n"
)
'''

MOCK_GH = r'''
import fcntl
import json
import os
from pathlib import Path
import sys

path = Path(os.environ["FAKE_GH_STATE"])
args = sys.argv[1:]
with path.open("r+") as handle:
    fcntl.flock(handle, fcntl.LOCK_EX)
    data = json.load(handle)
    prs = data["prs"]
    if args[:2] == ["pr", "list"]:
        print(json.dumps([p for p in prs if p["state"] == "open"]))
    elif args[:2] == ["pr", "diff"]:
        print("\n".join(data["changed_paths"]))
    elif args[:2] == ["auth", "token"]:
        print("fixture-token")
    elif args[:2] == ["issue", "edit"]:
        pass
    elif args[:2] == ["pr", "create"]:
        head = args[args.index("--head") + 1]
        if any(p["headRefName"] == head and p["state"] == "open" for p in prs):
            sys.exit(7)
        number = data["next"]
        data["next"] += 1
        prs.append({
            "number": number, "state": "open", "headRefName": head,
            "title": args[args.index("--title") + 1],
        })
        print(f"https://github.com/al-teamaot-com/jason/pull/{number}")
    elif args[:2] == ["pr", "view"]:
        print(prs[-1]["number"])
    else:
        print("Unexpected mocked gh invocation: " + repr(args), file=sys.stderr)
        sys.exit(8)
    handle.seek(0)
    handle.truncate()
    json.dump(data, handle)
    handle.flush()
'''


class DocumentationPublisherE2ETest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = self.root / "remote.git"
        self.repo = self.root / "repo"
        self.gh_state = self.root / "github-state.json"
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        (self.bin_dir / "gh").write_text("#!/usr/bin/env python3\n" + MOCK_GH)
        (self.bin_dir / "gh").chmod(0o755)
        self.gh_state.write_text(json.dumps({
            "prs": [], "next": 700,
            "changed_paths": [JSON_PATH, MD_PATH],
        }))
        self.git("init", "--bare", "--initial-branch=main", str(self.remote))
        self.git("clone", str(self.remote), str(self.repo))
        self.git("-C", str(self.repo), "config", "user.name", "Fixture")
        self.git("-C", str(self.repo), "config", "user.email", "fixture@example.invalid")
        self.git("-C", str(self.repo), "checkout", "-B", "main")
        (self.repo / "docs/control").mkdir(parents=True)
        (self.repo / "tools").mkdir()
        (self.repo / JSON_PATH).write_text('{"schema_version":"1.0"}\n')
        (self.repo / MD_PATH).write_text("# Automated Change State\n")
        (self.repo / "tools/documentation_success_reconciler.py").write_text(MOCK_RECONCILER)
        (self.repo / "tools/validate_documentation_control.py").write_text("print('VALIDATION=PASS')\n")
        (self.repo / "tools/development_release_coordinator.py").write_text(
            "from pathlib import Path\nimport sys\n"
            "Path(sys.argv[sys.argv.index('--output') + 1]).write_text('fixture board')\n"
        )
        self.git("-C", str(self.repo), "add", ".")
        self.git("-C", str(self.repo), "commit", "-m", "revision A")
        self.rev_a = self.git("-C", str(self.repo), "rev-parse", "HEAD").stdout.strip()
        (self.repo / "fixture.txt").write_text("next revision\n")
        self.git("-C", str(self.repo), "add", ".")
        self.git("-C", str(self.repo), "commit", "-m", "revision B")
        self.rev_b = self.git("-C", str(self.repo), "rev-parse", "HEAD").stdout.strip()
        self.git("-C", str(self.repo), "push", "-u", "origin", "main")

    def git(self, *args):
        result = subprocess.run(["git", *args], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def invoke(self, revision, *, mode="source", run_id="123", repo=None, tree=None):
        env = os.environ.copy()
        env["PATH"] = str(self.bin_dir) + os.pathsep + env["PATH"]
        env["FAKE_GH_STATE"] = str(self.gh_state)
        env["JASON_DOCUMENTATION_REPO_ROOT"] = str(repo or self.repo)
        env["JASON_DOCUMENTATION_WORKTREE_ROOT"] = str(tree or self.root / "trees")
        return subprocess.run(
            ["bash", str(PUBLISHER), mode, revision, run_id, "https://example.invalid/workflow"],
            env=env, capture_output=True, text=True, timeout=35,
        )

    def assert_published(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + "\n" + result.stderr)

    def state(self):
        return json.loads(self.gh_state.read_text())

    def branch_sha(self):
        return self.git(
            "--git-dir", str(self.remote), "rev-parse", "refs/heads/" + BRANCH
        ).stdout.strip()

    def published_state(self):
        result = self.git(
            "--git-dir", str(self.remote), "show",
            "refs/heads/" + BRANCH + ":" + JSON_PATH,
        )
        return json.loads(result.stdout)

    def test_two_successive_revisions_share_one_pr_and_branch(self):
        self.assert_published(self.invoke(self.rev_a))
        first = self.state()["prs"][0]
        self.assertEqual(first["headRefName"], BRANCH)
        self.assert_published(self.invoke(self.rev_b, run_id="124"))
        prs = self.state()["prs"]
        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0]["number"], first["number"])
        self.assertEqual(self.published_state()["validated_source"]["revision"], self.rev_b)

    def test_replay_is_noop_for_existing_candidate(self):
        self.assert_published(self.invoke(self.rev_a))
        sha = self.branch_sha()
        repeated = self.invoke(self.rev_a)
        self.assert_published(repeated)
        self.assertIn("DOCUMENTATION_PUBLICATION=NO_CHANGE", repeated.stdout)
        self.assertEqual(self.branch_sha(), sha)
        self.assertEqual(len(self.state()["prs"]), 1)

    def test_stale_revision_cannot_replace_new_snapshot(self):
        self.assert_published(self.invoke(self.rev_a))
        self.assert_published(self.invoke(self.rev_b, run_id="124"))
        sha = self.branch_sha()
        stale = self.invoke(self.rev_a)
        self.assertNotEqual(stale.returncode, 0)
        self.assertIn("BLOCKED_STALE_OR_DIVERGENT_REVISION", stale.stderr)
        self.assertEqual(self.branch_sha(), sha)
        self.assertEqual(len(self.state()["prs"]), 1)

    def test_source_production_interleave_keeps_both_records(self):
        self.assert_published(self.invoke(self.rev_a))
        self.assert_published(self.invoke(self.rev_a, mode="production"))
        self.assert_published(self.invoke(self.rev_b, run_id="124"))
        state = self.published_state()
        self.assertEqual(state["production"]["revision"], self.rev_a)
        self.assertEqual(state["validated_source"]["revision"], self.rev_b)
        self.assertEqual(len(self.state()["prs"]), 1)

    def test_non_generated_change_blocks_update(self):
        self.assert_published(self.invoke(self.rev_a))
        data = self.state()
        data["changed_paths"].append("tools/unrelated.py")
        self.gh_state.write_text(json.dumps(data))
        sha = self.branch_sha()
        rejected = self.invoke(self.rev_b)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("BLOCKED_NON_GENERATED_CHANGE", rejected.stderr)
        self.assertEqual(self.branch_sha(), sha)

    def test_historical_main_state_blocks_stale_event_without_an_open_pr(self):
        # CI may replay an old event after the previous documentation PR was merged.
        path = self.repo / JSON_PATH
        path.write_text(json.dumps({
            "schema_version": "1.0",
            "validated_source": {"revision": self.rev_b, "status": "ci_passed"},
        }) + "\n")
        self.git("-C", str(self.repo), "add", JSON_PATH)
        self.git("-C", str(self.repo), "commit", "-m", "main already records latest source")
        self.git("-C", str(self.repo), "push", "origin", "main")
        stale = self.invoke(self.rev_a)
        self.assertNotEqual(stale.returncode, 0)
        self.assertIn("BLOCKED_STALE_OR_DIVERGENT_REVISION", stale.stderr)
        self.assertEqual(self.state()["prs"], [])

    def test_main_newer_than_open_pr_also_blocks_stale_event(self):
        self.assert_published(self.invoke(self.rev_a))
        existing = self.branch_sha()
        path = self.repo / JSON_PATH
        path.write_text(json.dumps({
            "schema_version": "1.0",
            "validated_source": {"revision": self.rev_b, "status": "ci_passed"},
        }) + "\n")
        self.git("-C", str(self.repo), "add", JSON_PATH)
        self.git("-C", str(self.repo), "commit", "-m", "newer canonical main evidence")
        self.git("-C", str(self.repo), "push", "origin", "main")
        rejected = self.invoke(self.rev_a)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("BLOCKED_STALE_OR_DIVERGENT_REVISION", rejected.stderr)
        self.assertEqual(self.branch_sha(), existing)

    def test_closed_pr_remote_branch_rejects_stale_history(self):
        self.assert_published(self.invoke(self.rev_a))
        self.assert_published(self.invoke(self.rev_b, run_id="124"))
        before = self.branch_sha()
        data = self.state()
        data["prs"][0]["state"] = "closed"
        self.gh_state.write_text(json.dumps(data))
        rejected = self.invoke(self.rev_a)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("BLOCKED_STALE_OR_DIVERGENT_REVISION", rejected.stderr)
        self.assertEqual(self.branch_sha(), before)

    def test_failed_ci_does_not_spawn_second_pr_on_new_revision(self):
        self.assert_published(self.invoke(self.rev_a))
        data = self.state()
        data["prs"][0]["checks"] = "failure"
        self.gh_state.write_text(json.dumps(data))
        self.assert_published(self.invoke(self.rev_b, run_id="124"))
        self.assertEqual(len(self.state()["prs"]), 1)
        self.assertEqual(self.published_state()["validated_source"]["revision"], self.rev_b)

    def test_closed_branch_with_non_generated_changes_is_never_overwritten(self):
        self.assert_published(self.invoke(self.rev_a))
        data = self.state()
        data["prs"][0]["state"] = "closed"
        self.gh_state.write_text(json.dumps(data))
        other = self.root / "unrelated-branch-client"
        self.git("clone", str(self.remote), str(other))
        self.git("-C", str(other), "config", "user.name", "Fixture")
        self.git("-C", str(other), "config", "user.email", "fixture@example.invalid")
        self.git("-C", str(other), "checkout", "-b", "current", "origin/" + BRANCH)
        (other / "tools").mkdir(exist_ok=True)
        (other / "tools/unrelated.py").write_text("print('unrelated')\n")
        self.git("-C", str(other), "add", ".")
        self.git("-C", str(other), "commit", "-m", "unrelated edit")
        self.git("-C", str(other), "push", "origin", "HEAD:" + BRANCH)
        sha = self.branch_sha()
        rejected = self.invoke(self.rev_b)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("BLOCKED_NON_GENERATED_BRANCH", rejected.stderr)
        self.assertEqual(self.branch_sha(), sha)

    def test_two_hosts_racing_old_and_new_revision_preserve_newest(self):
        self.assert_published(self.invoke(self.rev_a))
        other = self.root / "second-host-repo"
        self.git("clone", str(self.remote), str(other))
        self.git("-C", str(other), "config", "user.name", "Fixture")
        self.git("-C", str(other), "config", "user.email", "fixture@example.invalid")
        with ThreadPoolExecutor(max_workers=2) as workers:
            old = workers.submit(
                self.invoke, self.rev_a, repo=other, tree=self.root / "trees-old"
            )
            new = workers.submit(
                self.invoke, self.rev_b, run_id="124",
                repo=self.repo, tree=self.root / "trees"
            )
            outcomes = (old.result(), new.result())
        self.assertEqual(
            outcomes[1].returncode, 0,
            outcomes[1].stdout + "\n" + outcomes[1].stderr
        )
        self.assertEqual(self.published_state()["validated_source"]["revision"], self.rev_b)
        self.assertEqual(len(self.state()["prs"]), 1)

    def test_two_hosts_initial_publication_can_create_at_most_one_pr(self):
        other = self.root / "another-host-repo"
        self.git("clone", str(self.remote), str(other))
        self.git("-C", str(other), "config", "user.name", "Fixture")
        self.git("-C", str(other), "config", "user.email", "fixture@example.invalid")
        with ThreadPoolExecutor(max_workers=2) as workers:
            first = workers.submit(
                self.invoke, self.rev_a, repo=self.repo, tree=self.root / "trees-a"
            )
            second = workers.submit(
                self.invoke, self.rev_a, repo=other, tree=self.root / "trees-b"
            )
            results = [first.result(), second.result()]
        self.assertTrue(
            any(r.returncode == 0 for r in results),
            repr([(r.stdout, r.stderr) for r in results]),
        )
        self.assertEqual(len(self.state()["prs"]), 1)
        self.assertEqual(self.state()["prs"][0]["headRefName"], BRANCH)


if __name__ == "__main__":
    unittest.main()
