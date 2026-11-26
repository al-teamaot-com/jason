"""CCC retirement is source-governed, with independent health retained."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_new_production_desired_state_removes_only_legacy_ccc_scheduler():
    d = json.loads((ROOT / 'config/production-desired-state.json').read_text())
    units = set(d["allowed_system_units"] + d["required_system_units"])
    assert "jason-ccc.service" not in units
    assert "jason-ccc.timer" not in units
    for required in ("jason-openclaw-authority-full-integrity.timer",
                     "jason-openclaw-authority-health.timer",
                     "jason-production-drift-watchdog.timer",
                     "jason-provider-health-canary.timer",
                     "jason-release-control-readback.timer"):
        assert required in d["required_system_units"]


def test_native_health_and_authenticated_owner_are_release_policy_requirements():
    d = json.loads((ROOT / 'config/mobile-release-approval-policy.json').read_text())
    review = d["high_impact_review"]
    assert d["schema_version"] == "3.1"
    assert review["authenticated_entra_owner_decision_required"] is True
    assert review["independent_native_release_health_required"] is True
    assert "independent_ccc_required" not in review
    assert review["owner_exact_sha_required"] is True
    assert review["protected_release_gates_unchanged"] is True


def test_reviewed_open_breaker_profile_binds_only_failed_ccc_unit():
    d = json.loads((ROOT / 'config/open-breaker-recovery-policy.json').read_text())
    matched = [p for p in d["profiles"]
               if p["id"] == "retire_obsolete_ccc_scheduler"]
    assert len(matched) == 1
    p = matched[0]
    assert p["change_class"] == "release_blocker"
    assert p["risk_profile"] == "production_control_core"
    assert p["drift_problems"] == [
        {"kind": "failed_system_unit", "unit": "jason-ccc.service"}
    ]
    assert p["max_changed_files"] <= 16
    assert p["runtime_health"] == {"mode": "healthy"}
    assert set(p["required_changed_files"]) == {
        "config/production-desired-state.json",
        "tools/reconcile_managed_unit_delta.py",
        "config/mobile-release-approval-policy.json",
    }


def test_immutable_host_reconciler_owns_unit_retirement_and_rollback_archive():
    source = (ROOT / "tools/reconcile_production_host_services.sh").read_text()
    assert "release_owned_unit_delta" in source
    assert 'SYSTEM_UNIT_DELTA="$BACKUP_DIR/release-system-unit-delta.txt"' in source
    assert 'cp -a "/etc/systemd/system/$unit" "$BACKUP_DIR/system-$unit.before"' in source
    assert 'systemctl disable --now "$unit"' in source
    assert 'rm -f -- "/etc/systemd/system/$unit"' in source
    assert "install_ccc_scheduler.sh" not in source


def test_ccc_not_a_live_deployment_certification_dependency():
    source = (ROOT / "tools/release_manager_host_runner.py").read_text()
    # Historical CCC verifier remains for reading forensic evidence; the new
    # normal release contract does not invoke it as an admission gate.
    start = source.index("def execute_release(") if "def execute_release(" in source else None
    assert "native_pre_mutation_gate" in source
    assert "native_post_mutation_gate" in source
    assert source.count("run_release_ccc_gate(") == 1
    assert "require_current_protected_release_source" in source
