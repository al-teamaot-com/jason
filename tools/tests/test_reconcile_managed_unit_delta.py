"""Unit-delta regression is wholly isolated in pytest's temporary paths."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[1] / "reconcile_managed_unit_delta.py"
SPEC = importlib.util.spec_from_file_location("reconcile_managed_unit_delta", MODULE)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def setup_releases(tmp_path):
    root = tmp_path / "releases"
    candidate = root / ("a" * 40)
    target = root / ("b" * 40)
    sysd = tmp_path / "etc-systemd"
    userd = tmp_path / "user-systemd"
    for p in (candidate, target):
        (p / "config").mkdir(parents=True)
        (p / "infrastructure/openclaw-operations/systemd/user").mkdir(parents=True)
        (p / "infrastructure/showcase/systemd").mkdir(parents=True)
    sysd.mkdir()
    userd.mkdir()
    return root, candidate, target, sysd, userd


def manifest(release, *, system=(), user=()):
    (release / "config/production-desired-state.json").write_text(json.dumps({
        "schema_version": "1.0",
        "required_system_units": list(system),
        "allowed_system_units": [],
        "required_user_units": list(user),
        "allowed_user_units": [],
    }))


def test_candidate_only_system_timer_is_selected_without_actions(tmp_path):
    root, candidate, target, installed, user = setup_releases(tmp_path)
    unit = "jason-new-monitor.timer"
    manifest(candidate, system=(unit, "jason-shared.service"))
    manifest(target, system=("jason-shared.service",))
    content = "[Unit]\nDescription=Safe synthetic candidate timer\n"
    (candidate / "infrastructure/showcase/systemd" / unit).write_text(content)
    (installed / unit).write_text(content)
    plan = mod.plan_unit_removals(candidate, target, installed, scope="system")
    assert plan == [unit]
    assert (installed / unit).exists()  # planner has no side effects


def test_target_declared_shared_unit_cannot_be_removed(tmp_path):
    root, candidate, target, installed, user = setup_releases(tmp_path)
    manifest(candidate, system=("jason-critical.service",))
    manifest(target, system=("jason-critical.service",))
    (installed / "jason-critical.service").write_text("valuable")
    assert mod.plan_unit_removals(candidate, target, installed, scope="system") == []


def test_modified_candidate_unit_fails_closed(tmp_path):
    root, candidate, target, installed, user = setup_releases(tmp_path)
    manifest(candidate, system=("jason-new.service",))
    manifest(target)
    (candidate / "infrastructure/showcase/systemd/jason-new.service").write_text("expected")
    (installed / "jason-new.service").write_text("different")
    with pytest.raises(mod.UnitDeltaError, match="differs"):
        mod.plan_unit_removals(candidate, target, installed, scope="system")


def test_missing_immutable_candidate_definition_fails_closed(tmp_path):
    root, candidate, target, installed, user = setup_releases(tmp_path)
    manifest(candidate, system=("jason-new.service",))
    manifest(target)
    (installed / "jason-new.service").write_text("installed")
    with pytest.raises(mod.UnitDeltaError, match="exactly one immutable"):
        mod.plan_unit_removals(candidate, target, installed, scope="system")


def test_symlink_or_unsafe_unit_never_planned(tmp_path):
    root, candidate, target, installed, user = setup_releases(tmp_path)
    manifest(candidate, system=("jason-new.service",))
    manifest(target)
    (candidate / "infrastructure/showcase/systemd/jason-new.service").write_text("installed")
    (installed / "jason-new.service").symlink_to(
        candidate / "infrastructure/showcase/systemd/jason-new.service"
    )
    with pytest.raises(mod.UnitDeltaError, match="symlink"):
        mod.plan_unit_removals(candidate, target, installed, scope="system")
    manifest(candidate, system=("jason-bad/../../etc/passwd",))
    with pytest.raises(mod.UnitDeltaError, match="invalid"):
        mod.plan_unit_removals(candidate, target, installed, scope="system")


def test_user_unit_delta_uses_user_definition(tmp_path):
    root, candidate, target, installed, user = setup_releases(tmp_path)
    manifest(candidate, user=("jason-new-queue.timer",))
    manifest(target)
    definition = "[Timer]\nOnCalendar=hourly\n"
    (candidate / "infrastructure/openclaw-operations/systemd/user/jason-new-queue.timer").write_text(definition)
    (user / "jason-new-queue.timer").write_text(definition)
    assert mod.plan_unit_removals(candidate, target, user, scope="user") == ["jason-new-queue.timer"]


def test_bounded_delta_rejects_bulk_unit_removal(tmp_path):
    root, candidate, target, installed, user = setup_releases(tmp_path)
    manifest(candidate, system=tuple(f"jason-new-{i}.service" for i in range(9)))
    manifest(target)
    with pytest.raises(mod.UnitDeltaError, match="too many"):
        mod.plan_unit_removals(candidate, target, installed, scope="system")


def test_pinned_revision_cannot_resolve_outside_immutable_root(tmp_path):
    root, candidate, target, installed, user = setup_releases(tmp_path)
    assert mod.pinned_release(candidate, root) == candidate
    with pytest.raises(mod.UnitDeltaError, match="exact immutable"):
        mod.pinned_release(tmp_path / "elsewhere", root)


def test_installed_unit_missing_does_not_require_removal(tmp_path):
    root, candidate, target, installed, user = setup_releases(tmp_path)
    manifest(candidate, system=("jason-new.timer",))
    manifest(target)
    assert mod.plan_unit_removals(candidate, target, installed, scope="system") == []


def test_installed_unit_file_owner_wrong_denied_before_deletion(tmp_path):
    import os
    root, candidate, target, installed, user = setup_releases(tmp_path)
    manifest(candidate, system=("jason-new.timer",))
    manifest(target)
    content = "[Unit]\nDescription=Unit owned incorrectly\n"
    (candidate / "infrastructure/showcase/systemd/jason-new.timer").write_text(content)
    (installed / "jason-new.timer").write_text(content)
    if os.geteuid() != 0:
        with pytest.raises(mod.UnitDeltaError, match="unexpected owner"):
            mod.plan_unit_removals(
                candidate, target, installed, scope="system", enforce_owner=True,
            )


def test_duplicate_candidate_unit_definition_fails_closed(tmp_path):
    root, candidate, target, installed, user = setup_releases(tmp_path)
    manifest(candidate, system=("jason-new.timer",))
    manifest(target)
    (candidate / "infrastructure/openclaw-operations/systemd").mkdir(exist_ok=True)
    for folder in (
        "infrastructure/openclaw-operations/systemd",
        "infrastructure/showcase/systemd",
    ):
        (candidate / folder / "jason-new.timer").write_text("duplicate")
    (installed / "jason-new.timer").write_text("duplicate")
    with pytest.raises(mod.UnitDeltaError, match="exactly one immutable"):
        mod.plan_unit_removals(candidate, target, installed, scope="system")


def test_triggering_units_are_removed_before_services(tmp_path):
    root, candidate, target, installed, user = setup_releases(tmp_path)
    units = ("jason-new.service", "jason-new.timer", "jason-new.path")
    manifest(candidate, system=units)
    manifest(target)
    for unit in units:
        content = f"[Unit]\nDescription={unit}\n"
        (candidate / "infrastructure/showcase/systemd" / unit).write_text(content)
        (installed / unit).write_text(content)
    assert mod.plan_unit_removals(candidate, target, installed, scope="system") == [
        "jason-new.path", "jason-new.timer", "jason-new.service"
    ]


def test_immutable_revision_alias_symlink_cannot_masquerade_as_different_sha(tmp_path):
    root, candidate, target, installed, user = setup_releases(tmp_path)
    alias = root / ("c" * 40)
    alias.symlink_to(candidate, target_is_directory=True)
    with pytest.raises(mod.UnitDeltaError, match="exact immutable"):
        mod.pinned_release(alias, root)


def test_unit_delta_cli_denies_unprivileged_execution(tmp_path):
    import os
    import subprocess
    import sys
    if os.geteuid() == 0:
        pytest.skip("non-root denial exercised on the regular runner")
    root, candidate, target, installed, user = setup_releases(tmp_path)
    manifest(candidate)
    manifest(target)
    result = subprocess.run(
        [
            sys.executable, str(MODULE), "--release-root", str(root),
            "--candidate", str(candidate), "--target", str(target),
            "--scope", "system", "--installed-dir", str(installed),
        ],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert "root host reconciliation is required" in result.stderr
