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


def test_all_1020_registered_worktrees_including_last_dirty_overlap_are_checked(
    tmp_path, monkeypatch,
):
    """Real host has >1,000 worktrees; don't silently skip later developers."""
    count = 1020
    paths = [tmp_path / f"reviewed-{i:04d}" for i in range(count)]
    for path in paths:
        path.mkdir()
    target = paths[-1]
    inspected = []

    def fake_command(args, cwd=None):
        if args[:3] == ["git", "worktree", "list"]:
            return "\n\n".join(f"worktree {p}" for p in paths)
        assert args[:3] == ["git", "status", "--porcelain=v1"]
        inspected.append(cwd)
        assert args[-1] == "shared.py"
        return " M shared.py\n" if cwd == target else ""

    monkeypatch.setattr(m, "command", fake_command)
    overlaps, n, stale, registered = m.dirty_worktrees(tmp_path, {"shared.py"})
    assert n == count and registered == count and stale == []
    assert len(inspected) == count
    assert len(set(inspected)) == count
    assert overlaps == [{
        "path": str(target),
        "changed_files": ["shared.py"],
    }]


def test_more_than_2000_registered_worktrees_still_fails_closed(monkeypatch, tmp_path):
    paths = [tmp_path / f"registry-{i:05d}" for i in range(2001)]
    def fake_command(args, cwd=None):
        assert args[:3] == ["git", "worktree", "list"]
        return "\n\n".join(f"worktree {p}" for p in paths)
    monkeypatch.setattr(m, "command", fake_command)
    with pytest.raises(m.ScopeBlocked, match="incomplete registered worktree set"):
        m.dirty_worktrees(tmp_path, {"shared.py"})


def test_missing_registered_worktree_still_refuses_scope_review(monkeypatch, tmp_path):
    paths = [tmp_path / f"present-{i}" for i in range(3)]
    for path in paths[:2]:
        path.mkdir()
    def fake_command(args, cwd=None):
        if args[:3] == ["git", "worktree", "list"]:
            return "\n\n".join(f"worktree {p}" for p in paths)
        return ""
    monkeypatch.setattr(m, "command", fake_command)
    with pytest.raises(m.ScopeBlocked, match="worktree unavailable"):
        m.dirty_worktrees(tmp_path, {"shared.py"})



def test_verified_stale_git_registrations_skipped_without_modifying_worktrees(
    tmp_path, monkeypatch,
):
    existing = [tmp_path / f"present-{i}" for i in range(1020)]
    stale = [tmp_path / f"missing-{i}" for i in range(26)]
    for path in existing:
        path.mkdir()
    inspected = []
    parts = [f"worktree {p}\nHEAD {'a' * 40}" for p in existing]
    parts += [
        f"worktree {p}\nHEAD {'a' * 40}\nprunable gitdir file points to non-existent location"
        for p in stale
    ]
    def fake_command(args, cwd=None):
        if args[:3] == ["git", "worktree", "list"]:
            return "\n\n".join(parts)
        assert args[:3] == ["git", "status", "--porcelain=v1"]
        inspected.append(cwd)
        return " M shared.py\n" if cwd == existing[-1] else ""
    monkeypatch.setattr(m, "command", fake_command)
    overlaps, checked, ignored, registered = m.dirty_worktrees(tmp_path, {"shared.py"})
    assert checked == 1020 and registered == 1046
    assert len(inspected) == 1020 and set(inspected) == set(existing)
    assert set(ignored) == {str(p) for p in stale}
    assert overlaps == [{"path": str(existing[-1]), "changed_files": ["shared.py"]}]
    assert all(x.is_dir() for x in existing)
    assert all(not x.exists() for x in stale)


def test_prunable_marker_cannot_hide_a_real_worktree(tmp_path, monkeypatch):
    present = tmp_path / "still-present"
    present.mkdir()
    monkeypatch.setattr(
        m, "command",
        lambda args, cwd=None: (
            f"worktree {present}\nHEAD {'a' * 40}\nprunable gitdir file points to non-existent location"
        ),
    )
    with pytest.raises(m.ScopeBlocked, match="marked prunable while present"):
        m.dirty_worktrees(tmp_path, {"shared.py"})


def test_unverified_absent_git_registration_is_never_silently_skipped(tmp_path, monkeypatch):
    missing = tmp_path / "missing-unverified"
    monkeypatch.setattr(m, "command", lambda args, cwd=None: f"worktree {missing}")
    with pytest.raises(m.ScopeBlocked, match="worktree unavailable"):
        m.dirty_worktrees(tmp_path, {"shared.py"})


def test_scope_digest_includes_verified_missing_git_registry_evidence(tmp_path, monkeypatch):
    """Cannot reuse a release receipt after the Git worktree inventory changes."""
    sha = "a" * 40
    commits = [{"sha": sha, "subject": "Reviewed feature (#101)", "prs": [101]}]
    monkeypatch.setattr(m, "source_scope", lambda *_: (commits, ["shared.py"]))
    monkeypatch.setattr(m, "open_pr_overlaps", lambda *_args, **_kwargs: ([], 0))
    monkeypatch.setattr(
        m, "dirty_worktrees",
        lambda *_: ([], 1020, ["/tmp/stale-Git-entry"], 1046),
    )
    initial = m.review(
        tmp_path, "test/repo", "1" * 40, "2" * 40,
        allowed_prs=[101], pr_reader=reader([]),
    )
    assert initial["status"] == "SCOPE_REVIEWED_NOT_DEPLOYMENT_APPROVED"
    assert initial["registered_worktrees"] == 1046
    assert initial["worktrees_inspected"] == 1020
    assert initial["git_verified_stale_registrations"] == ["/tmp/stale-Git-entry"]
    monkeypatch.setattr(
        m, "dirty_worktrees",
        lambda *_: ([], 1020, ["/tmp/a-different-stale-Git-entry"], 1046),
    )
    changed = m.review(
        tmp_path, "test/repo", "1" * 40, "2" * 40,
        allowed_prs=[101], pr_reader=reader([]),
    )
    assert changed["scope_sha256"] != initial["scope_sha256"]
