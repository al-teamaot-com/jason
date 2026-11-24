"""Strictly forward-only, Root-governed segmented audit journal recovery.

No full legacy SQLite reconstruction, copy, mount, rollback, or provider call.
This module is source-only until an independently authenticated, exact-scope
Root installer publishes immutable bytes and a one-use Root grant. A journal
receipt is not a replacement for that grant or an approval system.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager, ExitStack
import fcntl
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
import shutil
import stat
import subprocess
import sys
import time

from orchestrator import journal_sql
from orchestrator.segmented_journal import JournalUnavailable, fingerprint, need, read_control
from tools import audit_journal_control as old

SOURCE = Path('/usr/local/lib/jason/audit-journal-forward-v1/audit_journal_no_restore_worker.py')
GRANT = Path('/var/lib/jason-audit-journal/private/no-restore-grant.json')
RECEIPTS = Path('/var/lib/jason-audit-journal/private')
ADMISSION_RECEIPT = RECEIPTS / 'forward-admission-recovered.json'
ROLLOVER_RECEIPT = RECEIPTS / 'forward-first-scheduled-rollover.json'
ACTION = 'RECOVER-SEGMENTED-AUDIT-WITHOUT-LEGACY-REBUILD'
APPROVED_PHASES = frozenset(('recovery_authorized',))
NO_RESTORE_OPS = frozenset(('recover','maintain','read-status'))


@contextmanager
def protected_host_mutation():
    """Two existing cross-release locks, held only during bounded mutation.

    The worker MUST NOT run concurrently with another host or PMv4 release.
    Waiting for subsequent health checks never retains either lock.
    """
    from tools import audit_journal_release_scope as scope
    order=((scope.STATE/'production-transaction.lock',1000,0o664),
           (Path('/var/lib/jason/pmv4-shadow/control/host-mutation.lock'),0,0o600))
    with ExitStack() as stack:
        deadline=time.monotonic()+30
        for path,uid,mode in order:
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
            stack.callback(os.close,fd)
            m=os.fstat(fd)
            need(stat.S_ISREG(m.st_mode) and m.st_uid==uid and m.st_nlink==1
                 and stat.S_IMODE(m.st_mode)==mode,
                 'FORWARD_PROTECTED_RELEASE_LOCK_IDENTITY')
            while True:
                try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);break
                except BlockingIOError:
                    need(time.monotonic()<deadline,'FORWARD_OTHER_RELEASE_ACTIVE')
                    time.sleep(0.1)
        for path,expected in scope.PROTECTED.items():
            need(file_digest(Path(path))==expected,
                 'FORWARD_PROTECTED_NATIVE_SOURCE_CHANGED')
        yield


def file_digest(path):
    value=sha256()
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        with os.fdopen(fd,'rb') as stream:
            meta=os.fstat(stream.fileno())
            need(stat.S_ISREG(meta.st_mode) and meta.st_nlink==1,'FORWARD_REGULAR_ONE_LINK')
            for block in iter(lambda:stream.read(1024*1024),b''):
                value.update(block)
    finally:
        # os.fdopen owns and closes the descriptor even after hashing errors.
        pass
    return value.hexdigest()


def exact_sealed(p,record,*,initial=None):
    need(record['state']=='sealed' and record['proof']['integrity']=='ok'
         and record['proof']['restore_verified'] is True
         and record['proof']['events']>=0 and
         len(record['proof']['file_sha256'])==64, 'FORWARD_SEALED_PROOF_REQUIRED')
    if initial is not None:
        need(record['id']==initial['segment_id'] and record['proof']['events']==initial['events']
             and record['proof']['file_sha256']==initial['archive_sha256'],
             'FORWARD_OWNER_SIGNED_HISTORY_CHANGED')
    archive=p.artifact(record)
    meta=archive.lstat()
    need(not archive.is_symlink() and stat.S_ISREG(meta.st_mode) and meta.st_nlink==1
         and meta.st_uid==p.custody_uid and meta.st_gid==p.writer_uid
         and stat.S_IMODE(meta.st_mode)==0o440,'FORWARD_ARCHIVE_CUSTODY')
    need(meta.st_dev!=p.active.parent.stat().st_dev and archive.parent==p.archives,
         'FORWARD_ARCHIVE_INDEPENDENT_FILESYSTEM')
    return archive


def record_reservations(active, expected):
    """Keep unknown results unknown; never erase or invent provider outcomes."""
    import sqlite3
    with sqlite3.connect(active.as_uri()+'?mode=ro',uri=True,timeout=5) as db:
        db.execute('PRAGMA query_only=ON')
        pending=db.execute('SELECT count(*) FROM audit_journal_pending_outcomes').fetchone()[0]
        need(pending==0,'FORWARD_PENDING_PROVIDER_OUTCOMES')
        rows=db.execute('SELECT execution_id,provider_started,remaining_bytes FROM audit_journal_inflight ORDER BY execution_id').fetchall()
        current=[]
        for execution,started,remaining in rows:
            last=db.execute('SELECT event_type,capability_name,occurred_at FROM orchestration_events '
                            'WHERE execution_id=? ORDER BY rowid DESC LIMIT 1',(execution,)).fetchone()
            need(last is not None and started in (0,1) and remaining>=0,
                 'FORWARD_UNRECOGNIZED_RESERVATION')
            # Historical event types are evidence; never assert a provider result.
            need(last[0] in ('orchestration.capability.invoking','orchestration.capability.resolved'),
                 'FORWARD_RESERVATION_UNEXPECTED_EVENT')
            need((started==1)==(last[0]=='orchestration.capability.invoking'),
                 'FORWARD_RESERVATION_PROVIDER_STATE_MISMATCH')
            current.append({'execution_hash':sha256(execution.encode()).hexdigest(),
                            'provider_started':bool(started),
                            'capability':last[1], 'last_event_type':last[0],
                            'last_occurred_at':last[2], 'result':'unknown_not_retried'})
    # Exact set and count is bound to the one-use Owner manifest; do not admit
    # a new/changed provider operation in the middle of recovery.
    need(current==expected,'FORWARD_RESERVATIONS_CHANGED')
    return current


def scope_current(c,grant,*,verify_reservations=True):
    p=c.p
    need(grant['action']==ACTION and grant['no_legacy_rebuild'] is True,
         'FORWARD_EXACT_NO_REBUILD_OWNER_GRANT')
    with p.gate():
        catalog=p.catalog()
        need(catalog['mode']=='segmented' and catalog['generation']>=grant['initial_generation'],
             'FORWARD_SEGMENTED_LINEAGE')
        if verify_reservations:
            need(catalog['epoch']==grant['initial_epoch'] and
                 catalog['generation']==grant['initial_generation'],
                 'FORWARD_INITIAL_GENERATION_CHANGED')
        first=catalog['segments'][0]
        exact_sealed(p,first,initial=grant['original_archive'])
        p.active_identity()
    if verify_reservations and grant['stage'] not in ('accepted',):
        record_reservations(p.active,grant['initial_reservations'])
    return catalog


def archive_readback(c,archive,events):
    out=c._sql('archive_readback',{'source':str(archive),'profile':c.profile_arguments()},seconds=60)
    need(out['reads_verified'] is True and out['event_probes']==min(2,events)
         and out.get('provider_contacted') is False,'FORWARD_ARCHIVE_READER_NOT_VERIFIED')
    return out


def ensure_immutable_worker(grant):
    need(os.geteuid()==0 and sys.flags.isolated==1 and Path(__file__).resolve()==SOURCE,
         'FORWARD_INSTALLED_ROOT_ONLY')
    meta=SOURCE.lstat()
    need(not SOURCE.is_symlink() and stat.S_ISREG(meta.st_mode) and
         meta.st_uid==meta.st_gid==0 and stat.S_IMODE(meta.st_mode)==0o444,
         'FORWARD_REVIEWED_SOURCE_CUSTODY')
    need(file_digest(SOURCE)==grant['source_sha256'],'FORWARD_REVIEWED_SOURCE_CHANGED')
    need(grant['independently_verified_entra_owner'] is True and grant['owner_oid']==old.OWNER,
         'FORWARD_INDEPENDENT_OWNER_REQUIRED')
    need(grant['stage'] in APPROVED_PHASES,'FORWARD_APPROVED_STAGE_REQUIRED')
    need(grant['scope_sha256']==sha256(old.canonical(grant['scope'])).hexdigest(),
         'FORWARD_IMMUTABLE_OWNER_SCOPE_CHANGED')
    need(grant['scope']['action']==ACTION and grant['scope']['no_legacy_rebuild'] is True
         and grant['scope']['candidate_sha']==grant['candidate_sha'],
         'FORWARD_OWNER_SCOPE_ACTION')
    need(grant['scope']['source_sha256']==grant['source_sha256'],
         'FORWARD_OWNER_SCOPE_SOURCE')


def verify_and_reclaim(c,record,grant):
    """One exact redundant original image; never the canonical live journal."""
    p=c.p
    with p.gate():
        catalog=p.catalog()
        need(catalog['mode']=='segmented','FORWARD_SEGMENTED_REQUIRED')
        need(record in catalog['segments'],'FORWARD_SEGMENT_CHANGED')
        generation=catalog['generation']
        archive=exact_sealed(p,record,
             initial=grant['original_archive'] if record['id']==grant['original_archive']['segment_id'] else None)
        before=p.pending/record['proof']['source_before_image']
        receipt=RECEIPTS/('forward-reclaim-'+record['id']+'.json')
        if not before.exists():
            # Retain exact historical metadata. After interruption between
            # source unlink and durable confirmation, independently revalidate
            # archive and finalize only the already-prepared receipt.
            row=read_control(receipt,p.custody_uid,0o400)
            need(row['status'] in ('prepared','reclaimed')
                 and row['scope_sha256']==grant['scope_sha256']
                 and row['archive_sha256']==record['proof']['file_sha256']
                 and row['source_fingerprint']==record['proof']['source_before_fingerprint'],
                 'FORWARD_MISSING_SOURCE_WITHOUT_RECEIPT')
            if row['status']=='prepared':
                need(file_digest(archive)==record['proof']['file_sha256'],
                     'FORWARD_INTERRUPTED_RECLAIM_ARCHIVE_CHANGED')
                archive_readback(c,archive,record['proof']['events'])
                c._json(receipt,{**row,'status':'reclaimed',
                                  'reclaimed_at':datetime.now(timezone.utc).isoformat()},0o400)
            return {'status':'already_reclaimed','segment_id':record['id']}
        before_meta=before.lstat()
        need(not before.is_symlink() and stat.S_ISREG(before_meta.st_mode) and
             before_meta.st_nlink==1 and before_meta.st_uid==p.custody_uid and
             before_meta.st_gid==p.writer_uid and stat.S_IMODE(before_meta.st_mode)==0o440,
             'FORWARD_SOURCE_CUSTODY')
        need(before!=p.active and before.parent==p.pending and
             fingerprint(before_meta)==record['proof']['source_before_fingerprint'] and
             before_meta.st_dev==p.active.parent.stat().st_dev,
             'FORWARD_BEFORE_IMAGE_FINGERPRINT_CHANGED')
        prior=read_control(receipt,p.custody_uid,0o400) if receipt.exists() else None
        if prior is not None:
            need(prior.get('status')=='prepared'
                 and prior.get('scope_sha256')==grant['scope_sha256']
                 and prior.get('archive_sha256')==record['proof']['file_sha256']
                 and prior.get('source_fingerprint')==record['proof']['source_before_fingerprint']
                 and prior.get('archive_fingerprint')==record['fingerprint'],
                 'FORWARD_PARTIAL_RECLAIM_RECEIPT_CHANGED')
    # Hash both actual complete files, independently. No copy/restore created.
    expected=record['proof']['file_sha256']
    need(file_digest(archive)==expected,'FORWARD_ARCHIVE_SHA_MISMATCH')
    need(file_digest(before)==expected,'FORWARD_BEFORE_IMAGE_SHA_MISMATCH')
    archive_readback(c,archive,record['proof']['events'])
    with c.serialized(),p.gate(exclusive=True):
        now=p.catalog()
        need(now['generation']==generation and record in now['segments'],
             'FORWARD_CATALOG_CHANGED_DURING_HASH')
        need(p.artifact(record)==archive and
             fingerprint(archive.lstat())==record['fingerprint'],
             'FORWARD_ARCHIVE_FINGERPRINT_CHANGED')
        need(fingerprint(before.lstat())==record['proof']['source_before_fingerprint'],
             'FORWARD_BEFORE_IMAGE_CHANGED_DURING_HASH')
        old.require_no_handles(before)
        proof={'scope_sha256':grant['scope_sha256'],'segment_id':record['id'],
               'archive_sha256':expected,'source_fingerprint':fingerprint(before.lstat()),
               'archive_fingerprint':fingerprint(archive.lstat()),
               'verified_at':datetime.now(timezone.utc).isoformat(),
               'status':'prepared','no_legacy_rebuild':True,'provider_calls':0}
        if prior is None:c._json(receipt,proof,0o400)
        else:
            need(prior['source_fingerprint']==proof['source_fingerprint']
                 and prior['archive_fingerprint']==proof['archive_fingerprint']
                 and prior['archive_sha256']==proof['archive_sha256'],
                 'FORWARD_PREPARED_RECLAIM_REPLAY_CHANGED')
        before.unlink()
        old.sync(before.parent)
        c._json(receipt,{**proof,'status':'reclaimed',
                         'reclaimed_at':datetime.now(timezone.utc).isoformat()},0o400)
    return {'status':'reclaimed','segment_id':record['id'],'verified_source_bytes':proof['source_fingerprint']['bytes']}


def recover_forward(c,grant):
    """Retain reservations and original evidence; no provider replay."""
    scope_current(c,grant)
    need(not c.intent.exists() and not (c.private/'rollback-mounted.json').exists(),
         'FORWARD_UNRESOLVED_TRANSITION')
    initial=c.p.catalog()['segments'][0]
    # Do not clear the admission barrier before data lineage is independently
    # verified and original/source file custody survives an interruption.
    reclaim=verify_and_reclaim(c,initial,grant)
    record_reservations(c.p.active,grant['initial_reservations'])
    c._sql('barrier',{'path':str(c.p.active),'enabled':False},seconds=15)
    import sqlite3
    with sqlite3.connect(c.p.active.as_uri()+'?mode=ro',uri=True,timeout=3) as db:
        triggers=db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'audit_journal_maintenance_%'").fetchall()
        need(not triggers,'FORWARD_BARRIER_REMAINS')
    c._json(ADMISSION_RECEIPT,{'scope_sha256':grant['scope_sha256'],
             'status':'admissions_restored','unknown_reservations_retained':len(grant['initial_reservations']),
             'no_legacy_rebuild':True,'observed_at':datetime.now(timezone.utc).isoformat()},0o400)
    return {'status':'admissions_restored','reclaim':reclaim,
            'unknown_results_preserved':len(grant['initial_reservations']),
            'no_legacy_rebuild':True}


def maintenance_step(c,grant,*,now=None,force_initial=False):
    """One bounded scheduled step; no path to legacy reconstruction."""
    now=now or datetime.now(timezone.utc)
    scope_current(c,grant,verify_reservations=False)
    receipt=read_control(ADMISSION_RECEIPT,c.p.custody_uid,0o400)
    need(receipt.get('scope_sha256')==grant['scope_sha256']
         and receipt.get('status')=='admissions_restored',
         'FORWARD_INITIAL_ADMISSION_RECOVERY_REQUIRED')
    with c.p.gate():
        catalog=c.p.catalog()
        pending=[r for r in catalog['segments'] if r['state']=='pending']
        due=force_initial or c.p.active_bytes()>=c.p.target_bytes
        local=now.astimezone(ZoneInfo('America/New_York'))
        midnight=local.replace(hour=0,minute=15,second=0,microsecond=0)
        if local<midnight:midnight-=timedelta(days=1)
        due=due or datetime.fromisoformat(catalog['opened_at'])<midnight.astimezone(timezone.utc)
        sealed=[r for r in catalog['segments'] if r['state']=='sealed']
    if pending:
        return c.seal_one(seconds=10800)
    for r in sealed:
        if (c.p.pending/r['proof']['source_before_image']).exists():
            return verify_and_reclaim(c,r,grant)
    if due:
        active=journal_sql.active_state(c.p.active)
        need(active['pending_outcomes']==0,'FORWARD_UNRECONCILED_OUTCOMES')
        return c.transition(initial=False)
    return c.scrub_one(now=now)


def reviewed_forward_desired(old_final):
    # The original final desired-state policy is already independently SHA
    # bound in the consumed historical release. Modify exactly ONE allowed unit.
    unit='jason-audit-journal-no-restore-release.service'
    need(isinstance(old_final,dict) and
         'jason-audit-journal-maintenance.timer' in old_final.get('required_system_units',[]) and
         'jason-audit-journal-release.service' in old_final.get('allowed_system_units',[]) and
         unit not in old_final.get('allowed_system_units',[]) and
         unit not in old_final.get('required_system_units',[]),
         'FORWARD_EXACT_PREVIOUS_FINAL_DESIRED_POLICY')
    amended=json.loads(json.dumps(old_final))
    amended['allowed_system_units'].append(unit)
    amended['allowed_system_units'].sort()
    need(set(amended)==set(old_final) and
         all(amended[k]==old_final[k] for k in old_final if k!='allowed_system_units'),
         'FORWARD_NO_UNRELATED_DESIRED_STATE_CHANGE')
    return amended


def safe_native_acceptance(c,grant):
    """Verify actual independent full/fast/drift and protected breaker."""
    from tools import audit_journal_release_scope as scope
    import sqlite3
    p=c.p
    with p.gate():
        cat=p.catalog()
        need(cat['mode']=='segmented' and cat['segments'][0]['id']==grant['original_archive']['segment_id']
             and cat['segments'][0]['state']=='sealed',
             'FORWARD_EXPECTED_PROTECTED_ARCHIVE')
        need(all(r['state']=='sealed' for r in cat['segments']),
             'FORWARD_PENDING_ARCHIVE_SEGMENT')
    before=p.pending/(grant['original_archive']['segment_id']+'.sqlite3')
    need(not before.exists(),'FORWARD_BEFORE_IMAGE_RECLAIM_NOT_COMPLETE')
    with sqlite3.connect(p.active.as_uri()+'?mode=ro',uri=True,timeout=2) as db:
        present=db.execute("SELECT name FROM sqlite_master WHERE type='trigger' "
                           "AND name LIKE 'audit_journal_maintenance_%'").fetchall()
        admission=read_control(ADMISSION_RECEIPT,p.custody_uid,0o400)
        need(admission.get('scope_sha256')==grant['scope_sha256']
             and admission.get('status')=='admissions_restored',
             'FORWARD_ADMISSION_RECEIPT_NOT_VERIFIED')
        new_count=db.execute("SELECT count(*) FROM orchestration_events "
                 "WHERE event_type='orchestration.request.received' AND occurred_at>?",
                 (admission['observed_at'],)).fetchone()[0]
    need(not present,'FORWARD_NEW_ADMISSION_STILL_BLOCKED')
    need(new_count>=1,'FORWARD_REAL_POST_BARRIER_REQUEST_NOT_OBSERVED')
    root_free=shutil.disk_usage(p.active.parent).free
    need(root_free>35_000_000_000,'FORWARD_ROOT_DISK_RECLAIM_NOT_OBSERVED')
    timer=subprocess.run(['/usr/bin/systemctl','show','jason-audit-journal-maintenance.timer',
         '-p','ActiveState','-p','UnitFileState'],capture_output=True,text=True,timeout=10,check=False)
    need(timer.returncode==0 and 'ActiveState=active' in timer.stdout
         and 'UnitFileState=enabled' in timer.stdout,
         'FORWARD_DAILY_TIMER_NOT_ACTIVE')
    maintenance=read_control(p.control/'maintenance-status.json',p.custody_uid,0o444)
    need(maintenance.get('status')=='scheduled_no_restore_verified'
         and maintenance.get('first_scheduled_rollover_verified') is True
         and maintenance.get('native_health',{}).get('status') in
             ('existing_native_full_fast_drift_and_revalidation_verified',
              'current_native_full_evidence_observed'),
         'FORWARD_MAINTENANCE_NOT_VERIFIED')
    full=json.loads(Path('/var/lib/jason/openclaw/operational-full-health.json').read_text())
    fast=json.loads(Path('/var/lib/jason/openclaw/operational-health.json').read_text())
    drift=json.loads((scope.STATE/'production-drift.json').read_text())
    control=json.loads((scope.STATE/'production-control-state.json').read_text())
    coverage=full.get('orchestration_journal',{})
    need(full.get('status')=='pass' and full.get('failures')==[]
         and fast.get('status')=='pass' and fast.get('failures')==[]
         and coverage.get('integrity')=='ok' and coverage.get('mode')=='segmented'
         and coverage.get('closed_segments')==len(cat['segments'])
         and coverage.get('catalog_sha256')==sha256(old.canonical(cat)).hexdigest(),
         'FORWARD_ACTUAL_CURRENT_FULL_FAST_HEALTH_NOT_PASS')
    observed=datetime.fromisoformat(drift['observed_at'].replace('Z','+00:00'))
    delay=(datetime.now(timezone.utc)-observed).total_seconds()
    need(drift.get('status')=='pass' and drift.get('problems')==[]
         and 0<=delay<=180
         and control.get('circuit_breaker',{}).get('state')=='closed',
         'FORWARD_INDEPENDENT_FRESH_DRIFT_BREAKER_NOT_PASS')
    for name,expected in scope.PROTECTED.items():
        need(file_digest(Path(name))==expected,'FORWARD_NATIVE_PROTECTED_SOURCE_CHANGED')
    peers=scope.protected_peer_inventory()
    need(len(peers)==len(scope.EXPECTED_PEER_IMAGES),
         'FORWARD_ALL_NATIVE_PROTECTED_PEERS_REQUIRED')
    return {'status':'accepted','root_free_bytes':root_free,'sealed_segments':len(cat['segments']),
            'initial_archive_events':grant['original_archive']['events'],
            'full_health':'pass','fast_health':'pass','drift':'pass','breaker':'closed',
            'provider_calls':0,'no_legacy_rebuild':True}


def finish_recovery(c,grant):
    """Original worker stays disabled; this exact service owns acceptance."""
    from tools import audit_journal_release_scope as scope
    def progress(phase,**extra):
        c._json(c.p.control/'forward-release-status.json',
                {'schema_version':'1.0','action':ACTION,'phase':phase,
                 'scope_sha256':grant['scope_sha256'],
                 'observed_at':datetime.now(timezone.utc).isoformat(),**extra},0o444)
    progress('verifying_sealed_archive_without_legacy_rebuild')
    release=subprocess.run(['/usr/bin/systemctl','show','jason-audit-journal-release.service',
                 '-p','MainPID','-p','UnitFileState'],capture_output=True,text=True,timeout=15,check=False)
    need(release.returncode==0 and 'MainPID=0' in release.stdout
         and 'UnitFileState=disabled' in release.stdout,
         'FORWARD_FAILED_RESTORE_WORKER_BOOT_NOT_DISABLED')
    with protected_host_mutation():
        result=recover_forward(c,grant)
        progress('admissions_restored_history_archived_and_root_copy_reclaimed',
                 retained_unknown_reservations=result['unknown_results_preserved'])
        finish_initial_native_setup(c,grant)
    progress('awaiting_actual_no_restore_daily_rollover_and_native_health')
    deadline=time.monotonic()+7200
    while time.monotonic()<deadline:
        try:
            accepted=safe_native_acceptance(c,grant)
        except (FileNotFoundError,KeyError,ValueError,RuntimeError,JournalUnavailable):
            time.sleep(5)
            continue
        progress('accepted',**accepted)
        return accepted
    raise RuntimeError('FORWARD_NATIVE_SCHEDULED_ACCEPTANCE_DEADLINE')


def finish_initial_native_setup(c,grant):
    """Use previous exact final policy and only one newly signed unit allowance."""
    from tools import audit_journal_release_scope as scope
    old_plan=read_control(c.private/'release-plan.json',0,0o400)
    old_final=read_control(c.private/'desired-final.json',0,0o400)
    final_digest=sha256(old.canonical(old_final)).hexdigest()
    need(old_plan['scope']['desired_state_after_sha256']==final_digest and
         old_plan['candidate_sha']==grant['scope']['prior_failed_candidate_sha'],
         'FORWARD_PREVIOUS_FINAL_DESIRED_SCOPE')
    desired=read_control(scope.DESIRED,0,0o600)
    initial=old_plan['scope']['desired_state_initial_sha256']
    need(sha256(old.canonical(desired)).hexdigest() in (initial,final_digest),
         'FORWARD_DESIRED_POLICY_UNEXPECTED')
    # Keep every old final policy field unchanged. The only addition is the
    # separately Owner-authorized one-shot recovery unit's allow-list entry.
    amended=reviewed_forward_desired(old_final)
    need(sha256(old.canonical(amended)).hexdigest()==
         grant['scope']['immutable_evidence']['new_desired_sha256'],
         'FORWARD_NEW_DESIRED_POLICY_NOT_OWNER_BOUND')
    c._json(scope.DESIRED,amended,0o600)
    enable=subprocess.run(['/usr/bin/systemctl','enable','--now','jason-audit-journal-maintenance.timer'],
                          capture_output=True,text=True,timeout=30,check=False)
    need(enable.returncode==0,'FORWARD_MAINTENANCE_TIMER_ACTIVATION_FAILED')


def root_main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--operation',choices=tuple(sorted(NO_RESTORE_OPS)),required=True)
    args=parser.parse_args()
    grant=read_control(GRANT,0,0o400)
    ensure_immutable_worker(grant)
    c=old.root_controller()
    if args.operation=='read-status':
        result={'status':c.status(),'no_legacy_rebuild':True}
    elif args.operation=='recover':
        result=finish_recovery(c,grant)
    else:
        scope_current(c,grant,verify_reservations=False)
        initial=ROLLOVER_RECEIPT
        if initial.exists():
            first=read_control(initial,0,0o400)
            need(first.get('scope_sha256')==grant['scope_sha256'],
                 'FORWARD_FIRST_ROLLOVER_SCOPE_CHANGED')
        else:
            first={'scope_sha256':grant['scope_sha256'],
                   'before_epoch':c.p.catalog()['epoch'], 'completed':False,
                   'scheduled_started_at':datetime.now(timezone.utc).isoformat()}
            c._json(initial,first,0o400)
        steps=[]
        for step in range(12):
            epoch=c.p.catalog()['epoch']
            force=not first['completed'] and epoch==first['before_epoch']
            result=maintenance_step(c,grant,force_initial=force)
            steps.append(result)
            if result.get('status') in ('no_history','scrub_not_due'):
                break
        else:raise RuntimeError('FORWARD_MAINTENANCE_STEP_BOUND')
        current=c.p.catalog()
        need(current['epoch']!=first['before_epoch'] and
             all(r['state']=='sealed' for r in current['segments']),
             'FORWARD_FIRST_SCHEDULED_ROLLOVER_NOT_COMPLETE')
        if not first['completed']:
            first={**first,'completed':True,'after_epoch':current['epoch'],
                   'observed_at':datetime.now(timezone.utc).isoformat()}
            c._json(initial,first,0o400)
        native=c.ensure_native_full_health(force_revalidate=first.get('native_verified') is not True)
        if native.get('status')=='existing_native_full_fast_drift_and_revalidation_verified' and not first.get('native_verified'):
            first={**first,'native_verified':True,
                   'native_verified_at':datetime.now(timezone.utc).isoformat()}
            c._json(initial,first,0o400)
        result={'status':'scheduled_no_restore_verified','steps':steps,
                'first_scheduled_rollover_verified':True,
                'native_health':native,'no_legacy_rebuild':True}
        c._json(c.p.control/'maintenance-status.json',
                {**result,'observed_at':datetime.now(timezone.utc).isoformat()},0o444)
    print(json.dumps(result,sort_keys=True),flush=True)


if __name__=='__main__':
    try:root_main()
    except Exception as exc:
        raise SystemExit('DENIED:'+type(exc).__name__+':'+str(exc).split(':')[0][:160])
