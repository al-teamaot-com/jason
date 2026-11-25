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
