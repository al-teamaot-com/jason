"""Bounded CCC-only repair leaves production authorization and freeze intact."""
import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import patch
import pytest

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "tools/owner_single_step_v2_ccc_recovery.py"


def load():
    spec = importlib.util.spec_from_file_location("one_time_ccc_recovery", P)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def state(*, breaker_state="open", problem="jason-ccc.service"):
    data = {"last_known_good": {"manifest": {
        "revision": "c43e88e072c0b35c5b342d5e712fe34565b3e0cd"}},
        "circuit_breaker": {"state": breaker_state,
            "source": "production_drift_watchdog",
            "reason": "continuous_production_drift_detected"}}
    drift = {"schema_version":"1.0", "status":"drift_detected",
             "problems":[{"kind":"failed_system_unit","state":"failed","unit":problem}]}
    return data, drift


def test_exact_legacy_ccc_units_only():
    m = load()
    assert m.UNITS == ("jason-ccc.timer", "jason-ccc.service")
    assert m.LKG == "c43e88e072c0b35c5b342d5e712fe34565b3e0cd"
    assert m.FAILED_LKG == "aa6fa38a29b803e11ada63afb3cf25d17b7daf44"


def test_non_root_cannot_mutate_systemd_or_breaker():
    m = load()
    with patch.object(m.os, "geteuid", return_value=1000), \
         patch.object(m, "command", side_effect=AssertionError("no systemd action")):
        with pytest.raises(PermissionError, match="authenticated local sudo"):
            m.recover_ccc()


@pytest.mark.parametrize("breaker_state,problem", [
    ("closed", "jason-ccc.service"),
    ("open", "jason-not-ccc.service"),
    ("other", "jason-ccc.service"),
])
def test_unreviewed_root_drift_never_passes(breaker_state, problem):
    m = load()
    baseline, drift = state(breaker_state=breaker_state, problem=problem)
    with patch.object(m.rootctl, "protected_read", side_effect=[baseline,drift]), \
         patch.object(m, "command", side_effect=AssertionError("no systemd mutation")):
        with pytest.raises(ValueError):
            m.validate_baseline()


@pytest.mark.parametrize("policy", [
    {"schema_version":"1.0","allowed_system_units":["jason-ccc.service"],
     "required_system_units":[]},
    {"schema_version":"1.0","allowed_system_units":[
        "jason-ccc.timer","jason-ccc.service"],
     "required_system_units":["jason-ccc.service"]},
    {"schema_version":"0.9","allowed_system_units":[
        "jason-ccc.timer","jason-ccc.service"],"required_system_units":[]},
])
def test_root_policy_denies_missing_required_or_wrong_schema(policy):
    m = load()
    baseline, drift = state()
    with patch.object(m.rootctl, "protected_read", side_effect=[baseline,drift]), \
         patch.object(m, "exact_file", return_value=json.dumps(policy).encode()), \
         patch.object(m, "command", side_effect=AssertionError("no mutation")):
        with pytest.raises(ValueError, match="root desired-state policy"):
            m.validate_baseline()


def test_untrusted_file_symlink_rejected(tmp_path):
    m = load()
    target = tmp_path / "regular"
    target.write_bytes(b"secret")
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(PermissionError, match="unsafe protected file"):
        m.exact_file(link, owner=os.getuid())


def test_freeze_requires_original_owner_and_mode(tmp_path):
    m = load()
    f = tmp_path / "production-deployment-freeze"
    f.write_bytes(b"frozen")
    f.chmod(0o644)
    with patch.object(m, "FREEZE", f):
        with pytest.raises(PermissionError, match="freeze ownership/mode"):
            m.freeze_snapshot()


def test_restore_units_rebuilds_exact_archived_files_only(tmp_path):
    m = load()
    installed = tmp_path / "system"
    archive = tmp_path / "archive"
    installed.mkdir()
    archive.mkdir()
    for name in m.UNITS:
        (archive/name).write_bytes(("OLD_"+name).encode())
    calls = []
    with patch.object(m, "SYSTEM_UNITS", installed), \
         patch.object(m.os, "chown"), \
         patch.object(m, "command", side_effect=lambda *args, **kwargs:
                      calls.append(args) or type("R", (), {"returncode":0})()), \
         patch.object(m.rootctl, "write_json") as update:
        m.restore_units(archive, True)
    assert all((installed/u).read_bytes() == (archive/u).read_bytes() for u in m.UNITS)
    assert ("systemctl","daemon-reload") in calls
    assert ("systemctl","enable","--now","jason-ccc.timer") in calls
    update.assert_not_called()


def test_do_not_accept_production_release_or_silent_breaker_bypass():
    content = P.read_text()
    assert 'rootctl.refresh_stale_drift()' in content
    assert 'rootctl.apply_transition(' in content
    assert '"action":"revalidate","revision":LKG' in content
    assert 'rootctl.verify_immutable_lkg_fingerprint(' in content
    assert 'rootctl.write_json(CONTROL, updated, 0, 0)' in content
    assert 'no_standing_authority' in content or 'no_standing_authority' in content.lower()
    assert 'release_manager.promote' not in content
    assert 'jason-runtime' not in content or "runtime_or_mcp_restarted" in content


def test_restore_units_refreshes_actual_drift_not_old_snapshot(tmp_path):
    m = load()
    installed = tmp_path / "system"
    archive = tmp_path / "archive"
    installed.mkdir()
    archive.mkdir()
    for name in m.UNITS:
        (archive/name).write_bytes(("OLD_"+name).encode())
    calls=[]
    with patch.object(m,"SYSTEM_UNITS",installed), \
         patch.object(m.os,"chown"), \
         patch.object(m,"command",side_effect=lambda *args,**kw:
                      calls.append(args) or type("R",(),{"returncode":0})()), \
         patch.object(m.rootctl,"refresh_stale_drift") as refresh, \
         patch.object(m.rootctl,"write_json") as write:
        m.restore_units(archive,True)
    refresh.assert_called_once_with()
    write.assert_not_called()
    assert all((installed/u).read_bytes()==(archive/u).read_bytes() for u in m.UNITS)


def test_restore_units_never_overwrites_drift_when_refresh_fails(tmp_path):
    m = load()
    installed = tmp_path / "system"
    archive = tmp_path / "archive"
    installed.mkdir()
    archive.mkdir()
    drift = {"schema_version":"1.0","status":"drift_detected",
             "problems":[{"kind":"failed_system_unit","unit":"jason-ccc.service","state":"failed"}]}
    for name in m.UNITS:
        (archive/name).write_bytes(("OLD_"+name).encode())
    calls=[]
    with patch.object(m,"SYSTEM_UNITS",installed), \
         patch.object(m.os,"chown"), \
         patch.object(m,"command",side_effect=lambda *args,**kw:
                      calls.append(args) or type("R",(),{"returncode":0})()), \
         patch.object(m.rootctl,"refresh_stale_drift",side_effect=RuntimeError("other drift")), \
         patch.object(m.rootctl,"write_json") as write:
        m.restore_units(archive,True)
    write.assert_not_called()
    assert drift["status"]=="drift_detected"
    assert all((installed/u).read_bytes()==(archive/u).read_bytes() for u in m.UNITS)
