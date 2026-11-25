"""Real host ordering regression: install user timer before final drift guard."""
from __future__ import annotations
import importlib.util
import json
import subprocess
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
    override=units/'jason-release-approval-only.service.d'/m.APPROVAL_OVERRIDE
    override.parent.mkdir(parents=True)
    override.write_bytes((ROOT/'infrastructure/openclaw-operations/systemd/user'
                         /'jason-release-approval-only.service.d'/m.APPROVAL_OVERRIDE).read_bytes())
    unit_dir=tmp_path/'units'
    unit_dir.mkdir()
    lib=tmp_path/'lib';lib.mkdir()
    (lib/'release_manager_host_runner.py').write_text('unchanged running controller')
    (lib/'release-manager-source').symlink_to(source)
    monkeypatch.setattr(m,'ROOT',source)
    monkeypatch.setattr(m,'UNIT_DIR',unit_dir)
    monkeypatch.setattr(m,'LIB',lib)
    monkeypatch.setattr(m,'ensure_authoritative_approval_worktree',lambda:None)
    monkeypatch.setattr(m.os,'geteuid',lambda:1000)
    return unit_dir,lib


def test_unit_only_mode_installs_pair_but_never_replaces_running_controller(monkeypatch,tmp_path):
    units,lib=setup_installer(tmp_path,monkeypatch)
    with patch('sys.argv',['installer','--approval-units-only','--activate']), patch.object(m.subprocess,'run') as run:
        assert m.main()==0
    assert (units/TIMER).read_text()=='reviewed '+TIMER
    assert (units/SERVICE).read_text()=='reviewed '+SERVICE
    assert (units/(SERVICE+'.d')/m.APPROVAL_OVERRIDE).read_bytes() == (ROOT/'infrastructure/openclaw-operations/systemd/user'/ (SERVICE+'.d')/m.APPROVAL_OVERRIDE).read_bytes()
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
    assert list(units.iterdir()) == []


def test_bootstrap_without_pair_does_not_change_units(monkeypatch,tmp_path):
    units,_=setup_installer(tmp_path,monkeypatch,False,False)
    with patch.object(m.subprocess,'run') as run:
        assert m.install_approval_only_units(activate=True) is False
        run.assert_not_called()
    assert list(units.iterdir()) == []


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


def _git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _configured_real_repo(tmp_path, monkeypatch):
    source=tmp_path/'canonical-project'
    source.mkdir()
    subprocess.run(['git','init','-q','-b','main',str(source)],check=True)
    _git(source,'config','user.email','tests@example.invalid')
    _git(source,'config','user.name','Test Owner')
    (source/'tools').mkdir()
    (source/'tools/manual_release_scope.py').write_text('reviewed scope')
    _git(source,'add','tools/manual_release_scope.py')
    _git(source,'commit','-qm','baseline scope reviewer')
    bare=tmp_path/'bare-origin.git'
    subprocess.run(['git','init','--bare','-q',str(bare)],check=True)
    _git(source,'remote','add','origin',str(bare))
    _git(source,'push','-q','-u','origin','main')
    _git(source,'fetch','origin','main')
    sha=_git(source,'rev-parse','HEAD')
    worktree=tmp_path/'authorized-approval-source'
    monkeypatch.setattr(m,'SOURCE_REPO',source)
    monkeypatch.setattr(m,'APPROVAL_WORKTREE',worktree)
    monkeypatch.setattr(m,'ROOT',tmp_path/'immutable'/sha)
    return source,worktree,sha


def test_approval_worktree_uses_shared_registry_and_is_idempotent(tmp_path,monkeypatch):
    source,target,sha=_configured_real_repo(tmp_path,monkeypatch)
    m.ensure_authoritative_approval_worktree()
    assert _git(target,'rev-parse','HEAD')==sha
    assert m._git_common_dir(target)==m._git_common_dir(source)
    m.ensure_authoritative_approval_worktree()
    assert _git(target,'rev-parse','HEAD')==sha
    assert len([x for x in _git(source,'worktree','list','--porcelain').splitlines()
                if x.startswith('worktree ')])==2


def test_approval_worktree_does_not_discard_unfinished_work(tmp_path,monkeypatch):
    _,target,_=_configured_real_repo(tmp_path,monkeypatch)
    m.ensure_authoritative_approval_worktree()
    (target/'local-operator-work.txt').write_text('preserve me')
    with pytest.raises(RuntimeError,match='uncommitted changes'):
        m.ensure_authoritative_approval_worktree()
    assert (target/'local-operator-work.txt').read_text()=='preserve me'


def test_approval_worktree_refuses_isolated_git_clone(tmp_path,monkeypatch):
    source,target,_=_configured_real_repo(tmp_path,monkeypatch)
    subprocess.run(['git','clone','-q',str(source),str(target)],check=True)
    with pytest.raises(RuntimeError,match='not in authoritative Git registry'):
        m.ensure_authoritative_approval_worktree()
    assert target.is_dir()


def test_approval_worktree_updates_exact_sha_without_new_registry_entry(tmp_path,monkeypatch):
    source,target,_=_configured_real_repo(tmp_path,monkeypatch)
    m.ensure_authoritative_approval_worktree()
    (source/'tools/manual_release_scope.py').write_text('next reviewed source')
    _git(source,'add','tools/manual_release_scope.py')
    _git(source,'commit','-qm','next reviewed candidate')
    _git(source,'push','-q','origin','main')
    new_sha=_git(source,'rev-parse','HEAD')
    monkeypatch.setattr(m,'ROOT',tmp_path/'immutable'/new_sha)
    m.ensure_authoritative_approval_worktree()
    assert _git(target,'rev-parse','HEAD')==new_sha
    assert len([x for x in _git(source,'worktree','list','--porcelain').splitlines()
                if x.startswith('worktree ')])==2


def test_approval_worktree_rejects_unreviewed_source_revision(tmp_path,monkeypatch):
    _,target,_=_configured_real_repo(tmp_path,monkeypatch)
    monkeypatch.setattr(m,'ROOT',tmp_path/'immutable'/'not-a-sha')
    with pytest.raises(RuntimeError,match='exact immutable release SHA'):
        m.ensure_authoritative_approval_worktree()
    assert not target.exists()



def test_frozen_baseline_rollback_restores_old_unit_but_effective_source_stays_canonical(
        tmp_path, monkeypatch):
    """Old LKG overwrites base service, but its installer never clears drop-ins."""
    units, lib=setup_installer(tmp_path,monkeypatch)
    with patch.object(m.subprocess,'run'):
        assert m.install_approval_only_units(activate=False)
    base=units/SERVICE
    stable=units/(SERVICE+'.d')/m.APPROVAL_OVERRIDE
    canonical=stable.read_bytes()
    # Simulate full pre-existing baseline reconciliation byte-for-byte.
    prior=(ROOT/'tools/tests/fixtures/pmv31_baseline_approval_only_unit_ee8d0652.service').read_text()
    assert 'engineering-worker-source' in prior
    assert 'ConditionPathExists=/var/lib/jason/openclaw/release-manager/auto-promotion-incident-hold' in prior
    base.write_text(prior)
    # Baseline's pre-PR installer touches only the base service and timer.
    assert base.read_text()==prior
    assert stable.read_bytes()==canonical
    lines=[line for line in stable.read_text().splitlines()
           if line.startswith('ExecStart=')]
    assert len(lines)==2 and lines[0]=='ExecStart='
    assert '--repo /home/al/.local/lib/jason/release-approval-source' in lines[1]
    assert 'engineering-worker-source' not in lines[1]
    assert 'promote' not in lines[1]
    assert 'WorkingDirectory=/home/al/.local/lib/jason/release-approval-source' in stable.read_text()
    assert (lib/'release-manager-source').is_symlink()


def test_approval_override_install_idempotent_and_refuses_unapproved_tamper(
        tmp_path, monkeypatch):
    units,_=setup_installer(tmp_path,monkeypatch)
    with patch.object(m.subprocess,'run'):
        assert m.install_approval_only_units()
        assert m.install_approval_only_units()
    path=units/(SERVICE+'.d')/m.APPROVAL_OVERRIDE
    path.write_text('[Service]\nExecStart=/usr/bin/false\n')
    with patch.object(m.subprocess,'run') as runner:
        with pytest.raises(RuntimeError,match='existing approval rollback override is not reviewed'):
            m.install_approval_only_units()
        runner.assert_not_called()
    assert path.read_text()=='[Service]\nExecStart=/usr/bin/false\n'


def test_approval_override_refuses_symlink_before_unit_mutation(tmp_path,monkeypatch):
    units,_=setup_installer(tmp_path,monkeypatch)
    folder=units/(SERVICE+'.d')
    folder.symlink_to(tmp_path/'alien-target',target_is_directory=True)
    with patch.object(m.subprocess,'run') as runner:
        with pytest.raises(RuntimeError,match='directory is a symlink'):
            m.install_approval_only_units()
        runner.assert_not_called()
    assert not (units/SERVICE).exists()


def test_production_baseline_script_does_not_remove_approval_dropin():
    script=(ROOT/'tools/reconcile_production_host_services.sh').read_text()
    # Explicitly test that the candidate contains no deletion of this durable
    # rollback source-authority override; the old baseline has no knowledge of
    # its existence either.
    assert 'jason-release-approval-only.service.d' not in script
    assert '10-canonical-release-scope.conf' not in script
    assert 'jason-release-approval-only.service.d' not in (
        ROOT/'tools/install_release_host_reconciler.py').read_text()
