"""Production mutation stays behind exact Owner authority; fixtures only."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from pathlib import Path
import json
import pytest

from tools import audit_journal_health_reader_install as repair


@contextmanager
def locked():
    yield


def test_exact_native_scope_excludes_frozen_sources_and_policies():
    assert len(repair.FILES) == 4 and len(repair.BEFORE) == 3
    assert all((repair.NATIVE / name).parent == repair.NATIVE for name in repair.FILES.values())
    assert all('/trusted/' not in str(repair.NATIVE / x) for x in repair.FILES.values())
    assert not any('policy' in x or 'adoption' in x for x in repair.FILES.values())


def test_only_current_single_health_failure_can_enter_repair():
    now = datetime.now(timezone.utc)
    drift = {'status': 'drift_detected', 'observed_at': now.isoformat(), 'problems': [
        {'kind': 'failed_system_unit', 'state': 'failed', 'unit': repair.SERVICES[0]}]}
    control = {'circuit_breaker': {'state': 'open', 'reason': 'continuous_production_drift_detected'}}
    repair.strict_repair_drift(drift, control, now=now)
    for changed in [[], drift['problems'] * 2,
                    [{'kind': 'failed_system_unit', 'state': 'failed', 'unit': 'other.service'}]]:
        with pytest.raises(PermissionError, match='UNRELATED_OR_UNKNOWN_DRIFT'):
            repair.strict_repair_drift({**drift, 'problems': changed}, control, now=now)
    with pytest.raises(PermissionError, match='STALE_NATIVE_DRIFT'):
        repair.strict_repair_drift({**drift, 'observed_at': (now - timedelta(minutes=4)).isoformat()},
                                  control, now=now)
    with pytest.raises(PermissionError, match='UNEXPECTED_BREAKER_STATE'):
        repair.strict_repair_drift(drift, {'circuit_breaker': {'state': 'closed'}}, now=now)


def test_owner_denial_runs_no_system_command_and_writes_no_record(tmp_path, monkeypatch):
    monkeypatch.setattr(repair, 'RECORD', tmp_path / 'must-not-exist')
    monkeypatch.setattr(repair, 'preflight', lambda *a: {'exact_scope': 'fixture'})
    commands = []
    def deny(scope):
        raise PermissionError('Owner did not approve')
    with pytest.raises(PermissionError, match='Owner did not approve'):
        repair.execute(SimpleNamespace(command=lambda *a, **k: commands.append(a)), None,
                       {'locks': locked, 'owner': deny}, 'f' * 40, {})
    assert not commands and not repair.RECORD.exists()


def test_root_preflight_never_authenticates_or_changes_system(tmp_path, monkeypatch):
    monkeypatch.setattr(repair, 'RECORD', tmp_path / 'must-not-exist')
    monkeypatch.setattr(repair, 'preflight', lambda *a: {'exact_scope': 'fixture'})
    repair.execute(None, None, {'locks': locked}, 'f' * 40, {}, check_only=True)
    assert not repair.RECORD.exists()


def test_state_change_during_owner_decision_denies_before_first_write(tmp_path, monkeypatch):
    monkeypatch.setattr(repair, 'RECORD', tmp_path / 'must-not-exist')
    scopes = iter([{'scope': 1}, {'scope': 2}])
    monkeypatch.setattr(repair, 'preflight', lambda *a: next(scopes))
    with pytest.raises(PermissionError, match='STATE_CHANGED_DURING_APPROVAL'):
        repair.execute(None, SimpleNamespace(OWNER='verified-fixture-owner'),
                       {'locks': locked, 'owner': lambda _: 'verified-fixture-owner'}, 'f' * 40, {})
    assert not repair.RECORD.exists()


def test_unprivileged_installer_preflight_is_denied(monkeypatch):
    monkeypatch.setattr(repair.os, 'geteuid', lambda: 1000)
    with pytest.raises(PermissionError, match='ISOLATED_ROOT_REQUIRED'):
        repair.preflight(None, None, 'f' * 40, {})


def test_new_canonical_installer_routes_keep_old_operations_exclusive():
    source = Path('tools/audit_journal_install.py').read_text()
    assert '--repair-native-health-private-reader' in source
    assert '--preflight-native-health-private-reader' in source
    assert 'HEALTH_READER_PROTECTED_CI' in source
    assert 'ONE_EXACT_INSTALLER_OPERATION' in source
    assert 'check_only=args.preflight_native_health_private_reader' in source


def test_shared_owner_prompt_displays_only_the_exact_native_health_targets(monkeypatch,capsys):
    from tools import pmv4_e_dispatch_install as owner
    raw=b'synthetic-reviewed-owner-auth-source'
    monkeypatch.setattr(owner,'read',lambda *a:raw)
    monkeypatch.setattr(owner,'OAUTH_HASH',owner.digest(raw))
    calls=[]
    def form(url,args):
        calls.append(url)
        if url.endswith('devicecode'):
            return {'user_code':'SYNTHETIC','device_code':'synthetic-only',
                    'verification_uri':'https://example.invalid/synthetic-auth',
                    'expires_in':60,'interval':5}
        return {'access_token':'synthetic-only-never-networked'}
    monkeypatch.setattr(owner,'load_code',lambda *a:{
        'TENANT':'synthetic-tenant','CLIENT_ID':'synthetic-client','SCOPE':'synthetic-scope',
        '_form':form,'jwt_owner':lambda _: 'synthetic-verified-owner'})
    monkeypatch.setattr(owner.time,'sleep',lambda _:None)
    scope={'action':repair.ACTION,'policy':{'candidate_sha':'f'*40,'rollback_sha':'e'*40},
           **repair.native_target_scope()}
    prompts=[]
    monkeypatch.setattr('builtins.input',lambda prompt:(prompts.append(prompt),repair.ACTION)[1])
    assert owner.owner(scope)=='synthetic-verified-owner'
    output=capsys.readouterr().out
    targets=next(line.split('=',1)[1] for line in output.splitlines() if line.startswith('INSTALL_TARGETS='))
    assert targets.split(',')==scope['exact_native_targets']
    assert len(targets.split(','))==4
    assert all(Path(x).parent==repair.NATIVE for x in targets.split(','))
    assert 'INSTALL_SCOPE_SHA256='+owner.digest(owner.canonical(scope)) in output
    assert len(prompts)==1 and len(calls)==2
    assert '/pmv4-e-bootstrap/' not in targets


def test_approval_target_alias_does_not_mutate_native_enforcement_targets():
    scope=repair.native_target_scope()
    assert scope['installation_targets']==scope['exact_native_targets']
    scope['installation_targets'].append('/synthetic-renderer-change')
    assert len(scope['exact_native_targets'])==4
