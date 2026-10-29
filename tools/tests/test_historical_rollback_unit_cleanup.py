"""P0 #1101 rollback unit cleanup, fully disposable; never invokes real systemctl."""
from __future__ import annotations

import importlib.util
import os
import stat
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


worker = load(ROOT / "tools/release_host_reconcile_worker.py", "jason_root_legacy_rollback_test")
planner = load(ROOT / "tools/reconcile_managed_unit_delta.py", "jason_delta_legacy_rollback_test")
SHA_A = "a" * 40
SHA_B = "b" * 40


def fixture(tmp_path, monkeypatch, *, approved=True):
    releases = tmp_path / "releases"
    candidate = releases / SHA_A
    target = releases / SHA_B
    (candidate / "config").mkdir(parents=True)
    (target / "config").mkdir(parents=True)
    system = "jason-delegation-maintenance.timer"
    shared_user = "jason-release-manager.timer"
    newer = "jason-new-rollback-watch.timer"
    source = candidate / "infrastructure/openclaw-operations/systemd/user"
    source.mkdir(parents=True)
    (source / newer).write_text("[Timer]\nOnCalendar=hourly\n")
    legacy = target / "infrastructure/openclaw-operations/systemd/user"
    legacy.mkdir(parents=True)
    (legacy / shared_user).write_text("[Timer]\n")
    legacy_system = target / "infrastructure/openclaw-operations/systemd"
    legacy_system.mkdir(parents=True, exist_ok=True)
    (legacy_system / system).write_text("[Timer]\n")
    (candidate / "config/production-desired-state.json").write_text(
        '{"schema_version":"1.0","required_system_units":[],'
        '"allowed_system_units":[],"required_user_units":["' + newer + '"],'
        '"allowed_user_units":[]}'
    )
    current = tmp_path / "current"
    current.symlink_to(candidate, target_is_directory=True)
    installed_system = tmp_path / "systemd-system"
    installed_user = tmp_path / "systemd-user"
    installed_system.mkdir()
    installed_user.mkdir()
    installed = installed_user / newer
    installed.write_bytes((source / newer).read_bytes())
    state = {
        "last_known_good": {
            "manifest": {"revision": SHA_B if approved else SHA_A, "complete": True}
        }, "circuit_breaker": {"state": "closed"},
    }
    fake_helper = SimpleNamespace(
        ROOT=tmp_path / "protected",
        _root_only=lambda path: path,
        _json=lambda path: state,
    )
    monkeypatch.setattr(worker.pwd, "getpwnam",
                        lambda account: SimpleNamespace(pw_uid=os.getuid()))
    monkeypatch.setattr(worker, "RELEASE_ROOT", releases)
    monkeypatch.setattr(worker, "CURRENT", current)
    monkeypatch.setattr(worker, "SYSTEM_UNIT_DIR", installed_system)
    monkeypatch.setattr(worker, "USER_UNIT_DIR", installed_user)
    monkeypatch.setattr(worker, "SPOOL", tmp_path / "spool")
    monkeypatch.setattr(worker, "_trusted_root_policy_helper", lambda: fake_helper)
    monkeypatch.setattr(worker, "_trusted_unit_delta_planner", lambda: planner)
    return newer, installed, state


def test_historical_rollback_preflight_is_read_only_and_lkg_bound(tmp_path, monkeypatch):
    newer, installed, state = fixture(tmp_path, monkeypatch)
    result = worker._historical_unit_cleanup_plan(SHA_B)
    assert result[2] == ()
    assert result[3] == (newer,)
    assert installed.exists()
    state["last_known_good"]["manifest"]["revision"] = SHA_A
    with pytest.raises(worker.HostReconcileError, match="protected LKG"):
        worker._historical_unit_cleanup_plan(SHA_B)
    assert installed.exists()


def test_historical_rollback_rejects_changed_unit_without_any_commands(tmp_path, monkeypatch):
    newer, installed, state = fixture(tmp_path, monkeypatch)
    installed.write_text("unexpected user modification")
    with patch.object(worker.subprocess, "run") as commands:
        with pytest.raises(planner.UnitDeltaError, match="differs"):
            worker._reconcile_historical_release_units(SHA_B, "safe-request")
    commands.assert_not_called()
    assert installed.exists()


def test_historical_rollback_removes_only_verified_candidate_unit_with_backup(tmp_path, monkeypatch):
    newer, installed, state = fixture(tmp_path, monkeypatch)
    spool = tmp_path / "spool"
    spool.mkdir()
    # Run the actual file backup/removal path in a disposable UID-1000
    # fixture. Mock only the root UID representation and systemctl. The live
    # root-only service's ownership/mode check stays unchanged in source.
    original_lstat = Path.lstat
    backup_root = spool / "historical-unit-backups"

    def lstat_as_root(path, *args, **kwargs):
        result = original_lstat(path, *args, **kwargs)
        if path == backup_root:
            values = list(result)
            values[4] = 0
            return os.stat_result(values)
        return result

    monkeypatch.setattr(Path, "lstat", lstat_as_root)
    monkeypatch.setattr(worker.os, "fchown", lambda *args: None)
    commands = []
    monkeypatch.setattr(
        worker.subprocess, "run",
        lambda args, **kwargs: commands.append(args) or SimpleNamespace(returncode=0),
    )
    before = installed.read_bytes()
    removed = worker._reconcile_historical_release_units(SHA_B, "safe-request")
    assert removed == ["user:" + newer]
    assert not installed.exists()
    backup = backup_root / "safe-request" / ("user-" + newer)
    assert backup.read_bytes() == before
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    assert any("disable" in args and "--now" in args and newer in args
               for args in commands)
    assert all("systemctl" in args for args in commands)
    assert all(not ("restart" in args or "reboot" in args) for args in commands)


def test_historical_unit_backup_rejects_dotdot_identity_before_mutation(tmp_path, monkeypatch):
    newer, installed, state = fixture(tmp_path, monkeypatch)
    with patch.object(worker.subprocess, "run") as commands:
        with pytest.raises(worker.HostReconcileError, match="invalid rollback backup identity"):
            worker._reconcile_historical_release_units(SHA_B, "..")
    commands.assert_not_called()
    assert installed.exists()
