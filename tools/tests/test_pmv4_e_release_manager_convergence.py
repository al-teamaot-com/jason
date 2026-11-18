"""PMv4 E Release Manager convergence must never reinstall PMv3 after retirement.

Source-only tests; no privileged/systemd/provider mutation.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import release_manager_host_runner as runner


def test_before_cutover_legacy_selection_is_nonmutating(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "PMV4_E_ACCEPTED_MARKER", tmp_path / "absent")
    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **kw: pytest.fail("unexpected call"))
    assert runner.pmv4_e_scheduling_mode() == "legacy"


def _install_synthetic_marker_and_guard(tmp_path, monkeypatch):
    marker = tmp_path / "accepted.json"
    marker.write_text("{}")
    monkeypatch.setattr(runner, "PMV4_E_ACCEPTED_MARKER", marker)
    # Installed /usr/bin/python3 is root-owned and not group/world writable.
    # The command itself is mocked, so no real unit guard is invoked.
    monkeypatch.setattr(runner, "PMV4_E_UNIT_GUARD", Path("/usr/bin/python3"))
    return marker


def test_after_cutover_acceptance_uses_root_installed_guard_only(tmp_path, monkeypatch):
    _install_synthetic_marker_and_guard(tmp_path, monkeypatch)
    calls = []
    proof = {
        "status":"accepted_for_one_configured_service",
        "role":"component-release", "unit":"jason-pmv4-component-release.timer",
        "owner_authority_issued":False, "production_changes_performed":False,
    }
    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        return SimpleNamespace(returncode=0,stdout=json.dumps(proof),stderr="")
    monkeypatch.setattr(runner.subprocess,"run",fake_run)
    assert runner.pmv4_e_scheduling_mode()=="replacement"
    assert calls[0][0][:3]==["/usr/bin/python3","-I","-B"]
    assert calls[0][0][-2:]==["--mode","component-release"]


@pytest.mark.parametrize("result", [
    SimpleNamespace(returncode=255,stdout="",stderr="denied"),
    SimpleNamespace(returncode=0,stdout="not-json",stderr=""),
    SimpleNamespace(returncode=0,stdout='{"status":"accepted_for_one_configured_service","role":"engineering"}',stderr=""),
])
def test_present_but_invalid_acceptance_denied_no_legacy_fallback(tmp_path,monkeypatch,result):
    _install_synthetic_marker_and_guard(tmp_path,monkeypatch)
    monkeypatch.setattr(runner.subprocess,"run",lambda *a,**kw:result)
    with pytest.raises(runner.ReleaseManagerError,match="PMv4 E"):
        runner.pmv4_e_scheduling_mode()


def test_replacement_alignment_checks_six_new_and_six_old_controls(monkeypatch):
    monkeypatch.setattr(runner,"pmv4_e_scheduling_mode",lambda:"replacement")
    required=set(runner.PMV4_E_USER_TIMERS+runner.PMV4_E_ROOT_TRIGGERS+runner.SYSTEM_CONTROL_TIMERS)
    calls=[]
    def active(unit, *, user):
        calls.append((unit,user))
        return unit in required
    monkeypatch.setattr(runner,"unit_active",active)
    result=runner.scheduled_control_alignment()
    assert all(result[u]=="active" for u in required)
    assert all(result[u]=="inactive" for u in runner.PMV4_E_RETIRED_USER+runner.PMV4_E_RETIRED_ROOT)
    assert len(calls)==len(required)+6


def test_old_timer_reactivation_is_a_blocking_duplicate_claim(monkeypatch):
    monkeypatch.setattr(runner,"pmv4_e_scheduling_mode",lambda:"replacement")
    required=set(runner.PMV4_E_USER_TIMERS+runner.PMV4_E_ROOT_TRIGGERS+runner.SYSTEM_CONTROL_TIMERS)
    required.add("jason-release-manager.timer")
    monkeypatch.setattr(runner,"unit_active",lambda unit,*,user:unit in required)
    with pytest.raises(runner.ReleaseManagerError,match="retired user control still active"):
        runner.scheduled_control_alignment()


def test_missing_replacement_timer_denies_even_if_legacy_timer_active(monkeypatch):
    monkeypatch.setattr(runner,"pmv4_e_scheduling_mode",lambda:"replacement")
    required=set(runner.PMV4_E_USER_TIMERS+runner.PMV4_E_ROOT_TRIGGERS+runner.SYSTEM_CONTROL_TIMERS)
    required.remove("jason-pmv4-component-release.timer")
    required.add("jason-release-manager.timer")
    monkeypatch.setattr(runner,"unit_active",lambda unit,*,user:unit in required)
    with pytest.raises(runner.ReleaseManagerError,match="required user control"):
        runner.scheduled_control_alignment()


def test_legacy_timers_still_required_prior_to_acceptance(monkeypatch):
    monkeypatch.setattr(runner,"pmv4_e_scheduling_mode",lambda:"legacy")
    required=set(runner.USER_CONTROL_TIMERS+runner.SYSTEM_CONTROL_TIMERS)
    monkeypatch.setattr(runner,"unit_active",lambda unit,*,user:unit in required)
    assert set(runner.scheduled_control_alignment())==required


def test_accepted_release_manager_path_never_runs_legacy_installer():
    source=(Path(__file__).resolve().parents[2]/"tools/release_manager_host_runner.py").read_text()
    start=source.index("def install_release_manager_from_current(")
    end=source.index("_PREPROD_OPENCLAW_EXCLUDED",start)
    region=source[start:end]
    assert region.index('if pmv4_e_scheduling_mode() == "replacement":') < region.index('installer = current / "tools" / "install_release_manager.py"')
    assert "no legacy installer fallback" in region
    assert 'scheduled_control_alignment()' in region
