"""Disposable, non-root, no-provider tests of forward-only journal recovery."""
from contextlib import contextmanager
from datetime import datetime,timezone,timedelta
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import json
import os
import sqlite3

import pytest
from tools import audit_journal_no_restore_worker as fwd
from orchestrator.segmented_journal import fingerprint,JournalUnavailable
from tools import audit_journal_control as old


@contextmanager
def noop(*args,**kwargs):
    yield


class FakeProfile:
    def __init__(self,base,archive,source,active,record):
        self.active=active
        self.archives=archive.parent
        self.pending=source.parent
        self.control=base/'control'
        self.custody_uid=os.getuid()
        self.writer_uid=os.getgid()
        self.target_bytes=1024
        self.ceiling_bytes=10_000_000
        self._record=record
        self._catalog={'mode':'segmented','generation':2,'epoch':'sealed-initial',
                       'opened_at':datetime.now(timezone.utc).isoformat(),
                       'segments':[record]}
        self.gate=noop
    def catalog(self):return self._catalog
    def artifact(self,record):
        assert record is self._record
        return self.archives/(record['id']+'.sqlite3')
    def active_identity(self):return self.active.stat()
    def active_bytes(self):return self.active.stat().st_size


class FakeController:
    def __init__(self,profile,private):
        self.p=profile
        self.private=private
        self.intent=private/'transaction.json'
        self.serialized=noop
        self.requests=[]
    def _json(self,path,value,mode=0o444):
        old.atomic(path,value,mode,owner=self.p.custody_uid)
    def profile_arguments(self):return {'fixture':True}
    def _sql(self,operation,args,seconds=30):
        self.requests.append(operation)
        if operation=='archive_readback':
            return {'reads_verified':True,'event_probes':2,'provider_contacted':False}
        if operation=='barrier':
            from orchestrator.journal_sql import admission_barrier
            admission_barrier(Path(args['path']),args['enabled'])
            return {'enabled':args['enabled']}
        raise RuntimeError('unexpected operation '+operation)
    def scrub_one(self,now=None):return {'status':'scrub_not_due'}
    def transition(self,initial=False):
        assert initial is False
        self.requests.append('rotate_without_legacy_reconstruction')
        self.p._catalog={**self.p._catalog,'epoch':'next-current-epoch',
                         'generation':self.p._catalog['generation']+1}
        return {'status':'rotated'}


def sqlite_active(path):
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE orchestration_events (event_id TEXT, execution_id TEXT, event_type TEXT, '
                   'capability_name TEXT, occurred_at TEXT)')
        db.execute('CREATE TABLE audit_journal_inflight (execution_id TEXT, provider_started INTEGER, remaining_bytes INTEGER)')
        db.execute('CREATE TABLE audit_journal_pending_outcomes (receipt_id TEXT, queued_at REAL)')
        db.execute('CREATE TABLE audit_journal_meta (epoch TEXT PRIMARY KEY)')
        db.execute("INSERT INTO audit_journal_meta VALUES ('sealed-initial')")
        for i,(started,capability,kind) in enumerate(((1,'service.configuration.read','orchestration.capability.invoking'),
                                                       (0,'endpoint.device.read','orchestration.capability.resolved'),
                                                       (1,'backup.endpoint.asset.search','orchestration.capability.invoking'))):
            key='example-execution-'+str(i)
            db.execute('INSERT INTO audit_journal_inflight VALUES (?,?,?)',(key,started,25_000_000))
            db.execute('INSERT INTO orchestration_events VALUES (?,?,?,?,?)',
                       ('event-'+str(i),key,kind,capability,datetime.now(timezone.utc).isoformat()))
        db.execute('CREATE TRIGGER audit_journal_maintenance_admission BEFORE INSERT ON orchestration_events '
                   "WHEN NEW.event_type = 'orchestration.request.received' BEGIN SELECT RAISE(ABORT,'JASON_AUDIT_JOURNAL_MAINTENANCE'); END")


@pytest.fixture
def specimen(tmp_path,monkeypatch):
    base=tmp_path
    for n in ('archive','pending','active','private','control'):
        (base/n).mkdir()
    archive=base/'archive'/('a'*32+'.sqlite3')
    source=base/'pending'/('a'*32+'.sqlite3')
    active=base/'active'/'active.sqlite3'
    archive.write_bytes(b'unchanged full sealed archive bytes for a small fixture')
    source.write_bytes(archive.read_bytes())
    archive.chmod(0o440)
    source.chmod(0o440)
    os.chown(archive,-1,os.getgid())
    os.chown(source,-1,os.getgid())
    sqlite_active(active)
    proof={'integrity':'ok','restore_verified':True,'events':3,
           'file_sha256':sha256(archive.read_bytes()).hexdigest(),
           'source_before_image':source.name,
           'source_before_fingerprint':fingerprint(source.stat())}
    rec={'id':'a'*32,'state':'sealed','proof':proof,'fingerprint':fingerprint(archive.stat())}
    p=FakeProfile(base,archive,source,active,rec)
    c=FakeController(p,base/'private')
    monkeypatch.setattr(fwd,'RECEIPTS',base/'private')
    monkeypatch.setattr(fwd,'ADMISSION_RECEIPT',base/'private'/'forward-admission-recovered.json')
    # Unit fixture cannot assume a distinct archive filesystem. Production
    # enforces this independently in exact_sealed(), tested below.
    monkeypatch.setattr(fwd,'exact_sealed',lambda profile,r,**kwargs:archive)
    initial=fwd.record_reservations(active,expected=[
        {'execution_hash':sha256(('example-execution-'+str(i)).encode()).hexdigest(),
         'provider_started':bool(started),'capability':capability,'last_event_type':kind,
         'last_occurred_at':last,'result':'unknown_not_retried'}
        for i,started,capability,kind,last in
        [(i,r[0],r[1],r[2],sqlite3.connect(active).execute('SELECT occurred_at FROM orchestration_events WHERE execution_id=?',('example-execution-'+str(i),)).fetchone()[0])
         for i,r in enumerate([(1,'service.configuration.read','orchestration.capability.invoking'),
                               (0,'endpoint.device.read','orchestration.capability.resolved'),
                               (1,'backup.endpoint.asset.search','orchestration.capability.invoking')])]
    ])
    # The signed scope binds every still-open reservation, including unknown results.
    grant={'action':fwd.ACTION,'no_legacy_rebuild':True,'stage':'recovery_authorized',
           'scope_sha256':'a'*64,'initial_generation':2,'initial_epoch':'sealed-initial',
           'initial_reservations':initial,'original_archive':{'segment_id':rec['id'],'events':3,
                'archive_sha256':proof['file_sha256']}}
    return c,grant,archive,source


def test_recovery_proves_archive_and_reclaims_only_redundant_copy(specimen):
    c,grant,archive,source=specimen
    result=fwd.recover_forward(c,grant)
    assert result['status']=='admissions_restored'
    assert result['unknown_results_preserved']==3 and result['no_legacy_rebuild'] is True
    assert not source.exists() and archive.is_file()
    assert archive.read_bytes()==b'unchanged full sealed archive bytes for a small fixture'
    assert 'archive_readback' in c.requests and 'barrier' in c.requests
    assert 'rebuild' not in c.requests and 'restore' not in c.requests
    with sqlite3.connect(c.p.active) as db:
        assert db.execute('SELECT COUNT(*) FROM audit_journal_inflight').fetchone()[0]==3
        assert db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='audit_journal_maintenance_admission'").fetchone()[0]==0
    assert fwd.recover_forward(c,grant)['status']=='admissions_restored'


def test_recovery_denies_mismatched_archive_without_deletion(specimen):
    c,grant,archive,source=specimen
    archive.chmod(0o600);archive.write_bytes(b'tampered archive')
    with pytest.raises(JournalUnavailable,match='ARCHIVE_SHA_MISMATCH'):
        fwd.recover_forward(c,grant)
    assert source.exists()
    with sqlite3.connect(c.p.active) as db:
        assert db.execute("SELECT count(*) FROM sqlite_master WHERE name='audit_journal_maintenance_admission'").fetchone()[0]==1


def test_recovery_denies_mismatched_source_without_deletion(specimen):
    c,grant,archive,source=specimen
    source.chmod(0o600);source.write_bytes(b'tampered source')
    with pytest.raises(JournalUnavailable,match='SOURCE_CUSTODY'):
        fwd.recover_forward(c,grant)
    assert archive.exists() and source.exists()


def test_recovery_rejects_new_provider_reservation_without_deletion(specimen):
    c,grant,archive,source=specimen
    with sqlite3.connect(c.p.active) as db:
        db.execute('INSERT INTO audit_journal_inflight VALUES (?,?,?)',('not-authorized',1,99))
        db.execute('INSERT INTO orchestration_events VALUES (?,?,?,?,?)',
                   ('new','not-authorized','orchestration.capability.invoking','service.unknown.read','2026-11-24T00:00:00+00:00'))
    with pytest.raises(JournalUnavailable,match='RESERVATIONS_CHANGED'):
        fwd.recover_forward(c,grant)
    assert archive.exists() and source.exists()


def test_recovery_denies_pending_outcome_without_deletion(specimen):
    c,grant,archive,source=specimen
    with sqlite3.connect(c.p.active) as db:
        db.execute("INSERT INTO audit_journal_pending_outcomes VALUES ('pending',1234567890)")
    with pytest.raises(JournalUnavailable,match='PENDING_PROVIDER_OUTCOMES'):
        fwd.recover_forward(c,grant)
    assert archive.exists() and source.exists()


def test_recovery_denies_unsigned_scope(specimen):
    c,grant,archive,source=specimen
    grant['no_legacy_rebuild']=False
    with pytest.raises(JournalUnavailable,match='EXACT_NO_REBUILD_OWNER_GRANT'):
        fwd.recover_forward(c,grant)
    assert source.exists()


def test_missing_source_requires_prior_verified_reclaim_receipt(specimen):
    c,grant,archive,source=specimen
    source.unlink()
    with pytest.raises(FileNotFoundError):
        fwd.recover_forward(c,grant)
    assert archive.exists()


def test_same_filesystem_archive_rejected_without_mock(tmp_path):
    archive=tmp_path/'archive.sqlite3';active=tmp_path/'active.sqlite3'
    archive.write_bytes(b'x');archive.chmod(0o440);os.chown(archive,-1,os.getgid());active.write_bytes(b'y')
    record={'id':'a'*32,'state':'sealed','proof':{'integrity':'ok','restore_verified':True,
            'events':1,'file_sha256':'a'*64},'fingerprint':fingerprint(archive.stat())}
    p=SimpleNamespace(archives=tmp_path,active=active,custody_uid=os.getuid(),writer_uid=os.getgid(),
                      artifact=lambda r:archive)
    with pytest.raises(JournalUnavailable,match='ARCHIVE_INDEPENDENT_FILESYSTEM'):
        fwd.exact_sealed(p,record)


@pytest.mark.parametrize('events', [0,1,2,100])
def test_archive_probe_matches_sealed_event_count_even_when_empty(specimen,events):
    c,grant,archive,source=specimen
    c._sql=lambda op,args,seconds=30:{'reads_verified':True,
         'event_probes':min(events,2),'provider_contacted':False}
    assert fwd.archive_readback(c,archive,events)['reads_verified'] is True
    with pytest.raises(JournalUnavailable,match='ARCHIVE_READER_NOT_VERIFIED'):
        fwd.archive_readback(c,archive,0 if events>=2 else 2)


def test_maintenance_never_constructs_legacy_database(specimen,monkeypatch):
    c,grant,archive,source=specimen
    fwd.recover_forward(c,grant)
    result=fwd.maintenance_step(c,grant,force_initial=True)
    assert result['status']=='rotated' and c.p.catalog()['epoch']=='next-current-epoch'
    assert c.requests.count('rotate_without_legacy_reconstruction')==1
    assert not source.exists() and archive.exists()
    assert all(x not in c.requests for x in ('rebuild','legacy_restore_proof','prepare_rollback'))


def test_bounded_reclaim_recovers_prepared_receipt_before_unlink(specimen):
    c,grant,archive,source=specimen
    rec=c.p.catalog()['segments'][0]
    receipt=fwd.RECEIPTS/('forward-reclaim-'+rec['id']+'.json')
    prepared={'scope_sha256':grant['scope_sha256'],'segment_id':rec['id'],
              'archive_sha256':rec['proof']['file_sha256'],
              'source_fingerprint':fingerprint(source.stat()),
              'archive_fingerprint':fingerprint(archive.stat()),
              'status':'prepared','no_legacy_rebuild':True,'provider_calls':0}
    c._json(receipt,prepared,0o400)
    result=fwd.recover_forward(c,grant)
    assert result['status']=='admissions_restored'
    assert not source.exists() and archive.exists()
    assert json.loads(receipt.read_text())['status']=='reclaimed'


def test_bounded_reclaim_recovers_prepared_receipt_after_unlink(specimen):
    c,grant,archive,source=specimen
    rec=c.p.catalog()['segments'][0]
    receipt=fwd.RECEIPTS/('forward-reclaim-'+rec['id']+'.json')
    prepared={'scope_sha256':grant['scope_sha256'],'segment_id':rec['id'],
              'archive_sha256':rec['proof']['file_sha256'],
              'source_fingerprint':fingerprint(source.stat()),
              'archive_fingerprint':fingerprint(archive.stat()),
              'status':'prepared','no_legacy_rebuild':True,'provider_calls':0}
    c._json(receipt,prepared,0o400)
    source.unlink()
    result=fwd.recover_forward(c,grant)
    assert result['status']=='admissions_restored'
    assert result['reclaim']['status']=='already_reclaimed'
    assert archive.exists() and not source.exists()
    assert json.loads(receipt.read_text())['status']=='reclaimed'


def test_reclaim_denies_changed_prepared_receipt_without_deletion(specimen):
    c,grant,archive,source=specimen
    rec=c.p.catalog()['segments'][0]
    receipt=fwd.RECEIPTS/('forward-reclaim-'+rec['id']+'.json')
    c._json(receipt,{'scope_sha256':grant['scope_sha256'],
                     'source_fingerprint':fingerprint(source.stat()),
                     'archive_fingerprint':fingerprint(archive.stat()),
                     'archive_sha256':'0'*64,'status':'prepared'},0o400)
    with pytest.raises(JournalUnavailable,match='PARTIAL_RECLAIM_RECEIPT_CHANGED'):
        fwd.recover_forward(c,grant)
    assert archive.exists() and source.exists()


def test_native_acceptance_requires_real_new_request_after_barrier_removed(specimen,monkeypatch):
    c,grant,archive,source=specimen
    # The safety gate must be deterministic on development, production-sized
    # GitHub runners and low-space CI workers alike. Never inspect host space.
    monkeypatch.setattr(fwd.shutil,'disk_usage',lambda _:SimpleNamespace(free=10_000_000_000))
    fwd.recover_forward(c,grant)
    with pytest.raises(JournalUnavailable,match='REAL_POST_BARRIER_REQUEST_NOT_OBSERVED'):
        fwd.safe_native_acceptance(c,grant)
    with sqlite3.connect(c.p.active) as db:
        db.execute('INSERT INTO orchestration_events VALUES (?,?,?,?,?)',
                   ('genuine-observation','ordinary-request','orchestration.request.received',
                    'service.configuration.read','2099-01-01T00:00:00+00:00'))
    with pytest.raises(JournalUnavailable,match='ROOT_DISK_RECLAIM_NOT_OBSERVED'):
        fwd.safe_native_acceptance(c,grant)


def test_owner_bound_desired_state_can_add_only_exact_one_shot_unit():
    initial={'required_system_units':['jason-audit-journal-maintenance.timer'],
             'allowed_system_units':['jason-audit-journal-release.service'],
             'denied_actions':['production-reboot'], 'max_stopped_rollback_containers':27}
    copy=json.loads(json.dumps(initial))
    final=fwd.reviewed_forward_desired(initial)
    assert final['allowed_system_units']==['jason-audit-journal-no-restore-release.service',
                                          'jason-audit-journal-release.service']
    assert final['required_system_units']==initial['required_system_units']
    assert final['denied_actions']==initial['denied_actions']
    assert initial==copy
    with pytest.raises(JournalUnavailable,match='EXACT_PREVIOUS_FINAL_DESIRED_POLICY'):
        fwd.reviewed_forward_desired(final)


def test_interrupted_exact_recovery_resumes_after_new_segment_epoch(specimen):
    c,grant,archive,source=specimen
    assert fwd.recover_forward(c,grant)['status']=='admissions_restored'
    assert fwd.maintenance_step(c,grant,force_initial=True)['status']=='rotated'
    assert c.p.catalog()['epoch']!='sealed-initial'
    resumed=fwd.recover_forward(c,grant)
    assert resumed['status']=='admissions_restored'
    assert resumed['recovered_prior_bounded_attempt'] is True
    assert resumed['unknown_results_preserved']==3
    assert not source.exists() and archive.exists()
    assert c.requests.count('barrier')==1
    assert 'rebuild' not in c.requests and 'legacy_restore_proof' not in c.requests


def test_interrupted_recovery_rejects_forged_admission_receipt(specimen):
    c,grant,archive,source=specimen
    fwd.recover_forward(c,grant)
    path=fwd.ADMISSION_RECEIPT
    row=json.loads(path.read_text());row['scope_sha256']='0'*64
    c._json(path,row,0o400)
    with pytest.raises(JournalUnavailable,match='PREVIOUS_ADMISSION_RECEIPT_CHANGED'):
        fwd.recover_forward(c,grant)
    assert archive.exists()


def test_interrupted_recovery_rejects_reintroduced_admission_barrier(specimen):
    c,grant,archive,source=specimen
    fwd.recover_forward(c,grant)
    from orchestrator.journal_sql import admission_barrier
    admission_barrier(c.p.active,True)
    with pytest.raises(JournalUnavailable,match='PREVIOUS_BARRIER_REAPPEARED'):
        fwd.recover_forward(c,grant)
    assert archive.exists()


def test_original_one_use_grant_expires_for_recovery_and_cannot_replay():
    now=datetime.now(timezone.utc)
    grant={'approved_at':now.isoformat(),'scope_sha256':'f'*64}
    fwd.validate_execution_window(grant,'recover',now=now)
    fwd.validate_execution_window(grant,'recover',now=now+timedelta(hours=7))
    with pytest.raises(JournalUnavailable,match='EXPIRED_ONE_USE_ROOT_GRANT'):
        fwd.validate_execution_window(grant,'recover',now=now+timedelta(hours=9))
    with pytest.raises(JournalUnavailable,match='OWNER_APPROVAL_FROM_FUTURE'):
        fwd.validate_execution_window(grant,'recover',now=now-timedelta(minutes=1))


def test_post_expiry_maintenance_requires_exact_accepted_health_and_rollover(monkeypatch):
    now=datetime.now(timezone.utc)
    grant={'approved_at':(now-timedelta(days=1)).isoformat(),'scope_sha256':'f'*64}
    native={'phase':'accepted','scope_sha256':'f'*64,'no_legacy_rebuild':True,
            'full_health':'pass','drift':'pass'}
    rollover={'scope_sha256':'f'*64,'completed':True,'native_verified':True}
    monkeypatch.setattr(fwd,'read_control',lambda path,uid,mode: native if str(path).endswith('forward-release-status.json') else rollover)
    fwd.validate_execution_window(grant,'maintain',now=now)
    with pytest.raises(JournalUnavailable,match='EXPIRED_ONE_USE_ROOT_GRANT'):
        fwd.validate_execution_window(grant,'recover',now=now)
    rollover['native_verified']=False
    with pytest.raises(JournalUnavailable,match='DAILY_MAINTENANCE_NOT_ACCEPTED'):
        fwd.validate_execution_window(grant,'maintain',now=now)
    rollover['native_verified']=True
    native['scope_sha256']='0'*64
    with pytest.raises(JournalUnavailable,match='DAILY_MAINTENANCE_NOT_ACCEPTED'):
        fwd.validate_execution_window(grant,'maintain',now=now)


def test_failed_acceptance_releases_active_sqlite_fd_before_retry(specimen):
    """Avoid holding live SQLite across the five-second acceptance retry wait.

    A Python sqlite3 Connection context manager commits but DOES NOT close.
    A pending exception retains the function frame/connection while the
    approval-bound release worker sleeps; that blocks the real scheduled
    rotation through JOURNAL_LEGACY_HANDLE_STILL_OPEN.
    """
    c,grant,archive,source=specimen
    fwd.recover_forward(c,grant)
    active=c.p.active
    stat=active.stat()
    def holders():
        found=[]
        for candidate in Path('/proc/self/fd').iterdir():
            try:metadata=candidate.stat()
            except OSError:continue
            if (metadata.st_dev,metadata.st_ino)==(stat.st_dev,stat.st_ino):
                found.append(candidate.name)
        return found
    baseline=set(holders())
    try:
        fwd.safe_native_acceptance(c,grant)
    except JournalUnavailable as e:
        assert 'FORWARD_REAL_POST_BARRIER_REQUEST_NOT_OBSERVED' in str(e)
        assert set(holders())-baseline==set(), 'Live acceptance kept additional SQLite FD open during retry'
    else:raise AssertionError('expected genuine missing request safety gate')
