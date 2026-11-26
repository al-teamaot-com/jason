"""Stage E scope checks require host and freeze boundaries and fresh evidence."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from tools import pmv4_e_source_scope_guard as guard
from tools.tests.test_manual_release_scope import repo, git, m as scope

CANDIDATE = "b" * 40
ROLLBACK = "a" * 40
HEAD = "c" * 40
DIGEST = "d" * 64
NOW = datetime.now(timezone.utc)


def ci(**changes):
    result = {
        "candidate_sha": CANDIDATE,
        "protected_main": HEAD,
        "protected_main_ancestor": True,
        "required_ci_passed": True,
        "verified_at": NOW.isoformat(),
    }
    result.update(changes)
    return result


def args(**changes):
    result = {
        "candidate": CANDIDATE, "rollback": ROLLBACK,
        "manual_sha256": DIGEST, "host_lock_held": True,
        "freeze_lock_held": True, "production": False,
        "ci_data": ci(), "at": NOW,
    }
    result.update(changes)
    return result


def test_both_checks_receive_exact_head_and_use_unprivileged_fixed_commands():
    calls = []
    def runner(command, **kwargs):
        calls.append((command, kwargs))
        values = [HEAD + "\trefs/heads/main\n", "false\n", guard.PASS + "\n"]
        return SimpleNamespace(returncode=0, stdout=values[len(calls)-1])
    result = guard.verify_under_lock(**args(runner=runner))
    assert result["status"] == "protected_stage_e_source_scope_verified_under_lock"
    remote, shallow, verify = calls
    assert "GIT_GRAFT_FILE=/dev/null" in remote[0]
    assert shallow[0][-1] == "--is-shallow-repository"
    assert remote[0][:5] == ["/usr/sbin/runuser", "-u", "al", "--", "/usr/bin/env"]
    assert remote[0][-4:] == ["/usr/bin/git", "ls-remote", guard.REMOTE, "refs/heads/main"]
    assert verify[0][-5:] == [str(guard.MANUAL), str(guard.REPO), ROLLBACK, CANDIDATE, HEAD]
    assert all(call[1]["cwd"] == "/" and call[1]["env"] == {"PATH": "/usr/bin:/bin"}
               for call in calls)
    assert result["production_mutations"] is False


@pytest.mark.parametrize("changes", [
    {"host_lock_held": False},
    {"freeze_lock_held": False},
    {"candidate": "bad"},
    {"rollback": CANDIDATE},
    {"manual_sha256": "bad"},
    {"ci_data": ci(candidate_sha="f" * 40)},
    {"ci_data": ci(protected_main_ancestor=False)},
    {"ci_data": ci(required_ci_passed=False)},
    {"ci_data": ci(verified_at=(NOW - timedelta(seconds=601)).isoformat())},
    {"ci_data": ci(verified_at=(NOW + timedelta(seconds=1)).isoformat())},
])
def test_bad_locks_identity_or_evidence_fail_before_external_commands(changes):
    seen = []
    def runner(*a, **k):
        seen.append(a)
        raise AssertionError("must not run")
    with pytest.raises(guard.StageESourceScopeDenied):
        guard.verify_under_lock(**args(runner=runner, **changes))
    assert not seen


@pytest.mark.parametrize("remote_rc,remote_output,scope_rc,scope_output", [
    (1, "", 0, guard.PASS),
    (0, "e" * 40 + "\trefs/heads/main\n", 0, guard.PASS),
    (0, HEAD + "\trefs/heads/main\nextra", 0, guard.PASS),
    (0, HEAD + "\trefs/heads/main\n", 1, ""),
    (0, HEAD + "\trefs/heads/main\n", 0, "unverified"),
])
def test_changed_main_or_failed_scope_never_passes(remote_rc, remote_output,
                                                  scope_rc, scope_output):
    outputs = iter([SimpleNamespace(returncode=remote_rc, stdout=remote_output),
                    SimpleNamespace(returncode=0, stdout="false\n"),
                    SimpleNamespace(returncode=scope_rc, stdout=scope_output)])
    with pytest.raises(guard.StageESourceScopeDenied):
        guard.verify_under_lock(**args(runner=lambda *a, **k: next(outputs)))


def test_production_cannot_inject_a_fake_ci_result_or_runner():
    with pytest.raises(guard.StageESourceScopeDenied, match="CANONICAL_ROOT_GUARD_REQUIRED"):
        guard.verify_under_lock(**args(production=True, runner=lambda *a, **k: None))


def test_real_jes005_scope_rejects_later_protected_change(repo, monkeypatch):
    root, baseline, candidate, _ = repo
    (root / "tools/release_manager_example.py").write_text("later protected change\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "Later protected change")
    head = git(root, "rev-parse", "HEAD")
    monkeypatch.setattr(guard, "REPO", root)

    def runner(command, **kwargs):
        if "ls-remote" in command:
            return SimpleNamespace(returncode=0, stdout=head + "\trefs/heads/main\n")
        if "--is-shallow-repository" in command:
            return SimpleNamespace(returncode=0, stdout="false\n")
        try:
            scope.verify_pinned_candidate_against_main(root, baseline, candidate, head)
        except scope.ScopeBlocked:
            return SimpleNamespace(returncode=1, stdout="")
        return SimpleNamespace(returncode=0, stdout=guard.PASS)

    with pytest.raises(guard.StageESourceScopeDenied, match="PROTECTED_SCOPE_NOT_REVIEWED"):
        guard.verify_under_lock(**args(candidate=candidate, rollback=baseline,
                                      ci_data=ci(candidate_sha=candidate, protected_main=head),
                                      runner=runner))


def test_shallow_repository_cannot_hide_newer_protected_changes():
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        if "ls-remote" in command:
            return SimpleNamespace(returncode=0, stdout=HEAD + "\trefs/heads/main\n")
        return SimpleNamespace(returncode=0, stdout="true\n")
    with pytest.raises(guard.StageESourceScopeDenied, match="REVIEW_REPOSITORY_SHALLOW"):
        guard.verify_under_lock(**args(runner=runner))
    assert len(calls) == 2
