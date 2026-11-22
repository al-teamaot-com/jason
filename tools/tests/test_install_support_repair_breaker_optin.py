"""Preproduction installer contract; disposable files, mocked systemd, no live mutations."""
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from tools import install_support_repair_host_worker as installer

SOURCES = (
    "support_repair_host_worker", "engineering_pipeline", "pmv3_engineering_controller",
    "pmv3_integration_queue", "owner_approved_development_worker",
    "engineering_supervisor", "release_breaker_recovery_manager",
    "engineering_evidence_tools", "todo_engineering_intake", "todo_release_bridge",
    "operational_acceptance_reader", "release_manager_gate", "pmv3_worker_release_gate",
    "change_integration_gate", "documentation_impact_gate",
)
BASE_UNITS = ("jason-support-repair-worker.service", "jason-support-repair-worker.timer")
RECOVERY_UNITS = ("jason-release-breaker-recovery.service", "jason-release-breaker-recovery.timer")


@pytest.fixture
def environment(tmp_path):
    repo = tmp_path / "source"
    home = tmp_path / "home"
    spool = tmp_path / "spool"
    for name in SOURCES:
        src = repo / "tools" / (name + ".py")
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text(name, encoding="utf-8")
    for name in BASE_UNITS + RECOVERY_UNITS:
        src = repo / "infrastructure/openclaw-operations/systemd/user" / name
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("unit: " + name, encoding="utf-8")
    return repo, home, spool


def invoke(environment, args, *, fail_recovery=False):
    repo, home, spool = environment
    calls = []
    def systemctl(argv, **kwargs):
        calls.append((list(argv), kwargs))
        if (fail_recovery and "is-active" in argv
                and argv[-1] == "jason-release-breaker-recovery.timer"):
            raise subprocess.CalledProcessError(3, argv)
        return subprocess.CompletedProcess(argv, 0)
    with patch.object(sys, "argv", ["installer", "--repo", str(repo),
                                   "--spool", str(spool), *args]), \
         patch.object(Path, "home", return_value=home), \
         patch.object(installer.subprocess, "run", side_effect=systemctl):
        installer.main()
    return calls


def test_normal_release_does_not_stage_or_start_recovery(environment):
    _, home, _ = environment
    calls = invoke(environment, ["--activate"])
    unit_root = home / ".config/systemd/user"
    assert all((unit_root / u).is_file() for u in BASE_UNITS)
    assert all(not (unit_root / u).exists() for u in RECOVERY_UNITS)
    assert not any("jason-release-breaker-recovery.timer" in a
                   for a, _ in calls)


def test_recovery_requires_explicit_active_install(environment):
    _, home, _ = environment
    with pytest.raises(SystemExit):
        invoke(environment, ["--activate-breaker-recovery"])
    assert not home.exists()


def test_explicit_recovery_installs_two_units_and_checks_timer(environment):
    repo, home, _ = environment
    calls = invoke(environment, ["--activate", "--activate-breaker-recovery"])
    unit_root = home / ".config/systemd/user"
    for name in RECOVERY_UNITS:
        source = repo / "infrastructure/openclaw-operations/systemd/user" / name
        assert (unit_root / name).read_bytes() == source.read_bytes()
    commands = [a for a, _ in calls]
    assert ["systemctl", "--user", "enable", "--now",
            "jason-release-breaker-recovery.timer"] in commands
    assert ["systemctl", "--user", "is-active", "--quiet",
            "jason-release-breaker-recovery.timer"] in commands


def test_absent_unit_prevents_any_install(environment):
    repo, home, _ = environment
    (repo / "infrastructure/openclaw-operations/systemd/user"
     / "jason-release-breaker-recovery.service").unlink()
    with pytest.raises(SystemExit):
        invoke(environment, ["--activate", "--activate-breaker-recovery"])
    assert not home.exists()


def test_failed_recovery_readback_disables_timer(environment):
    repo, home, spool = environment
    calls = []
    def systemctl(argv, **kwargs):
        calls.append(list(argv))
        if "is-active" in argv and argv[-1] == "jason-release-breaker-recovery.timer":
            raise subprocess.CalledProcessError(3, argv)
        return subprocess.CompletedProcess(argv, 0)
    with patch.object(sys, "argv", ["installer", "--repo", str(repo),
                                   "--spool", str(spool), "--activate",
                                   "--activate-breaker-recovery"]), \
         patch.object(Path, "home", return_value=home), \
         patch.object(installer.subprocess, "run", side_effect=systemctl), \
         pytest.raises(subprocess.CalledProcessError):
        installer.main()
    assert ["systemctl", "--user", "disable", "--now",
            "jason-release-breaker-recovery.timer"] in calls
