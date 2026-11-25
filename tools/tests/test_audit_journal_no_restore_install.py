"""No Root production mutations; new one-use Owner plan denied by default."""
from contextlib import contextmanager
from datetime import datetime,timezone,timedelta
from pathlib import Path
from types import SimpleNamespace
import json,os,sqlite3
import pytest

from tools import audit_journal_no_restore_install as mod
from tools import audit_journal_no_restore_worker as worker
from tools import audit_journal_release_scope as scope


@contextmanager
def exclusive():
    yield


def database(path):
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE audit_journal_inflight '
                   '(execution_id TEXT, provider_started INTEGER, remaining_bytes INTEGER)')
        db.execute('CREATE TABLE audit_journal_pending_outcomes (receipt_id TEXT)')
        db.execute('CREATE TABLE orchestration_events '
                   '(execution_id TEXT,event_type TEXT,capability_name TEXT,occurred_at TEXT)')
        for i,(cap,started) in enumerate((('service.configuration.read',1),
            ('endpoint.device.read',0),('backup.endpoint.asset.search',1))):
            key='read-only-execution-'+str(i)
            db.execute('INSERT INTO audit_journal_inflight VALUES (?,?,?)',(key,started,20000000))
            event='orchestration.capability.invoking' if started else 'orchestration.capability.resolved'
            db.execute('INSERT INTO orchestration_events VALUES (?,?,?,?)',
                (key,event,cap,'2026-11-24T18:25:00+00:00'))
        db.execute('CREATE TRIGGER audit_journal_maintenance_admission BEFORE INSERT ON orchestration_events '
                   "BEGIN SELECT RAISE(ABORT,'MAINTENANCE'); END")


def test_exact_live_readonly_reservations_without_provider_calls(tmp_path):
    db=tmp_path/'fixture.sqlite3';database(db)
    actual=mod.live_reservations(db)
    assert len(actual)==3 and sum(r['provider_started'] for r in actual)==2
    assert {r['capability'] for r in actual}==mod.SAFE_READ_CAPABILITIES
    assert all(r['result']=='unknown_not_retried' and len(r['execution_hash'])==64 for r in actual)
    assert 'read-only-execution' not in str(actual)


def test_changed_unknown_provider_denied_before_owner(tmp_path):
    db=tmp_path/'fixture.sqlite3';database(db)
    with sqlite3.connect(db) as c:
        c.execute("UPDATE orchestration_events SET capability_name='user.password.reset' "
                  "WHERE capability_name='endpoint.device.read'")
    with pytest.raises(PermissionError,match='READ_ONLY_RESERVATION_PROVENANCE'):
        mod.live_reservations(db)


def test_pending_provider_outcome_denied_before_owner(tmp_path):
    db=tmp_path/'fixture.sqlite3';database(db)
    with sqlite3.connect(db) as c:c.execute("INSERT INTO audit_journal_pending_outcomes VALUES ('unknown')")
    with pytest.raises(PermissionError,match='UNKNOWN_PENDING_OUTCOME'):
        mod.live_reservations(db)


def test_new_or_missing_readonly_reservation_denied_before_owner(tmp_path):
    db=tmp_path/'fixture.sqlite3';database(db)
    with sqlite3.connect(db) as c:c.execute('DELETE FROM audit_journal_inflight LIMIT 1')
    with pytest.raises(PermissionError,match='THREE_KNOWN_RESERVATIONS_ONLY'):
        mod.live_reservations(db)


def test_missing_exact_admission_barrier_denied_before_owner(tmp_path):
    db=tmp_path/'fixture.sqlite3';database(db)
    with sqlite3.connect(db) as c:c.execute('DROP TRIGGER audit_journal_maintenance_admission')
    with pytest.raises(PermissionError,match='EXACT_KNOWN_ADMISSION_BARRIER'):
        mod.live_reservations(db)


def test_new_scope_health_fixes_only_one_shm_file_not_full_archive():
    units=mod.proposed_units(scope)
    assert set(units)=={mod.MAINTENANCE_DROPIN,mod.FAST_DROPIN,mod.FULL_DROPIN,mod.RELEASE_UNIT}
    aux='-'+str(scope.ACTIVE)+'-shm'
    for p in (mod.FAST_DROPIN,mod.FULL_DROPIN):
        assert units[p].decode()=='[Service]\nReadWritePaths='+aux+'\n'
        assert '/srv/jason/archive/' not in units[p].decode()
        assert 'sqlite3-wal' not in units[p].decode()
    assert '--operation maintain' in units[mod.MAINTENANCE_DROPIN].decode()
    assert '--operation recover' in units[mod.RELEASE_UNIT].decode()
    assert 'User=root' in units[mod.RELEASE_UNIT].decode()
    assert 'NoNewPrivileges=true' in units[mod.RELEASE_UNIT].decode()
    assert 'AmbientCapabilities=CAP_SETUID' in units[mod.RELEASE_UNIT].decode()
    assert 'CAP_SYS_ADMIN' not in units[mod.RELEASE_UNIT].decode()
    assert 'CapabilityBoundingSet=CAP_DAC_OVERRIDE CAP_SETUID CAP_SETGID CAP_SYS_PTRACE CAP_KILL' in units[mod.RELEASE_UNIT].decode()
    assert 'StartLimitIntervalSec=1h\nStartLimitBurst=3\n\n[Service]' in units[mod.RELEASE_UNIT].decode()
    assert 'Restart=on-failure\nRestartSec=120' in units[mod.RELEASE_UNIT].decode()
    assert 'ExecStart=' in units[mod.MAINTENANCE_DROPIN].decode()
    assert 'legacy.prepared.sqlite3' not in str(units)


def test_no_unprivileged_root_preflight(tmp_path,monkeypatch):
    # Run this test deterministically on both unprivileged GitHub and root CI.
    monkeypatch.setattr(mod.os,'geteuid',lambda:1000)
    with pytest.raises(PermissionError,match='ISOLATED_ROOT_REQUIRED'):
        mod.preflight(None,None,'0'*40,{})


def test_owner_denial_makes_zero_installation_changes(tmp_path,monkeypatch):
    monkeypatch.setattr(mod,'preflight',lambda *a:{'action':mod.ACTION,'immutable_evidence':{'original_archive':{'events':3}},'scope':'test'})
    monkeypatch.setattr(mod,'RECORD',tmp_path/'record-not-created')
    monkeypatch.setattr(mod,'proposed_units',lambda _: {})
    asked=[]
    auth={'locks':exclusive,'owner':lambda s:(asked.append(s),(_ for _ in ()).throw(PermissionError('no signed owner')))[1]}
    with pytest.raises(PermissionError,match='no signed owner'):
        mod.execute(None,None,None,None,auth,'f'*40,{})
    assert len(asked)==1
    assert not (tmp_path/'record-not-created').exists()


def test_owner_scope_changes_are_denied_before_disk_mutation(tmp_path,monkeypatch):
    scope_calls=[]
    def pre(*a):
        scope_calls.append(1)
        return {'action':mod.ACTION,'immutable_evidence':{'original_archive':{'events':3}},'approved_by':'owner','revision':len(scope_calls)}
    monkeypatch.setattr(mod,'preflight',pre)
    monkeypatch.setattr(mod,'RECORD',tmp_path/'record-not-created')
    monkeypatch.setattr(mod,'proposed_units',lambda _: {})
    auth={'locks':exclusive,'owner':lambda _:mod.OWNER}
    with pytest.raises(PermissionError,match='STATE_CHANGED_DURING_OWNER_APPROVAL'):
        mod.execute(None,None,None,None,auth,'f'*40,{})
    assert len(scope_calls)==2
    assert not (tmp_path/'record-not-created').exists()


def test_no_rebuild_route_is_explicitly_one_of_installer_choices():
    text=Path('tools/audit_journal_install.py').read_text()
    assert '--complete-no-legacy-restore' in text
    assert 'NO_RESTORE_PROTECTED_CI' in text
    assert 'audit_journal_no_restore_install' in text
    assert 'ONE_EXACT_INSTALLER_OPERATION' in text


def test_immutable_incident_window_allows_delayed_verified_reservations(tmp_path,monkeypatch):
    # The unresolved operations are immutable historical facts. Advancing the
    # wall clock beyond 24 hours must not destroy the exact recovery path.
    db=tmp_path/'past-cutover.sqlite3';database(db)
    class FutureClock(datetime):
        @classmethod
        def now(cls,tz=None):return datetime(2026,11,30,12,0,tzinfo=timezone.utc)
    monkeypatch.setattr(mod,'datetime',FutureClock)
    rows=mod.live_reservations(db)
    assert len(rows)==3 and all(r['result']=='unknown_not_retried' for r in rows)


def test_reservation_timestamp_outside_exact_cutover_denied(tmp_path):
    db=tmp_path/'wrong-cutover.sqlite3';database(db)
    with sqlite3.connect(db) as c:
        c.execute("UPDATE orchestration_events SET occurred_at='2026-11-25T03:00:00+00:00' "
                  "WHERE capability_name='endpoint.device.read'")
    with pytest.raises(PermissionError,match='READ_ONLY_RESERVATION_TIMESTAMP'):
        mod.live_reservations(db)
