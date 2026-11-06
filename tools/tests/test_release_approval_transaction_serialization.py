"""P0 #2071: an owner-approval timer must not trip drift mid-release."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from test_release_manager_host_runner import ROOT, SHA_A, SHA_B, runner


def make_hold(root: Path) -> Path:
    hold = root / "auto-promotion-incident-hold"
    hold.touch()
    return hold


def transaction(root: Path):
    path = root / "production-transaction.lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o660)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return fd


def release(fd: int) -> None:
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)


def test_mid_release_timer_defers_cleanly_before_reading_any_live_state(tmp_path, capsys):
    make_hold(tmp_path)
    fd = transaction(tmp_path)
    try:
        with (
            patch.object(runner, "DEFAULT_STATE", tmp_path),
            patch.object(runner, "_read_protected_snapshot") as root_read,
            patch.object(runner, "live_runtime") as live,
            patch.object(runner, "deploy_production") as deploy,
            patch.object(runner, "approve_release") as approve,
        ):
            assert runner.approval_only_while_promotion_held(ROOT, tmp_path) is False
        root_read.assert_not_called()
        live.assert_not_called()
        deploy.assert_not_called()
        approve.assert_not_called()
        assert "PRODUCTION_TRANSITION_IN_PROGRESS" in capsys.readouterr().out
        assert not (tmp_path / "mobile-release-offers").exists()
    finally:
        release(fd)


def test_timer_holds_same_native_lock_through_entire_approval_phase(tmp_path):
    make_hold(tmp_path)
    native_lock = tmp_path / "production-transaction.lock"

    def observed_while_approval_running(*args):
        fd = os.open(native_lock, os.O_RDWR | os.O_NOFOLLOW)
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(fd)
        return False

    with (
        patch.object(runner, "DEFAULT_STATE", tmp_path),
        patch.object(runner, "_approval_only_on_stable_production",
                     side_effect=observed_while_approval_running) as stable,
    ):
        assert runner.approval_only_while_promotion_held(ROOT, tmp_path) is False
    stable.assert_called_once_with(ROOT, tmp_path)

    fd = transaction(tmp_path)  # native release is free again
    release(fd)


def test_persistent_baseline_mismatch_outside_transaction_is_real_failure(tmp_path):
    make_hold(tmp_path)
    control = {
        "schema_version": "1.0", "circuit_breaker": {"state": "closed"},
        "last_known_good": {"manifest": {"revision": SHA_A}},
    }
    drift = {"schema_version": "1.0", "status": "pass", "problems": []}
    with (
        patch.object(runner, "DEFAULT_STATE", tmp_path),
        patch.object(runner, "_read_protected_snapshot",
                     side_effect=lambda state, name:
                         control if name == "production-control-state.json" else drift),
        patch.object(runner, "live_runtime", return_value={"revision": SHA_B}),
        patch.object(runner, "live_production_alignment", return_value={}),
        patch.object(runner, "deploy_production") as deploy,
    ):
        with pytest.raises(runner.ReleaseManagerError, match="does not match LKG"):
            runner.approval_only_while_promotion_held(ROOT, tmp_path)
    deploy.assert_not_called()
    assert not (tmp_path / "mobile-release-offers").exists()


@pytest.mark.parametrize("unsafe", ["symlink", "directory", "world_writable"])
def test_corrupted_native_lock_is_not_treated_as_valid_release_or_idle(tmp_path, unsafe):
    make_hold(tmp_path)
    lock = tmp_path / "production-transaction.lock"
    if unsafe == "symlink":
        lock.symlink_to(tmp_path / "nonexistent")
    elif unsafe == "directory":
        lock.mkdir()
    else:
        lock.touch()
        lock.chmod(0o666)
    with (
        patch.object(runner, "DEFAULT_STATE", tmp_path),
        patch.object(runner, "_read_protected_snapshot") as root_read,
    ):
        with pytest.raises(runner.ReleaseManagerError):
            runner.approval_only_while_promotion_held(ROOT, tmp_path)
    root_read.assert_not_called()


def test_no_incident_hold_means_no_approval_and_no_mutex_creation(tmp_path):
    with (
        patch.object(runner, "DEFAULT_STATE", tmp_path),
        patch.object(runner, "_read_protected_snapshot") as root_read,
    ):
        assert runner.approval_only_while_promotion_held(ROOT, tmp_path) is False
    root_read.assert_not_called()
    assert not (tmp_path / "production-transaction.lock").exists()


def test_existing_normal_cycle_remains_nonexecuting_and_idle(tmp_path, capsys):
    make_hold(tmp_path)
    root = {
        "schema_version": "1.0", "circuit_breaker": {"state": "closed"},
        "last_known_good": {"manifest": {"revision": SHA_A}},
    }
    drift = {"schema_version": "1.0", "status": "pass", "problems": []}
    with (
        patch.object(runner, "DEFAULT_STATE", tmp_path),
        patch.object(runner, "_read_protected_snapshot",
                     side_effect=lambda s, n:
                         root if n == "production-control-state.json" else drift),
        patch.object(runner, "live_runtime", return_value={"revision": SHA_A}),
        patch.object(runner, "live_production_alignment", return_value={}),
        patch.object(runner, "MOBILE_APPROVAL_POLICY", tmp_path / "missing.json"),
        patch.object(runner, "deploy_production") as deploy,
    ):
        assert runner.approval_only_while_promotion_held(ROOT, tmp_path) is False
    assert "OWNER_POLICY_UNAVAILABLE" in capsys.readouterr().out
    deploy.assert_not_called()
    assert (tmp_path / "production-transaction.lock").is_file()
