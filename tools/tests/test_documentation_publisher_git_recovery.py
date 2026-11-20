"""Real disposable Git remotes: rewritten generated branches and safe recovery."""
from pathlib import Path
import json
import os
import subprocess
import textwrap

import pytest

PUBLISHER = Path(__file__).resolve().parents[1] / "publish_documentation_reconciliation.sh"
BRANCH = "automation/documentation-reconcile-current"
GENERATED = {"docs/control/AUTOMATED-CHANGE-STATE.json", "docs/control/AUTOMATED-CHANGE-STATE.md"}


def git(root, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(root), *args], text=True, capture_output=True, check=check,
        env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"},
    )


def identity(root):
    git(root, "config", "user.name", "Disposable Documentation Test")
    git(root, "config", "user.email", "fixture@example.invalid")


def commit(root, message):
    git(root, "add", ".")
    git(root, "commit", "-m", message)
    return git(root, "rev-parse", "HEAD").stdout.strip()


@pytest.fixture
def source(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(remote)],
                   check=True, capture_output=True)
    repo = tmp_path / "repo"
    subprocess.run(["git", "clone", str(remote), str(repo)], check=True, capture_output=True)
    identity(repo)
    (repo / "docs/control").mkdir(parents=True)
    (repo / "tools").mkdir()
    (repo / "docs/control/AUTOMATED-CHANGE-STATE.json").write_text("{}")
    (repo / "docs/control/AUTOMATED-CHANGE-STATE.md").write_text("initial")
    (repo / "tools/documentation_success_reconciler.py").write_text(textwrap.dedent("""
        import json,sys
        from pathlib import Path
        revision=sys.argv[sys.argv.index('--source-revision')+1]
        Path('docs/control/AUTOMATED-CHANGE-STATE.json').write_text(
            json.dumps({'validated_source':{'revision':revision}}))
        Path('docs/control/AUTOMATED-CHANGE-STATE.md').write_text(revision)
    """))
    (repo / "tools/validate_documentation_control.py").write_text("pass\n")
    (repo / "tools/development_release_coordinator.py").write_text(textwrap.dedent("""
        import json,os,sys
        from pathlib import Path
        Path(os.environ['COORDINATOR_CALL']).write_text(json.dumps({
            'argv':sys.argv[1:],
            'token_present':os.environ.get('GITHUB_TOKEN')=='disposable-test-token'}))
        Path(sys.argv[sys.argv.index('--output')+1]).write_text('disposable board')
    """))
    seed = commit(repo, "fixture baseline")
    git(repo, "push", "origin", "main")
    git(repo, "switch", "-c", BRANCH)
    (repo / "docs/control/AUTOMATED-CHANGE-STATE.json").write_text(
        json.dumps({"validated_source": {"revision": seed}}))
    (repo / "docs/control/AUTOMATED-CHANGE-STATE.md").write_text("old generated")
    stale = commit(repo, "old generated revision")
    git(repo, "push", "-u", "origin", BRANCH)
    git(repo, "switch", "main")
    other = tmp_path / "other"
    subprocess.run(["git", "clone", str(remote), str(other)], check=True, capture_output=True)
    identity(other)
    git(other, "switch", "-c", BRANCH, seed)
    (other / "docs/control/AUTOMATED-CHANGE-STATE.json").write_text(
        json.dumps({"validated_source": {"revision": seed}}))
    (other / "docs/control/AUTOMATED-CHANGE-STATE.md").write_text("rewritten generated")
    fresh = commit(other, "replacement generated revision")
    git(other, "push", "--force", "origin", BRANCH)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    gh = fake_bin / "gh"
    gh.write_text("""#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
a=sys.argv[1:]
if a[:2]==['pr','list']: print('[]')
elif a[:2]==['auth','token']: print('disposable-test-token')
elif a[:2]==['issue','edit']: Path(os.environ['PUBLISHED']).write_text('board updated')
elif a[:2]==['pr','create']: print('https://github.com/example/fixture/pull/123')
elif a[:2]==['pr','view']: print('123')
else: raise SystemExit(90)
""")
    gh.chmod(0o700)
    env = {**os.environ, "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"],
           "JASON_DOCUMENTATION_REPO_ROOT": str(repo),
           "JASON_DOCUMENTATION_WORKTREE_ROOT": str(tmp_path / "worktrees"),
           "PUBLISHED": str(tmp_path / "published"),
           "COORDINATOR_CALL": str(tmp_path / "coordinator-call.json")}
    return {"repo": repo, "other": other, "remote": remote, "env": env,
            "seed": seed, "stale": stale, "fresh": fresh, "root": tmp_path}


def advance_main(s, *, merge_generated=False):
    if merge_generated:
        git(s["repo"], "fetch", "origin", "+" + "refs/heads/" + BRANCH
            + ":refs/remotes/origin/inspection")
        git(s["repo"], "merge", "--no-ff", "origin/inspection", "-m", "accepted generated state")
    (s["repo"] / "tools/unrelated_material.py").write_text("unchanged by publisher\n")
    current = commit(s["repo"], "later protected main material")
    git(s["repo"], "push", "origin", "main")
    return current


def publish(s, current):
    return subprocess.run(["bash", str(PUBLISHER), "source", current, "123", "https://example.invalid/123"],
                          env=s["env"], capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize("merged", [False, True])
def test_rewritten_tracking_ref_and_later_main_recover_through_normal_publication(source, merged):
    s = source
    current = advance_main(s, merge_generated=merged)
    assert git(s["other"], "merge-base", "--is-ancestor", s["stale"], s["fresh"],
               check=False).returncode == 1
    result = publish(s, current)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "DOCUMENTATION_PUBLICATION=PR_OPEN" in result.stdout
    assert Path(s["env"]["PUBLISHED"]).is_file()
    call = json.loads(Path(s["env"]["COORDINATOR_CALL"]).read_text())
    assert call['token_present'] is True
    assert '--token' not in call['argv'] and 'disposable-test-token' not in call['argv']
    tip = git(s["repo"], "rev-parse", BRANCH).stdout.strip()
    assert git(s["repo"], "merge-base", "--is-ancestor", current, tip).returncode == 0
    assert set(git(s["repo"], "diff", "--name-only", current, tip).stdout.splitlines()) == GENERATED
    assert json.loads(git(s["repo"], "show", tip + ":docs/control/AUTOMATED-CHANGE-STATE.json").stdout
                      )["validated_source"]["revision"] == current


def test_foreign_changes_are_denied_before_publication(source):
    s = source
    (s["other"] / "foreign-code.py").write_text("preserve me\n")
    foreign = commit(s["other"], "unrelated work must not be overwritten")
    git(s["other"], "push", "origin", BRANCH)
    current = advance_main(s)
    result = publish(s, current)
    assert result.returncode != 0
    assert "DOCUMENTATION_PUBLICATION=BLOCKED_NON_GENERATED_BRANCH" in result.stderr
    assert not Path(s["env"]["PUBLISHED"]).exists()
    assert git(s["repo"], "ls-remote", "origin", "refs/heads/" + BRANCH).stdout.split()[0] == foreign


@pytest.mark.parametrize("registered", [False, True])
def test_existing_work_is_preserved_instead_of_force_removed(source, registered):
    s = source
    current = advance_main(s)
    target = Path(s["env"]["JASON_DOCUMENTATION_WORKTREE_ROOT"]) / "documentation-reconcile-current"
    target.parent.mkdir()
    if registered:
        git(s["repo"], "worktree", "add", str(target), BRANCH)
    else:
        target.mkdir()
    sentinel = target / "unrelated-work.txt"
    sentinel.write_text("preserve this exact work")
    result = publish(s, current)
    expected = "BLOCKED_DIRTY_WORKTREE" if registered else "BLOCKED_UNREGISTERED_WORKTREE"
    assert result.returncode != 0 and expected in result.stderr
    assert sentinel.read_text() == "preserve this exact work"
    assert not Path(s["env"]["PUBLISHED"]).exists()
