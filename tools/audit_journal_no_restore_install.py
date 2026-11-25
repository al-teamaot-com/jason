"""One new exact, independently authenticated Root-only journal forward rescue.

Source-only until protected Main CI and Root Owner auth pass. No reliance on a
prior consumed grant; no broad production release mechanism and no legacy DB
reconstruction, provider retry, forced reservation deletion, or boot restart.
"""
from __future__ import annotations
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import json,os,re,stat,sqlite3,subprocess,sys

from tools import audit_journal_install_transaction as txlib
from tools import audit_journal_no_restore_worker as worker
from orchestrator.segmented_journal import JournalProfile,fingerprint

ACTION=worker.ACTION
OLD_CANDIDATE='1a8754efba20e1f1a700c6f9fb9ad9823b839b04'
OLD_SCOPE='000dcc2a2eb6e02db8d7a7424577b23e50b009d3bb6f85da9614ea08692b7d09'
FIRST_SEGMENT='6c04146d67564c5da2a62ecd3864236f'
FIRST_EVENTS=34_616_410
FIRST_SHA256='7b7971deba835d225d2b22410c4530119e421a4efb01407b6b0017dd8bde449c'
RECORD=Path('/var/lib/jason-owner-release/audit-journal-no-restore-v1')
SOURCE=worker.SOURCE
GRANT=worker.GRANT
MAINTENANCE_DROPIN=Path('/etc/systemd/system/jason-audit-journal-maintenance.service.d/95-forward-no-rebuild.conf')
FAST_DROPIN=Path('/etc/systemd/system/jason-openclaw-authority-health.service.d/95-journal-wal-shm.conf')
FULL_DROPIN=Path('/etc/systemd/system/jason-openclaw-authority-full-integrity.service.d/95-journal-wal-shm.conf')
RELEASE_UNIT=Path('/etc/systemd/system/jason-audit-journal-no-restore-release.service')
OWNER=worker.old.OWNER
SAFE_READ_CAPABILITIES=frozenset(('service.configuration.read','backup.endpoint.asset.search','endpoint.device.read'))
# The three existing read-only reservations were observed during the
# 2026-11-24 production cutover. These immutable evidence timestamps remain
# valid after 24 hours; current-time age is NOT a provider-result guarantee.
# New/different reservations remain denied by identity, stage and Owner scope.
INCIDENT_RESERVATION_EARLIEST=datetime(2026,11,24,18,0,tzinfo=timezone.utc)
INCIDENT_RESERVATION_LATEST=datetime(2026,11,24,19,0,tzinfo=timezone.utc)


def need(ok,why):
    if not ok:raise PermissionError('JOURNAL_FORWARD_'+why)


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(raw):return sha256(raw if isinstance(raw,bytes) else canonical(raw)).hexdigest()


def status(I,unit):
    result=I.command(['/usr/bin/systemctl','show',unit,'-p','ActiveState','-p','SubState',
                      '-p','MainPID','-p','Result','-p','UnitFileState'])
    return dict(line.split('=',1) for line in result.splitlines() if '=' in line)


def live_reservations(active):
    """No payload, credentials or provider retries; only durable facts."""
    with sqlite3.connect(active.as_uri()+'?mode=ro',uri=True,timeout=3) as c:
        c.execute('PRAGMA query_only=ON')
        need(c.execute('SELECT count(*) FROM audit_journal_pending_outcomes').fetchone()[0]==0,
             'UNKNOWN_PENDING_OUTCOME')
        rows=c.execute('SELECT execution_id,provider_started,remaining_bytes FROM audit_journal_inflight '
                       'ORDER BY execution_id').fetchall()
        need(len(rows)==3 and sum(r[1] for r in rows)==2,'THREE_KNOWN_RESERVATIONS_ONLY')
        found=[]
        for execution,started,remaining in rows:
            event=c.execute('SELECT event_type,capability_name,occurred_at FROM orchestration_events '
                            'WHERE execution_id=? ORDER BY rowid DESC LIMIT 1',(execution,)).fetchone()
            need(event is not None and event[1] in SAFE_READ_CAPABILITIES and
                 event[0]==('orchestration.capability.invoking' if started else 'orchestration.capability.resolved')
                 and remaining>=0,'READ_ONLY_RESERVATION_PROVENANCE')
            old_at=datetime.fromisoformat(event[2].replace('Z','+00:00'))
            need(old_at.tzinfo is not None and
                 INCIDENT_RESERVATION_EARLIEST<=old_at<=INCIDENT_RESERVATION_LATEST and
                 old_at<=datetime.now(timezone.utc),
                 'READ_ONLY_RESERVATION_TIMESTAMP')
            found.append({'execution_hash':sha256(execution.encode()).hexdigest(),
                          'provider_started':bool(started),'capability':event[1],
                          'last_event_type':event[0],'last_occurred_at':event[2],
                          'result':'unknown_not_retried'})
        names=c.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND "
                        "name LIKE 'audit_journal_maintenance_%'").fetchall()
        need(names==[('audit_journal_maintenance_admission',)],
             'EXACT_KNOWN_ADMISSION_BARRIER')
        return found


def native_units(I):
    release=status(I,'jason-audit-journal-release.service')
    maint=status(I,'jason-audit-journal-maintenance.timer')
    need(release['ActiveState']=='failed' and release['Result']=='exit-code'
         and release['MainPID']=='0' and release['UnitFileState']=='enabled',
         'PREVIOUS_RELEASE_FAILED_QUIESCED')
    need(maint['ActiveState']=='inactive' and maint['UnitFileState']=='disabled',
         'MAINTENANCE_EXPECTED_OFF')
    for unit in ('jason-runtime','jason-mcp-pilot','jason-pmv4-ticket-core'):
        raw=I.command(['/usr/bin/docker','inspect','--format','{{.State.Running}}',unit])
        need(raw=='true','PROTECTED_PRODUCER_NOT_RUNNING')
    return {'release':release,'timer':maint}


def checked_frozen_source(s,payload):
    policy=Path(s.POLICY)
    info=json.loads(txlib.raw_file(policy,0o600))
    trusted=info.get('trusted_source_sha256')
    need(info.get('enabled') is True and
         isinstance(trusted,dict) and set(trusted)==set(s.SOURCES),
         'OLDER_TRUSTED_ROOT_POLICY')
    for name,expected in trusted.items():
        path=s.BASE/'trusted'/name
        m=path.lstat()
        need(not path.is_symlink() and m.st_uid==m.st_gid==0 and m.st_nlink==1
             and stat.S_IMODE(m.st_mode)==0o444 and worker.file_digest(path)==expected,
             'PRIOR_INSTALLED_TRUSTED_SOURCE_CHANGED')
    need(isinstance(payload.get('tools/audit_journal_no_restore_worker.py'),bytes)
         and len(payload['tools/audit_journal_no_restore_worker.py'])<200_000,
         'EXACT_WORKER_BUNDLE_REQUIRED')
    return digest(canonical(info))


def proposed_units(s):
    shm='-'+str(s.ACTIVE)+'-shm'
    # Add a single optional WAL shared-memory file to each existing sandbox;
    # never make the 47GB data or WAL file or parent directory writable.
    health=('[Service]\nReadWritePaths='+shm+'\n').encode()
    loader="import runpy,sys;sys.path.insert(0,'"+str(s.BASE/'trusted/implementation')+"');"+\
           "sys.path.insert(0,'"+str(s.BASE/'trusted')+"');"+\
           "runpy.run_path('"+str(SOURCE)+"',run_name='__main__')"
    execute='/usr/bin/python3 -I -B -c "'+loader+'"'
    maintain=('[Service]\nExecStart=\nExecStart='+execute+' --operation maintain\n').encode()
    release=('''[Unit]
Description=One-use Owner-authenticated Jason audit journal recovery without legacy reconstruction
After=local-fs.target jason-audit-journal-data-recovery.service
Requires=jason-audit-journal-data-recovery.service
RequiresMountsFor=/srv/jason/archive /var/lib/jason/governed-ticket-shared
ConditionPathExists=/var/lib/jason-audit-journal/private/no-restore-grant.json
StartLimitIntervalSec=1h
StartLimitBurst=3

[Service]
Type=oneshot
User=root
Group=root
WorkingDirectory=/usr/local/lib/jason/audit-journal/trusted
'''+ 'ExecStart='+execute+' --operation recover\n'+'''TimeoutStartSec=8h
Restart=on-failure
RestartSec=120
Nice=19
IOSchedulingClass=idle
MemoryMax=768M
TasksMax=16
NoNewPrivileges=true
RestrictAddressFamilies=AF_UNIX AF_NETLINK
CapabilityBoundingSet=CAP_DAC_OVERRIDE CAP_SETUID CAP_SETGID CAP_SYS_PTRACE CAP_KILL
AmbientCapabilities=CAP_SETUID
UMask=0077
''').encode()
    need(shm=='-'+str(s.ACTIVE)+'-shm' and not any(x in shm for x in '*?'),
         'WAL_SCOPE_EXPECTED')
    return {MAINTENANCE_DROPIN:maintain,FAST_DROPIN:health,FULL_DROPIN:health,RELEASE_UNIT:release}


def reviewed_forward_desired(old_final):
    return worker.reviewed_forward_desired(old_final)


def preflight(I,s,candidate,payload):
    need(os.geteuid()==0 and sys.flags.isolated==1,'ISOLATED_ROOT_REQUIRED')
    need(re.fullmatch('[a-f0-9]{40}',candidate or '') is not None,'EXACT_PROTECTED_SOURCE_SHA')
    need(not RECORD.exists() and not GRANT.exists() and not SOURCE.exists()
         and all(not target.exists() for target in proposed_units(s)),
         'NO_SECOND_PRODUCTION_RECOVERY')
    for path,expected in s.PROTECTED.items():
        need(worker.file_digest(Path(path))==expected,'EXISTING_NATIVE_PROTECTED_SOURCE_CHANGED')
    prior_plan=json.loads(txlib.raw_file(s.PRIVATE/'release-plan.json',0o400))
    journal=json.loads(txlib.raw_file(s.PRIVATE/'release-journal.json',0o400))
    phase=json.loads((s.CONTROL/'release-status.json').read_bytes())
    need(prior_plan.get('candidate_sha')==OLD_CANDIDATE and
         prior_plan.get('scope_sha256')==OLD_SCOPE and
         prior_plan.get('independently_verified_entra_owner') is True and
         journal.get('recovery_started_at') and
         journal.get('outcome') not in ('accepted','rolled_back') and
         phase.get('candidate_sha')==OLD_CANDIDATE and phase.get('scope_sha256')==OLD_SCOPE and
         phase.get('phase')=='draining_admitted_work',
         'KNOWN_FAILED_ONE_USE_RELEASE_ONLY')
    old_final=json.loads(txlib.raw_file(s.PRIVATE/'desired-final.json',0o400))
    old_current=json.loads(txlib.raw_file(s.DESIRED,0o600))
    final_hash=digest(old_final)
    need(prior_plan['scope']['desired_state_after_sha256']==final_hash
         and digest(old_current) in
             (final_hash,prior_plan['scope']['desired_state_initial_sha256']),
         'EXACT_ORIGINAL_DESIRED_POLICY_UNCHANGED')
    new_final=reviewed_forward_desired(old_final)
    old_policy_sha=checked_frozen_source(s,payload)
    p=JournalProfile.load(s.PROFILE)
    with p.gate():
        catalog=p.catalog()
        need(catalog['mode']=='segmented' and catalog['generation']==2
             and len(catalog['segments'])==1,'EXACT_SEALED_SEGMENT_GENERATION')
        row=catalog['segments'][0]
        archive=worker.exact_sealed(p,row)
        need(row['id']==FIRST_SEGMENT and row['proof']['events']==FIRST_EVENTS
             and row['proof']['file_sha256']==FIRST_SHA256,
             'ORIGINAL_SEALED_HISTORY_IDENTITY')
        before=p.pending/row['proof']['source_before_image']
        meta=before.lstat()
        need(not before.is_symlink() and stat.S_ISREG(meta.st_mode) and
             meta.st_uid==p.custody_uid and meta.st_gid==p.writer_uid and
             stat.S_IMODE(meta.st_mode)==0o440 and
             fingerprint(meta)==row['proof']['source_before_fingerprint'],
             'PRESERVED_ORIGINAL_BEFORE_IMAGE')
        need(meta.st_dev==p.active.stat().st_dev and p.active.stat().st_size<2_147_483_648,
             'CANONICAL_ACTIVE_SMALL_AND_SEPARATE')
        need(not (s.PRIVATE/'transaction.json').exists() and
             not (s.PRIVATE/'rollback-mounted.json').exists(),
             'NO_UNKNOWN_NATIVE_TRANSACTION')
    units=native_units(I)
    evidence={'old_release_plan_sha256':digest(txlib.raw_file(s.PRIVATE/'release-plan.json',0o400)),
              'old_release_journal_sha256':digest(txlib.raw_file(s.PRIVATE/'release-journal.json',0o400)),
              'old_policy_sha256':old_policy_sha,
              'old_desired_sha256':digest(old_current),
              'new_desired_sha256':digest(new_final),
              'catalog_sha256':digest(canonical(catalog)),
              'original_archive':{'segment_id':row['id'],'archive_sha256':row['proof']['file_sha256'],
                                  'events':row['proof']['events']},
              'source_before_fingerprint':row['proof']['source_before_fingerprint'],
              'active_identity':{'device':p.active.stat().st_dev,'inode':p.active.stat().st_ino},
              'initial_generation':catalog['generation'],
              'initial_epoch':catalog['epoch'],
              'initial_reservations':live_reservations(p.active),
              'old_service':units,
              'initial_archive_device':archive.stat().st_dev,
              'source_sha256':digest(payload['tools/audit_journal_no_restore_worker.py']),
              'unit_sha256':{str(path):digest(raw) for path,raw in proposed_units(s).items()}}
    # Exact immutable allowed effects, not a broad promotion exception.
    scope={'schema_version':'1.0','action':ACTION,'candidate_sha':candidate,
           'policy':{'candidate_sha':candidate,'rollback_sha':s.ROLLBACK},
           'queue_cutover':True,
           'installation_targets':[str(SOURCE),str(GRANT),str(RECORD),
                                   *(str(path) for path in proposed_units(s))],
           'prior_failed_candidate_sha':OLD_CANDIDATE,
           'prior_approved_scope_sha256':OLD_SCOPE,
           'no_legacy_rebuild':True,'no_provider_invocations':True,
           'preserve_unknown_reservations':True,'production_freeze_unchanged':True,
           'service_reboots':False,'container_replacements':0,'provider_writes':0,
           'restored_legacy_database':False,
           'archive_history_delete_allowed':False,
           'redundant_local_before_image_reclaim_allowed':True,
           'one_use_owner_authentication_required':True,
           'same_exact_grant_bounded_idempotent_recovery_retries':2,
           'source_sha256':evidence['source_sha256'],
           'installed_targets':[str(SOURCE),str(GRANT),str(RECORD),
                                *(str(path) for path in proposed_units(s))],
           'systemd_effects':['disable_failed_original_audit_release_boot',
                              'reset_only_failed_original_systemd_unit_flag_not_breaker',
                              'activate_one_reviewed_forward_recovery_service',
                              'enable_scheduled_no_rebuild_maintenance_after_recovery'],
           'desired_policy_change':'add_only_jason-audit-journal-no-restore-release.service_to_allowed_system_units',
           'immutable_evidence':evidence}
    return scope


def execute(I,s,modules,c,auth,candidate,payload):
    from tools.audit_journal_install_transaction import InstallTransaction
    units=proposed_units(s)
    with auth['locks']():
        scope=preflight(I,s,candidate,payload)
        print('AUDIT_NO_RESTORE_COMPLETE_ROOT_PREFLIGHT=PASS',flush=True)
        print('NO_LEGACY_REBUILD=true',flush=True)
        print('EXACT_SCOPE_SHA256='+digest(scope),flush=True)
        print('VERIFIED_ARCHIVE_EVENTS='+str(scope['immutable_evidence']['original_archive']['events']),flush=True)
        print('PRESERVED_UNKNOWN_READ_ONLY_RESERVATIONS=3',flush=True)
        # Only the existing independently licensed Entra Owner verifier can
        # create a new exact objective grant; the prior claim is never reused.
        owner=auth['owner'](scope)
        need(owner==OWNER,'INDEPENDENT_LICENSED_OWNER_DENIED')
        need(preflight(I,s,candidate,payload)==scope,'STATE_CHANGED_DURING_OWNER_APPROVAL')
        RECORD.mkdir(mode=0o700)
        os.chown(RECORD,0,0);RECORD.chmod(0o700)
        tx=InstallTransaction(RECORD/'transaction.json',digest(scope))
        grant={'schema_version':'1.0','action':ACTION,'stage':'recovery_authorized',
               'no_legacy_rebuild':True,'owner_oid':owner,
               'independently_verified_entra_owner':True,
               'approved_at':datetime.now(timezone.utc).isoformat(),
               'candidate_sha':candidate,'source_sha256':scope['source_sha256'],
               'scope':scope,'scope_sha256':digest(scope),
               'initial_generation':scope['immutable_evidence']['initial_generation'],
               'initial_epoch':scope['immutable_evidence']['initial_epoch'],
               'initial_reservations':scope['immutable_evidence']['initial_reservations'],
               'original_archive':scope['immutable_evidence']['original_archive']}
        try:
            tx.write(RECORD/'approval.json',canonical(grant),0o400)
            tx.directory(SOURCE.parent)
            tx.write(SOURCE,payload['tools/audit_journal_no_restore_worker.py'],0o444)
            tx.write(GRANT,canonical(grant),0o400)
            for target,raw in units.items():
                tx.directory(target.parent)
                tx.write(target,raw,0o644)
            I.command(['/usr/bin/systemctl','daemon-reload'])
            # Durable one-use action receipt BEFORE changes to boot activation.
            tx.queued=True
            I.command(['/usr/bin/systemctl','disable','jason-audit-journal-release.service'])
            after=status(I,'jason-audit-journal-release.service')
            need(after['UnitFileState']=='disabled' and after['MainPID']=='0',
                 'FAILED_LEGACY_RELEASE_STILL_BOOT_ENABLED')
            # Clear systemd's failed flag ONLY for this known failed and now
            # disabled release. This is not a circuit-breaker reset or approval.
            I.command(['/usr/bin/systemctl','reset-failed','jason-audit-journal-release.service'])
            I.command(['/usr/bin/systemctl','--no-block','start',RELEASE_UNIT.name])
            print('AUDIT_NO_RESTORE_ROOT_RELEASE=QUEUED',flush=True)
            print('NEW_RELEASE_UNIT='+RELEASE_UNIT.name,flush=True)
            print('ROOT_BOOT_LEGACY_RESTART_DISABLED=true',flush=True)
            print('RECLAMATION_AND_HEALTH_ACCEPTANCE_PENDING=true',flush=True)
        except Exception:
            if not tx.queued:tx.rollback()
            raise
