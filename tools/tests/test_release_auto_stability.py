"""Unattended Release Manager must never choose a superseded Owner approval."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import release_manager_host_runner as runner

SHA_OLD = "8" * 40
SHA_MAIN = "b" * 40
SHA_LIVE = "e" * 40


def queue_release(root: Path, sha: str, *, approved: bool) -> dict:
    record = {
        "release_id": runner.record_id(sha),
        "state": "production_eligible",
        "release_candidate": {"candidate_sha": sha},
        "rollback_sha": SHA_LIVE,
        "owner_approval": {"approved": approved, "candidate_sha": sha if approved else None},
    }
    runner.atomic_json(root / "records" / (record["release_id"] + ".json"), record)
    return record


def auto_environment(head: str):
    return (
        patch.object(runner.gate, "load_json", return_value={
            "schedule": {"automatic_promotion_enabled": True}}),
        patch.object(runner, "production_window_open", return_value=True),
        patch.object(runner, "consume_owner_approval_requests"),
        patch.object(runner, "authoritative_auto_promotion_head", return_value=head),
    )


def test_authoritative_head_requires_exact_remote_ref():
    good = subprocess.CompletedProcess([], 0, SHA_MAIN + "\trefs/heads/main\n", "")
    with patch.object(runner.subprocess, "run", return_value=good) as cmd:
        assert runner.authoritative_auto_promotion_head(Path("/trusted")) == SHA_MAIN
        assert cmd.call_args.args[0] == [
            "git", "ls-remote", "--exit-code", "origin", "refs/heads/main",
        ]


@pytest.mark.parametrize("stdout,exit_status", [
    ("", 128),
    ("", 0),
    ("malformed refs/heads/main\n", 0),
    (SHA_MAIN + "\trefs/tags/main\n", 0),
    (SHA_MAIN + "\trefs/heads/main\n" + SHA_OLD + "\trefs/heads/main\n", 0),
])
def test_unverifiable_remote_head_fails_closed(stdout: str, exit_status: int):
    output = subprocess.CompletedProcess([], exit_status, stdout, "")
    with patch.object(runner.subprocess, "run", return_value=output):
        with pytest.raises(runner.ReleaseManagerError, match="protected main"):
            runner.authoritative_auto_promotion_head(Path("/trusted"))


def test_old_approved_release_is_not_promoted_or_mutated(tmp_path: Path):
    old = queue_release(tmp_path, SHA_OLD, approved=True)
    with (
        patch.object(runner.gate, "load_json", return_value={
            "schedule": {"automatic_promotion_enabled": True}}),
        patch.object(runner, "production_window_open", return_value=True),
        patch.object(runner, "consume_owner_approval_requests"),
        patch.object(runner, "authoritative_auto_promotion_head", return_value=SHA_MAIN),
        patch.object(runner, "deploy_production") as deploy,
        patch.object(runner, "reconcile_stopped_rollback_retention") as cleanup,
        patch.object(runner, "production_gate_result") as gate,
        patch.object(runner, "live_runtime") as runtime,
    ):
        assert runner.promote_eligible(Path("/trusted"), tmp_path) is False
        deploy.assert_not_called()
        cleanup.assert_not_called()
        gate.assert_not_called()
        runtime.assert_not_called()
    assert runner.load_record(tmp_path, old["release_id"]) == old


def test_new_main_requires_its_own_exact_owner_approval(tmp_path: Path):
    old = queue_release(tmp_path, SHA_OLD, approved=True)
    new = queue_release(tmp_path, SHA_MAIN, approved=False)
    def gate_result(repo, release):
        assert release["release_id"] == new["release_id"]
        return {"allowed": False, "reasons": [
            "production release requires explicit owner approval",
            "owner approval is not bound to the exact candidate SHA",
        ]}
    with (
        patch.object(runner.gate, "load_json", return_value={
            "schedule": {"automatic_promotion_enabled": True}}),
        patch.object(runner, "production_window_open", return_value=True),
        patch.object(runner, "consume_owner_approval_requests"),
        patch.object(runner, "authoritative_auto_promotion_head", return_value=SHA_MAIN),
        patch.object(runner, "live_runtime", return_value={"revision": SHA_LIVE}),
        patch.object(runner, "live_production_alignment", return_value={}),
        patch.object(runner, "production_gate_result", side_effect=gate_result),
        patch.object(runner, "write_owner_notification_event") as notify,
        patch.object(runner, "deploy_production") as deploy,
        patch.object(runner, "reconcile_stopped_rollback_retention") as cleanup,
    ):
        assert runner.promote_eligible(Path("/trusted"), tmp_path) is False
        notify.assert_called_once()
        assert notify.call_args.args[1]["release_id"] == new["release_id"]
        cleanup.assert_not_called()
        deploy.assert_not_called()
    assert runner.load_record(tmp_path, old["release_id"]) == old


def test_protected_main_advancing_after_gate_cancels_promotion(tmp_path: Path):
    queue_release(tmp_path, SHA_MAIN, approved=True)
    with (
        patch.object(runner.gate, "load_json", return_value={
            "schedule": {"automatic_promotion_enabled": True}}),
        patch.object(runner, "production_window_open", return_value=True),
        patch.object(runner, "consume_owner_approval_requests"),
        patch.object(runner, "authoritative_auto_promotion_head", side_effect=[
            SHA_MAIN, SHA_OLD,
        ]),
        patch.object(runner, "live_runtime", return_value={"revision": SHA_LIVE}),
        patch.object(runner, "live_production_alignment", return_value={}),
        patch.object(runner, "production_gate_result", return_value={
            "allowed": True, "reasons": []}),
        patch.object(runner, "reconcile_stopped_rollback_retention") as cleanup,
        patch.object(runner, "deploy_production") as deploy,
    ):
        assert runner.promote_eligible(Path("/trusted"), tmp_path) is False
        cleanup.assert_not_called()
        deploy.assert_not_called()


def test_remote_failure_during_final_head_recheck_defers_without_cleanup(tmp_path: Path):
    queue_release(tmp_path, SHA_MAIN, approved=True)
    with (
        patch.object(runner.gate, "load_json", return_value={
            "schedule": {"automatic_promotion_enabled": True}}),
        patch.object(runner, "production_window_open", return_value=True),
        patch.object(runner, "consume_owner_approval_requests"),
        patch.object(runner, "authoritative_auto_promotion_head", side_effect=[
            SHA_MAIN, runner.ReleaseManagerError("remote now unavailable"),
        ]),
        patch.object(runner, "live_runtime", return_value={"revision": SHA_LIVE}),
        patch.object(runner, "live_production_alignment", return_value={}),
        patch.object(runner, "production_gate_result", return_value={
            "allowed": True, "reasons": []}),
        patch.object(runner, "reconcile_stopped_rollback_retention") as cleanup,
        patch.object(runner, "deploy_production") as deploy,
    ):
        assert runner.promote_eligible(Path("/trusted"), tmp_path) is False
        cleanup.assert_not_called()
        deploy.assert_not_called()


def test_remote_unavailable_is_audited_deferral_not_a_failed_service(tmp_path: Path, capsys):
    original = queue_release(tmp_path, SHA_MAIN, approved=True)
    with (
        patch.object(runner.gate, "load_json", return_value={
            "schedule": {"automatic_promotion_enabled": True}}),
        patch.object(runner, "production_window_open", return_value=True),
        patch.object(runner, "consume_owner_approval_requests"),
        patch.object(runner, "authoritative_auto_promotion_head",
                     side_effect=runner.ReleaseManagerError("connection unreachable")),
        patch.object(runner, "deploy_production") as deploy,
    ):
        assert runner.promote_eligible(Path("/trusted"), tmp_path) is False
        deploy.assert_not_called()
    assert "RELEASE_MANAGER_AUTO_DEFERRED=authoritative_main_unavailable" in capsys.readouterr().out
    assert runner.load_record(tmp_path, original["release_id"]) == original


def test_worktree_attempt_paths_unique_for_same_candidate(tmp_path: Path):
    issued = iter(["a" * 32, "b" * 32])
    with (
        patch.object(runner, "uuid4", side_effect=lambda: SimpleNamespace(hex=next(issued))),
        patch.object(runner, "run") as run_git,
    ):
        first = runner.worktree(Path("/managed"), tmp_path, SHA_MAIN)
        second = runner.worktree(Path("/managed"), tmp_path, SHA_MAIN)
    assert first != second
    assert first.parent == second.parent == tmp_path / "worktrees"
    assert SHA_MAIN in first.name and SHA_MAIN in second.name
    assert run_git.call_count == 2


def test_worktree_never_removes_unowned_attempt_directory(tmp_path: Path):
    target = tmp_path / "worktrees" / (SHA_MAIN + "-" + "a" * 12)
    target.mkdir(parents=True)
    marker = target / "preserve.txt"
    marker.write_text("unrelated durable data")
    with (
        patch.object(runner, "uuid4", return_value=SimpleNamespace(hex="a" * 32)),
        patch.object(runner, "run") as git,
    ):
        with pytest.raises(runner.ReleaseManagerError, match="already exists"):
            runner.worktree(Path("/managed"), tmp_path, SHA_MAIN)
        git.assert_not_called()
    assert marker.read_text() == "unrelated durable data"


def test_worktree_surfaces_git_error_without_claiming_release(tmp_path: Path):
    with patch.object(runner, "run", side_effect=subprocess.CalledProcessError(
        128, "git worktree add", output="fatal: stale worktree registration",
    )):
        with pytest.raises(runner.ReleaseManagerError, match="stale worktree registration"):
            runner.worktree(Path("/managed"), tmp_path, SHA_MAIN)


def test_worktree_rejects_symlinked_root(tmp_path: Path):
    external = tmp_path / "external"
    external.mkdir()
    (tmp_path / "worktrees").symlink_to(external, target_is_directory=True)
    with patch.object(runner, "run") as run_git:
        with pytest.raises(runner.ReleaseManagerError, match="not a real directory"):
            runner.worktree(Path("/managed"), tmp_path, SHA_MAIN)
        run_git.assert_not_called()
