"""Native Release Manager integration acceptance for Workboard's protected surface.

These tests remain source-only: no release, Docker, Teams card, or service restart.
"""
import importlib.util
import json
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]


def module_from(name, filename):
    spec = importlib.util.spec_from_file_location(name, TOOLS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_bootstrap_source_profile_is_explicitly_off():
    declaration = json.loads(
        (TOOLS.parent / "config" / "openclaw-workboard-activation.json").read_text()
    )
    assert declaration == {"schema_version": "1.0", "profile": "off"}


def test_workboard_release_scope_is_protected_core():
    runner = module_from("workboard_native_runner", "release_manager_host_runner.py")
    for file in (
        "config/openclaw-workboard-activation.json",
        "tools/openclaw_workboard_release_surface.py",
        "tools/openclaw_workboard_release_scope.py",
    ):
        assert runner.classify_change_risk("feature", [file]) == "production_control_core"


def test_release_controller_source_integrates_preflight_native_transaction_and_rollback():
    source = (TOOLS / "release_manager_host_runner.py").read_text()
    assert "workboard_surface.plan(candidate_tree)" in source
    assert "workboard_surface.plan(deploy_worktree)" in source
    assert "workboard_surface.activate(" in source
    assert "workboard_surface.verify_active(" in source
    assert source.count("workboard_surface.rollback(") == 2
    assert "workboard_attempted = True" in source
    assert '"openclaw_workboard" = "unverified"' not in source
    assert 'recovery_steps["openclaw_workboard"] = "unverified"' in source


def test_installer_requires_full_release_controller_and_companion_pair():
    installer = (TOOLS / "install_release_manager.py").read_text()
    runner = (TOOLS / "release_manager_host_runner.py").read_text()
    for file in ("openclaw_workboard_release_scope.py", "openclaw_workboard_release_surface.py"):
        assert f'ROOT / "tools" / "{file}"' in installer
        assert f'"{file}"' in runner
    assert "installed Workboard release companion differs from host release" in runner


def test_no_standalone_mutation_entrypoint():
    surface = (TOOLS / "openclaw_workboard_release_surface.py").read_text()
    # Module is invoked only by the native transaction; no release CLI on its own.
    assert 'if __name__ == "__main__"' not in surface
    assert "approve_release" not in surface
    assert "openclaw workboard dispatch" not in surface
    assert "--no-build" in surface
