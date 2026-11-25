"""Execute the actual new isolated Root preflight path in a disposable lab.

This test exists because only a mocked denial path was exercised before a
production attempt failed at the first real preflight line (missing sys).
No actual root identity, production paths, sudo, provider or DB writes.
"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime,timezone,timedelta
from pathlib import Path
from types import SimpleNamespace
from hashlib import sha256
import json
import os
import sqlite3
import sys
import pytest

from tools import audit_journal_no_restore_install as mod
from tools import audit_journal_no_restore_worker as worker
from tools import audit_journal_install_transaction as txlib
from orchestrator.segmented_journal import fingerprint

@contextmanager
def gate(*args,**kwargs):
    yield


def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':')).encode()
def hashed(x):return sha256(canonical(x)).hexdigest()


def seed_sqlite(path):
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE audit_journal_inflight (execution_id TEXT, provider_started INTEGER, remaining_bytes INTEGER)')
        db.execute('CREATE TABLE audit_journal_pending_outcomes (receipt_id TEXT)')
        db.execute('CREATE TABLE orchestration_events (execution_id TEXT,event_type TEXT,capability_name TEXT,occurred_at TEXT)')
        for i,(cap,started) in enumerate((('service.configuration.read',1),('endpoint.device.read',0),('backup.endpoint.asset.search',1))):
            execution='exact-read-'+str(i)
            event=('orchestration.capability.invoking' if started else 'orchestration.capability.resolved')
            db.execute('INSERT INTO audit_journal_inflight VALUES (?,?,?)',(execution,started,23494656))
            db.execute('INSERT INTO orchestration_events VALUES (?,?,?,?)',(execution,event,cap,'2026-11-24T18:25:00+00:00'))
        db.execute("CREATE TRIGGER audit_journal_maintenance_admission BEFORE INSERT ON orchestration_events BEGIN SELECT RAISE(ABORT,'JOURNAL_MAINTENANCE'); END")


@pytest.fixture
def reviewed_lab(tmp_path,monkeypatch):
    home=tmp_path/'safe-fixture'
    home.mkdir()
    private=home/'private';private.mkdir()
    control=home/'control';control.mkdir()
    archive=home/'archive';archive.mkdir()
    pending=home/'pending';pending.mkdir()
    active=home/'active.sqlite3'
    seed_sqlite(active)
    src=pending/(mod.FIRST_SEGMENT+'.sqlite3');src.write_bytes(b'fixture encrypted prior original')
    (archive/(mod.FIRST_SEGMENT+'.sqlite3')).write_bytes(src.read_bytes())
    src.chmod(0o440)
    old_fp=fingerprint(src.stat())
    segment={'id':mod.FIRST_SEGMENT,'state':'sealed','proof':{'events':mod.FIRST_EVENTS,
          'file_sha256':mod.FIRST_SHA256,'integrity':'ok','restore_verified':True,
          'source_before_image':src.name,'source_before_fingerprint':old_fp}}
    catalog={'mode':'segmented','generation':2,'epoch':'exact-fixture-epoch','segments':[segment]}
    (control/'release-status.json').write_bytes(canonical({'phase':'draining_admitted_work',
         'scope_sha256':mod.OLD_SCOPE,'candidate_sha':mod.OLD_CANDIDATE}))
    old_final={'allowed_system_units':['jason-audit-journal-release.service'],
               'required_system_units':['jason-audit-journal-maintenance.timer'],
               'max_stopped_rollback_containers':27,'policy_version':'unchanged'}
    old_current={**old_final,'required_system_units':[],
                'allowed_system_units':['jason-audit-journal-release.service','jason-audit-journal-maintenance.timer']}
    desired=home/'production-desired-state.json';desired.write_bytes(canonical(old_current))
    old_plan={'candidate_sha':mod.OLD_CANDIDATE,'scope_sha256':mod.OLD_SCOPE,
         'independently_verified_entra_owner':True,
         'scope':{'desired_state_after_sha256':hashed(old_final),
                  'desired_state_initial_sha256':hashed(old_current)}}
    (private/'release-plan.json').write_bytes(canonical(old_plan))
    (private/'release-journal.json').write_bytes(canonical({'recovery_started_at':'2026-11-24T21:10:00+00:00',
         'scope_sha256':mod.OLD_SCOPE}))
    (private/'desired-final.json').write_bytes(canonical(old_final))
    fake_scope=SimpleNamespace(PRIVATE=private,CONTROL=control,DESIRED=desired,
         PROFILE=home/'profile.json',ACTIVE=active,BASE=home/'trusted-base',
         PROTECTED={},SOURCES=(),ROLLBACK='d1b8c196dadd4b672ec8ba47075f27bb61c98d63')
    fake_profile=SimpleNamespace(gate=gate,catalog=lambda:catalog,active=active,pending=pending,
        custody_uid=os.getuid(),writer_uid=os.stat(src).st_gid)
    root_targets={'RECORD':home/'new-root-record','GRANT':home/'new-owner-grant.json',
        'SOURCE':home/'new-root-executor.py','MAINTENANCE_DROPIN':home/'new-maintain.conf',
        'FAST_DROPIN':home/'new-fast.conf','FULL_DROPIN':home/'new-full.conf',
        'RELEASE_UNIT':home/'new-root.service'}
    for n,p in root_targets.items():monkeypatch.setattr(mod,n,p)
    monkeypatch.setattr(mod,'os',SimpleNamespace(geteuid=lambda:0))
    # The actual `sys.flags.isolated` lookup executes here. The old code had
    # no module sys import and would raise NameError in this test.
    assert mod.sys is sys, 'Installer must import sys before using sys.flags.isolated'
    monkeypatch.setattr(mod,'sys',SimpleNamespace(flags=SimpleNamespace(isolated=1)))
    monkeypatch.setattr(mod,'checked_frozen_source',lambda s,p:'bound-existing-protected-policy')
    monkeypatch.setattr(mod.JournalProfile,'load',lambda _:fake_profile)
    monkeypatch.setattr(mod.worker,'exact_sealed',lambda profile,row:archive/(mod.FIRST_SEGMENT+'.sqlite3'))
    orig=txlib.raw_file
    monkeypatch.setattr(mod.txlib,'raw_file',lambda path,mode=None:Path(path).read_bytes() if Path(path).resolve().is_relative_to(home.resolve()) else (_ for _ in ()).throw(AssertionError('OUTSIDE_TEST_SCOPE')))
    # Make sure this cannot affect the actual user root records.
    def command(args):
        if args[0]=='/usr/bin/systemctl' and 'jason-audit-journal-release.service' in args:
            return '\n'.join(('ActiveState=failed','Result=exit-code','MainPID=0','UnitFileState=enabled'))
        if args[0]=='/usr/bin/systemctl' and 'jason-audit-journal-maintenance.timer' in args:
            return '\n'.join(('ActiveState=inactive','Result=success','MainPID=0','UnitFileState=disabled'))
        if args[0]=='/usr/bin/docker' and args[1]=='inspect':return 'true'
        raise AssertionError(('PROHIBITED_PRODUCTION_COMMAND',args))
    bridge=SimpleNamespace(command=command)
    worker_bytes=Path('tools/audit_journal_no_restore_worker.py').read_bytes()
    return bridge,fake_scope,{'tools/audit_journal_no_restore_worker.py':worker_bytes},root_targets


def test_complete_reviewed_root_preflight_executes_without_root_writes(reviewed_lab):
    bridge,scope,payload,targets=reviewed_lab
    result=mod.preflight(bridge,scope,'f'*40,payload)
    assert result['action']==mod.ACTION
    assert result['immutable_evidence']['original_archive']['events']==mod.FIRST_EVENTS
    assert result['immutable_evidence']['original_archive']['archive_sha256']==mod.FIRST_SHA256
    assert result['no_legacy_rebuild'] is True
    assert len(result['immutable_evidence']['initial_reservations'])==3
    assert result['immutable_evidence']['old_service']['release']['Result']=='exit-code'
    assert result['immutable_evidence']['old_service']['timer']['UnitFileState']=='disabled'
    assert result==mod.preflight(bridge,scope,'f'*40,payload)
    assert all(not p.exists() for p in targets.values())


def test_full_execute_reaches_owner_denial_without_writes(reviewed_lab):
    bridge,scope,payload,targets=reviewed_lab
    requested=[]
    def deny(exact):
        requested.append(exact)
        raise PermissionError('NEW_EXACT_OWNER_APPROVAL_DENIED')
    auth={'locks':gate,'owner':deny}
    with pytest.raises(PermissionError,match='NEW_EXACT_OWNER_APPROVAL_DENIED'):
        mod.execute(bridge,scope,None,None,auth,'f'*40,payload)
    assert len(requested)==1 and requested[0]['action']==mod.ACTION
    assert all(not p.exists() for p in targets.values())



def test_exact_root_preflight_rejects_protected_source_drift_before_owner(reviewed_lab,tmp_path):
    bridge,scope,payload,targets=reviewed_lab
    protected=tmp_path/'protected-existing-root-source.py'
    protected.write_bytes(b'old accepted source bytes')
    scope.PROTECTED={str(protected):sha256(protected.read_bytes()).hexdigest()}
    assert mod.preflight(bridge,scope,'f'*40,payload)['action']==mod.ACTION
    protected.write_bytes(b'changed unapproved bytes')
    with pytest.raises(PermissionError,match='EXISTING_NATIVE_PROTECTED_SOURCE_CHANGED'):
        mod.preflight(bridge,scope,'f'*40,payload)
    assert all(not p.exists() for p in targets.values())


def test_exact_root_preflight_rejects_prior_release_identity_change(reviewed_lab):
    bridge,scope,payload,targets=reviewed_lab
    file=scope.PRIVATE/'release-plan.json'
    original=json.loads(file.read_text())
    original['candidate_sha']='f'*40
    file.write_bytes(canonical(original))
    with pytest.raises(PermissionError,match='KNOWN_FAILED_ONE_USE_RELEASE_ONLY'):
        mod.preflight(bridge,scope,'f'*40,payload)
    assert all(not p.exists() for p in targets.values())


def test_exact_root_preflight_rejects_changed_provider_state(reviewed_lab):
    bridge,scope,payload,targets=reviewed_lab
    with sqlite3.connect(scope.ACTIVE) as c:
        c.execute("UPDATE orchestration_events SET capability_name='user.password.reset' WHERE capability_name='endpoint.device.read'")
    with pytest.raises(PermissionError,match='READ_ONLY_RESERVATION_PROVENANCE'):
        mod.preflight(bridge,scope,'f'*40,payload)
    assert all(not p.exists() for p in targets.values())
