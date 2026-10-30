"""Real host ordering regression: install user timer before final drift guard."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('tested_offer_unit_installer', ROOT/'tools/install_release_manager.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
TIMER = 'jason-release-approval-only.timer'
SERVICE = 'jason-release-approval-only.service'


def setup_installer(tmp_path, monkeypatch, timer=True, service=True):
    source = tmp_path/'source'
    (source/'config').mkdir(parents=True)
    (source/'config/production-desired-state.json').write_text(json.dumps({
        'required_user_units': [TIMER] if timer else [],
        'allowed_user_units': [SERVICE] if service else [],
    }))
    units=source/'infrastructure/openclaw-operations/systemd/user'
    units.mkdir(parents=True)
    for name in (TIMER,SERVICE): (units/name).write_text('reviewed '+name)
    unit_dir=tmp_path/'units'
    lib=tmp_path/'lib';lib.mkdir()
    (lib/'release_manager_host_runner.py').write_text('unchanged running controller')
    (lib/'release-manager-source').symlink_to(source)
    monkeypatch.setattr(m,'ROOT',source)
    monkeypatch.setattr(m,'UNIT_DIR',unit_dir)
    monkeypatch.setattr(m,'LIB',lib)
    monkeypatch.setattr(m.os,'geteuid',lambda:1000)
    return unit_dir,lib


def test_unit_only_mode_installs_pair_but_never_replaces_running_controller(monkeypatch,tmp_path):
    units,lib=setup_installer(tmp_path,monkeypatch)
    with patch('sys.argv',['installer','--approval-units-only','--activate']), patch.object(m.subprocess,'run') as run:
        assert m.main()==0
    assert (units/TIMER).read_text()=='reviewed '+TIMER
    assert (units/SERVICE).read_text()=='reviewed '+SERVICE
    assert (lib/'release_manager_host_runner.py').read_text()=='unchanged running controller'
    assert (lib/'release-manager-source').is_symlink()
    commands=[call.args[0] for call in run.call_args_list]
    assert commands==[
        ['systemctl','--user','daemon-reload'],
        ['systemctl','--user','enable','--now',TIMER],
        ['systemctl','--user','is-active','--quiet',TIMER],
    ]
    assert all('jason-release-manager.timer' not in cmd for cmd in commands)


@pytest.mark.parametrize('timer,service',[(True,False),(False,True)])
def test_half_pair_refuses_before_copy_or_systemctl(monkeypatch,tmp_path,timer,service):
    units,_=setup_installer(tmp_path,monkeypatch,timer,service)
    with patch.object(m.subprocess,'run') as run:
        with pytest.raises(RuntimeError,match='incomplete'):
            m.install_approval_only_units(activate=True)
        run.assert_not_called()
    assert not units.exists()


def test_bootstrap_without_pair_does_not_change_units(monkeypatch,tmp_path):
    units,_=setup_installer(tmp_path,monkeypatch,False,False)
    with patch.object(m.subprocess,'run') as run:
        assert m.install_approval_only_units(activate=True) is False
        run.assert_not_called()
    assert not units.exists()


def test_host_installs_pair_after_staging_before_required_commit_and_drift():
    host=(ROOT/'tools/reconcile_production_host_services.sh').read_text()
    stages=['step_start protected_root_policy_stage','step_start held_approval_user_unit_install',
            'step_start root_release_transition_install','step_start production_drift_guard']
    positions=[host.index(stage) for stage in stages]
    assert positions==sorted(positions)
    between=host[positions[1]:positions[2]]
    assert 'run_as_al /usr/bin/python3 "$RELEASE_DIR/tools/install_release_manager.py"' in between
    assert '--approval-units-only --activate' in between
    assert 'promote' not in between
