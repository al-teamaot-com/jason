"""Stage B root-policy, installer ordering, and held-only offer guard contracts."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "reviewed_stage_b_root_migrator",
    ROOT / "tools/protected_root_policy_migration.py",
)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def test_stage_b_declares_exactly_one_reviewed_user_unit_plan():
    # Accept both exact stages: bootstrap (units absent) and reviewed Stage B
    # (units declared together). Always compare against the original baseline.
    observed = json.loads((ROOT / "config/production-desired-state.json").read_text())
    timer = "jason-release-approval-only.timer"
    service = "jason-release-approval-only.service"
    timer_present = timer in observed["required_user_units"]
    service_present = service in observed["allowed_user_units"]
    assert timer_present == service_present, "approval timer/service must be declared together"

    if timer_present:
        stage_b = observed
        stage_a = {
            **observed,
            "required_user_units": [x for x in observed["required_user_units"] if x != timer],
            "allowed_user_units": [x for x in observed["allowed_user_units"] if x != service],
        }
    else:
        stage_a = observed
        stage_b = {
            **observed,
            "required_user_units": observed["required_user_units"] + [timer],
            "allowed_user_units": observed["allowed_user_units"] + [service],
        }

    assert migration._planned_delta(stage_a, stage_b) == migration.APPROVED_HELD_OFFER_DELTA
    assert migration.APPROVED_HELD_OFFER_DELTA["required_system_units"] == frozenset()
    assert migration.APPROVED_HELD_OFFER_DELTA["allowed_system_units"] == frozenset()

    for wrong in (
        {**stage_b, "allowed_user_units": stage_a["allowed_user_units"]},
        {**stage_b, "required_user_units": stage_a["required_user_units"]},
        {**stage_b, "allowed_system_units": stage_b["allowed_system_units"] + ["jason-unsafe.service"]},
    ):
        with pytest.raises(migration.MigrationRefused):
            migration._planned_delta(stage_a, wrong)
    with pytest.raises(migration.MigrationRefused):
        migration._planned_delta(stage_b, stage_a)


def test_stage_b_root_scripts_run_exact_plan_stage_before_install_and_apply_after():
    stage = (ROOT / "tools/install_release_host_reconciler.py").read_text()
    apply = (ROOT / "tools/install_release_control_transition.py").read_text()
    host = (ROOT / "tools/reconcile_production_host_services.sh").read_text()
    assert "migration.UNIT_FIELDS" in stage and "migration.UNIT_FIELDS" in apply
    assert "migration.stage_for_candidate(candidate, baseline)" in stage
    assert "migration.apply_for_candidate(candidate,baseline)" in apply
    assert "jason-openclaw-authority-full-integrity.timer" not in stage
    assert "jason-openclaw-authority-full-integrity.timer" not in apply
    assert host.index("step_start protected_root_policy_stage") < host.index(
        "step_start system_service_activation"
    )
    assert host.index("step_start system_service_activation") < host.index(
        "step_start root_release_transition_install"
    )


def test_owner_offer_timer_is_held_only_and_not_promotion():
    unit = (ROOT / "infrastructure/openclaw-operations/systemd/user/jason-release-approval-only.service").read_text()
    timer = (ROOT / "infrastructure/openclaw-operations/systemd/user/jason-release-approval-only.timer").read_text()
    assert "ConditionPathExists=/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold" in unit
    starts = [line for line in unit.splitlines() if line.startswith("ExecStart=")]
    assert len(starts) == 1 and starts[0].endswith("approval-only-held")
    assert "promote" not in starts[0]
    assert "Unit=jason-release-approval-only.service" in timer
    installer = (ROOT / "tools/install_release_manager.py").read_text()
    assert "if approval_timer_declared != approval_service_declared:" in installer
    assert 'timers.append("jason-release-approval-only.timer")' in installer
    held = (ROOT / "infrastructure/openclaw-operations/systemd/user/jason-release-manager.service").read_text()
    assert "promote-eligible" in held
