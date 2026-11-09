"""Disposable regression for the native disabled provider-shadow unit stage."""
from __future__ import annotations
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools import stage_isolated_provider_shadow_units as m
from tools import reconcile_managed_unit_delta as delta

SOURCE = Path(__file__).resolve().parents[2]


def fixture(tmp_path):
    releases=tmp_path/'releases';candidate=releases/('a'*40)
    installed=tmp_path/'installed'
    for directory in (candidate,installed):directory.mkdir(parents=True)
    for name in m.REQUIRED_SOURCE_FILES:
        source=SOURCE/name;dest=candidate/name;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,dest)
    for unit in m.UNITS:
        source=SOURCE/m.SOURCE_ROOT/unit;dest=candidate/m.SOURCE_ROOT/unit
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
    policy={'schema_version':'1.0','allowed_system_units':list(m.UNITS),
            'required_system_units':[],'allowed_user_units':[],'required_user_units':[]}
    p=candidate/'config/production-desired-state.json';p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(policy))
    source=json.loads((SOURCE/'infrastructure/isolated-services/installation-manifest.json').read_text())
    p=candidate/'infrastructure/isolated-services/installation-manifest.json'
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(source))
    return releases,candidate,installed


def test_exact_sha_root_required(tmp_path):
    root,candidate,installed=fixture(tmp_path)
    assert m.pinned_release(candidate,'a'*40,root)==candidate
    with pytest.raises(m.StageError):m.pinned_release(candidate,'b'*40,root)
    alias=root/('b'*40);alias.symlink_to(candidate,target_is_directory=True)
    with pytest.raises(m.StageError):m.pinned_release(alias,'b'*40,root)


def test_exact_two_units_staged_disabled_and_idempotent(tmp_path):
    root,candidate,installed=fixture(tmp_path)
    before={p.name:p.read_bytes() for p in (candidate/m.SOURCE_ROOT).glob('jason-isolated-provider-health.*')}
    first=m.stage(candidate,installed)
    assert set(first)==set(m.UNITS)
    assert m.stage(candidate,installed)==()
    assert sorted(p.name for p in installed.iterdir())==sorted(m.UNITS)
    assert {p.name:p.read_bytes() for p in installed.iterdir()}==before
    assert not list(installed.glob('*timer.wants*'))


def test_policy_must_allow_not_require_shadow_units(tmp_path):
    root,candidate,installed=fixture(tmp_path)
    policy=candidate/'config/production-desired-state.json';data=json.loads(policy.read_text())
    data['required_system_units'].append(m.UNITS[0]);policy.write_text(json.dumps(data))
    with pytest.raises(m.StageError,match='only allowed'):m.stage(candidate,installed)
    assert list(installed.iterdir())==[]


def test_manifest_cannot_permit_activation(tmp_path):
    root,candidate,installed=fixture(tmp_path)
    file=candidate/'infrastructure/isolated-services/installation-manifest.json'
    value=json.loads(file.read_text());value['staged_native_provider_shadow']['allows_service_or_timer_activation']=True
    file.write_text(json.dumps(value))
    with pytest.raises(m.StageError,match='authorization/rollback'):m.stage(candidate,installed)
    assert list(installed.iterdir())==[]


def test_reject_altered_source_or_developer_checkout_command(tmp_path):
    root,candidate,installed=fixture(tmp_path)
    path=candidate/m.SOURCE_ROOT/m.UNITS[0]
    path.write_text(path.read_text().replace('--repo /opt/jason/current','--repo /home/al/projects/jason'))
    with pytest.raises(m.StageError,match='read-only'):m.stage(candidate,installed)
    assert list(installed.iterdir())==[]


def test_reject_symlinked_or_modified_installed_units(tmp_path):
    root,candidate,installed=fixture(tmp_path)
    target=installed/m.UNITS[0];target.symlink_to(candidate/m.SOURCE_ROOT/m.UNITS[0])
    with pytest.raises(m.StageError,match='symlink'):m.stage(candidate,installed)
    target.unlink();target.write_text('modified existing unit')
    with pytest.raises(m.StageError,match='differs'):m.stage(candidate,installed)
    assert not (installed/m.UNITS[1]).exists()


def test_required_companion_source_cannot_be_missing(tmp_path):
    root,candidate,installed=fixture(tmp_path)
    (candidate/'tools/isolated_service_shadow.py').unlink()
    with pytest.raises(m.StageError,match='missing'):m.stage(candidate,installed)
    assert list(installed.iterdir())==[]


def test_only_disabled_or_not_found_systemd_states_allowed():
    def runner_factory(states):
        def runner(cmd,**kwargs):
            return SimpleNamespace(stdout=states[cmd[1]],returncode=0)
        return runner
    m.check_dormant(m.UNITS[1],runner_factory({'is-active':'inactive\n','is-enabled':'disabled\n'}))
    m.check_dormant(m.UNITS[0],runner_factory({'is-active':'unknown\n','is-enabled':'not-found\n'}))
    with pytest.raises(m.StageError):
        m.check_dormant(m.UNITS[1],runner_factory({'is-active':'active\n','is-enabled':'enabled\n'}))
    with pytest.raises(m.StageError):
        m.check_dormant(m.UNITS[0],runner_factory({'is-active':'inactive\n','is-enabled':'enabled\n'}))


def test_existing_lkg_delta_planner_can_reverse_exact_two_units(tmp_path):
    root,candidate,installed=fixture(tmp_path)
    target=root/('b'*40);(target/'config').mkdir(parents=True)
    (target/'config/production-desired-state.json').write_text(json.dumps({
        'schema_version':'1.0','required_system_units':[], 'allowed_system_units':[],
        'required_user_units':[],'allowed_user_units':[]}))
    assert len(m.stage(candidate,installed))==2
    # This planner runs from the old trusted LKG source, so the units MUST be
    # located under a preexisting canonical source root it already recognizes.
    plan=delta.plan_unit_removals(candidate,target,installed,scope='system')
    assert plan==[m.UNITS[1],m.UNITS[0]]
    assert set(p.name for p in installed.iterdir())==set(m.UNITS)


def test_no_activation_command_in_stager_or_host_invocation():
    module=(SOURCE/'tools/stage_isolated_provider_shadow_units.py').read_text()
    assert "'enable'" not in module and "'start'" not in module
    assert 'systemctl stop' not in module
    host=(SOURCE/'tools/reconcile_production_host_services.sh').read_text()
    assert '--expected-sha "$SOURCE_REVISION"' in host
    assert 'stage_isolated_provider_shadow_units.py' in host
    assert 'jason-runtime.service' not in module
