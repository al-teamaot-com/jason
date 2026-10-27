"""Non-mutating manual release review regressions for concurrent MSP work."""
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "manual_release_scope.py"
spec = importlib.util.spec_from_file_location("manual_release_scope", SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "--bare", str(bare))
    root = tmp_path / "source"
    git(tmp_path, "clone", str(bare), str(root))
    git(root, "checkout", "-b", "main")
    git(root, "config", "user.name", "Isolated Reviewer")
    git(root, "config", "user.email", "reviewer@example.invalid")
    (root / "shared.py").write_text("baseline\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "baseline")
    git(root, "push", "-u", "origin", "main")
    base = git(root, "rev-parse", "HEAD")
    (root / "shared.py").write_text("approved change\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "Fix one controlled issue (#101)")
    git(root, "push", "origin", "main")
    candidate = git(root, "rev-parse", "HEAD")
    return root, base, candidate, tmp_path


def reader(prs):
    return lambda unused: json.dumps(prs)


def test_single_selected_fix_is_ready_without_mutation(repo):
    root, base, candidate, _ = repo
    first = m.review(root, "test/repo", base, candidate, allowed_prs=[101], pr_reader=reader([]))
    again = m.review(root, "test/repo", base, candidate, allowed_prs=[101], pr_reader=reader([]))
    assert first["status"] == "SCOPE_REVIEWED_NOT_DEPLOYMENT_APPROVED"
    assert first["deployment_authorized"] is False
    assert first["changed_files"] == ["shared.py"]
    assert first["scope_sha256"] == again["scope_sha256"]
    assert git(root, "status", "--porcelain") == ""


def test_any_extra_merged_fix_must_be_acknowledged(repo):
    root, base, candidate, _ = repo
    plan = m.review(root, "test/repo", base, candidate, pr_reader=reader([]))
    assert plan["status"] == "BLOCKED_SCOPE"
    assert plan["unreviewed_commit_shas"] == [candidate]


def test_dirty_concurrent_developer_worktree_is_preserved_and_blocks(repo):
    root, base, candidate, tmp = repo
    worktree = tmp / "dev-worktree"
    git(root, "worktree", "add", "-b", "feature/unfinished", str(worktree), candidate)
    original = b"UNFINISHED LOCAL WORK DO NOT TOUCH\n"
    (worktree / "shared.py").write_bytes(original)
    blocked = m.review(root, "test/repo", base, candidate, allowed_prs=[101], pr_reader=reader([]))
    assert blocked["status"] == "BLOCKED_SCOPE"
    assert blocked["unreviewed_worktrees"] == [str(worktree)]
    assert (worktree / "shared.py").read_bytes() == original
    acknowledged = m.review(root, "test/repo", base, candidate, allowed_prs=[101],
                            acknowledged_worktrees=[str(worktree)], pr_reader=reader([]))
    assert acknowledged["status"] == "SCOPE_REVIEWED_NOT_DEPLOYMENT_APPROVED"
    assert (worktree / "shared.py").read_bytes() == original


def test_open_pull_request_overlap_requires_explicit_acknowledgement(repo):
    root, base, candidate, _ = repo
    prs = [{"number": 209, "headRefName": "fix/another-developer",
            "files": [{"path": "shared.py"}]}]
    blocked = m.review(root, "test/repo", base, candidate,
                       allowed_prs=[101], pr_reader=reader(prs))
    assert blocked["unreviewed_open_prs"] == [209]
    assert blocked["status"] == "BLOCKED_SCOPE"
    approved = m.review(root, "test/repo", base, candidate,
                        allowed_prs=[101], acknowledged_prs=[209],
                        pr_reader=reader(prs))
    assert approved["status"] == "SCOPE_REVIEWED_NOT_DEPLOYMENT_APPROVED"


def test_superseded_candidate_is_not_releaseable(repo):
    root, base, candidate, _ = repo
    (root / "another.py").write_text("not approved\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "Another change (#102)")
    git(root, "push", "origin", "main")
    with pytest.raises(m.ScopeBlocked, match="protected main"):
        m.review(root, "test/repo", base, candidate, allowed_prs=[101],
                 pr_reader=reader([]))


def test_unknown_or_false_acknowledgements_never_authorize_release(repo):
    root, base, candidate, _ = repo
    invalid = m.review(root, "test/repo", base, candidate,
                       allowed_prs=[101, 9999], pr_reader=reader([]))
    assert invalid["status"] == "BLOCKED_SCOPE"
    assert invalid["acknowledgments_valid"] is False


def test_truncated_pr_list_fails_closed_if_pagination_fails(repo, monkeypatch):
    prs = [{"number": 209, "headRefName": "large", "files": [
        {"path": "other.py"} for i in range(100)
    ]}]
    def fail(_args, cwd=None):
        raise m.ScopeBlocked("required read-only evidence incomplete")
    monkeypatch.setattr(m, "command", fail)
    with pytest.raises(m.ScopeBlocked, match="evidence"):
        m.open_pr_overlaps("test/repo", {"shared.py"}, reader=reader(prs))


def test_paged_pr_file_list_detects_overlap(repo, monkeypatch):
    prs = [{"number": 209, "headRefName": "large", "files": [
        {"path": "other.py"} for i in range(100)
    ]}]
    paged = [[{"filename": "other.py"} for i in range(100)],
             [{"filename": "shared.py"}]]
    monkeypatch.setattr(m, "command", lambda _args, cwd=None: json.dumps(paged))
    items, count = m.open_pr_overlaps("test/repo", {"shared.py"}, reader=reader(prs))
    assert count == 1
    assert items[0]["changed_files"] == ["shared.py"]
