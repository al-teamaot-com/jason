"""Exact native-health repair through the existing audit installer and Owner verifier.

Source only until protected-main CI, root preflight and a fresh exact Owner
decision pass. Frozen journal code, its policy and adoption receipt never change.
"""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import os
import stat
import sys
import time

from tools.audit_journal_install_transaction import InstallTransaction, raw_file, atomic

ACTION = "REPAIR-EXACT-AUDIT-HEALTH-NATIVE-PRIVATE-READER"
RECORD = Path('/var/lib/jason-owner-release/audit-health-native-private-reader-v1')
NATIVE = Path('/usr/local/lib/jason/audit-journal/native-health')
FILES = {
    'tools/audit_journal_health_private_reader.py': 'audit_journal_health_private_reader.py',
    'tools/audit_journal_fast_health.py': 'openclaw_authority_fast_health.py',
    'tools/audit_journal_operational_health.py': 'openclaw_authority_operational_health.py',
    'tools/audit_journal_full_health_snapshot.py': 'openclaw_authority_live_audit_full_snapshot.py',
}
BEFORE = {
    'openclaw_authority_fast_health.py': 'aa0f2b7b3f2db09d59dc7d663a041bebef4f0021bf0d1b0ff4464bf619888a15',
    'openclaw_authority_operational_health.py': '68c126f708bce6a7d15497e57c711f047996357be003cb912ec70a992e0f0058',
    'openclaw_authority_live_audit_full_snapshot.py': '53bfdcb5a693c5e1ca912d5eedacbc3ca34c205e9550da7adb004e1847811b50',
}
SERVICES = ('jason-openclaw-authority-health.service',
            'jason-openclaw-authority-full-integrity.service')
TIMERS = tuple(x.replace('.service', '.timer') for x in SERVICES)


def need(ok, code):
    if not ok:
        raise PermissionError('AUDIT_HEALTH_READER_' + code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(raw):
    return sha256(raw).hexdigest()


def props(I, unit):
    text = I.command(['/usr/bin/systemctl', 'show', unit, '-p', 'ActiveState',
                      '-p', 'MainPID', '-p', 'Result', '-p', 'ExecMainStatus'])
    return dict(line.split('=', 1) for line in text.splitlines() if '=' in line)


def unit_configuration(I):
    units = (*SERVICES, *TIMERS, 'jason-audit-journal-maintenance.service',
             'jason-production-drift-watchdog.service')
    return {unit: digest(I.command(['/usr/bin/systemctl', 'cat', unit]).encode())
            for unit in units}


def preserved_audit(s):
    """Recheck every actual Root policy pin, without altering old Owner evidence."""
    policy_raw = raw_file(s.POLICY, 0o600)
    receipt_raw = raw_file(s.PRIVATE / 'adoption.json', 0o400)
    policy, receipt = json.loads(policy_raw), json.loads(receipt_raw)
    need(receipt.get('action') == s.ACTION and receipt.get('owner_oid') == s.OWNER
         and receipt.get('independently_verified_entra_owner') is True
         and receipt.get('policy_sha256') == digest(canonical(policy))
         and receipt.get('maintenance_policy_adopted') is True, 'ORIGINAL_ADOPTION')
    pins = policy.get('trusted_source_sha256')
    need(policy.get('enabled') is True and isinstance(pins, dict)
         and set(pins) == set(s.SOURCES), 'ORIGINAL_SOURCE_CLOSURE')
    for name, expected in pins.items():
        need(digest(raw_file(s.BASE / 'trusted' / name, 0o444)) == expected,
             'ORIGINAL_FROZEN_SOURCE_CHANGED')
    # The active profile, historical grants and desired-state policy are never targets.
    return {'policy_sha256': digest(policy_raw), 'adoption_sha256': digest(receipt_raw),
            'trusted_source_sha256': pins}


def strict_repair_drift(drift, control, *, now=None):
    now = now or datetime.now(timezone.utc)
    expected = {'kind': 'failed_system_unit', 'state': 'failed', 'unit': SERVICES[0]}
    need(drift.get('status') == 'drift_detected'
         and drift.get('problems') == [expected], 'UNRELATED_OR_UNKNOWN_DRIFT')
    stamp = datetime.fromisoformat(drift['observed_at'].replace('Z', '+00:00'))
    need(stamp.tzinfo is not None and 0 <= (now - stamp).total_seconds() <= 180,
         'STALE_NATIVE_DRIFT')
    breaker = control.get('circuit_breaker', {})
    need(breaker.get('state') == 'open'
         and breaker.get('reason') == 'continuous_production_drift_detected',
         'UNEXPECTED_BREAKER_STATE')


def preflight(I, s, candidate, payload):
    need(os.geteuid() == 0 and sys.flags.isolated == 1, 'ISOLATED_ROOT_REQUIRED')
    for directory in (NATIVE, NATIVE.parent, RECORD.parent):
        meta = directory.lstat()
        need(not directory.is_symlink() and stat.S_ISDIR(meta.st_mode)
             and meta.st_uid == meta.st_gid == 0 and not meta.st_mode & 0o022,
             'ROOT_DIRECTORY_CUSTODY')
    need(not os.path.lexists(RECORD), 'ONE_USE_REPAIR_ALREADY_CLAIMED')
    need(Path('/opt/jason/current').resolve().name == s.ROLLBACK, 'LIVE_RELEASE_CHANGED')
    original = preserved_audit(s)
    for path, expected in s.PROTECTED.items():
        need(digest(I.read(Path(path))) == expected, 'NATIVE_PROTECTION_CHANGED')
    for name in BEFORE:
        need(digest(raw_file(NATIVE / name, 0o444)) == BEFORE[name], 'NATIVE_BEFORE_IMAGE')
    need(not os.path.lexists(NATIVE / FILES['tools/audit_journal_health_private_reader.py']),
         'NEW_MODULE_ALREADY_EXISTS')
    for name in FILES:
        need(isinstance(payload.get(name), bytes) and 0 < len(payload[name]) < 100_000,
             'REVIEWED_PAYLOAD_MISSING')
    full, fast = [props(I, x) for x in (SERVICES[1], SERVICES[0])]
    need(full['ActiveState'] in ('inactive', 'failed') and full['MainPID'] == '0'
         and fast['ActiveState'] == 'failed' and fast['MainPID'] == '0', 'HEALTH_CHECK_BUSY')
    need(all(props(I, x)['ActiveState'] == 'active' for x in TIMERS), 'HEALTH_TIMER_CHANGED')
    for name in ('jason-audit-journal-release.service', 'jason-audit-journal-no-restore-release.service'):
        need(props(I, name)['MainPID'] == '0', 'AUDIT_RELEASE_STILL_RUNNING')
    accepted = json.loads(raw_file(s.CONTROL / 'forward-release-status.json', 0o444))
    maintenance = json.loads(raw_file(s.CONTROL / 'maintenance-status.json', 0o444))
    need(accepted.get('phase') == 'accepted' and accepted.get('status') == 'accepted'
         and maintenance.get('status') == 'scheduled_no_restore_verified'
         and maintenance.get('first_scheduled_rollover_verified') is True,
         'PRIOR_AUDIT_NOT_ACCEPTED')
    drift = json.loads(raw_file(s.STATE / 'production-drift.json', 0o600))
    control = json.loads(raw_file(s.STATE / 'production-control-state.json', 0o600))
    strict_repair_drift(drift, control)
    peers = s.protected_peer_inventory()
    scope = {
        'schema_version': '1.0', 'action': ACTION,
        'policy': {'candidate_sha': candidate, 'rollback_sha': s.ROLLBACK},
        'queue_cutover': False, 'exact_native_targets': [str(NATIVE / x) for x in FILES.values()],
        'source_sha256': {x: digest(payload[x]) for x in FILES},
        'before_sha256': dict(BEFORE), 'preserved_audit': original,
        'preserved_protected_sha256': dict(s.PROTECTED), 'protected_peers': peers,
        'prior_audit_scope_sha256': accepted['scope_sha256'],
        'unit_configuration_sha256': unit_configuration(I),
        'allowed_known_incident': 'only_failed_frequent_authority_health',
        'health_services_only': list(SERVICES), 'health_timers_only': list(TIMERS),
        'verification_services': [*SERVICES, 'jason-audit-journal-maintenance.service',
                                  'jason-production-drift-watchdog.service'],
        'maximum_full_scan_seconds': 5500, 'acceptance_attempts': 1,
        'core_container_stops': 0, 'provider_calls': 0,
        'direct_audit_database_mutations': False,
        'audit_maintenance': 'existing_adopted_policy_only',
        'historical_deletion': False, 'freeze_unchanged': True, 'breaker_reset': False,
        'rollback': 'restore_exact_three_native_before_images_remove_only_new_private_reader',
        'journal_policy_and_adoption_unchanged': True,
    }
    return scope


def verify_fresh_proofs(s, after):
    for name in ('operational-full-health.json', 'operational-health.json'):
        path = Path('/var/lib/jason/openclaw') / name
        meta = path.lstat()
        need(stat.S_ISREG(meta.st_mode) and meta.st_uid == 1000 and meta.st_nlink == 1
             and stat.S_IMODE(meta.st_mode) == 0o600 and meta.st_mtime >= after,
             'FRESH_HEALTH_CUSTODY')
        proof = json.loads(path.read_bytes())
        need(proof.get('status') == 'pass' and proof.get('failures') == []
             and proof.get('snapshot_source_exit_code') == 0
             and proof.get('provider_contacted') is False
             and proof.get('provider_credentials_used') is False, 'ACTUAL_HEALTH_FAILED')
        if name == 'operational-full-health.json':
            cover = proof.get('orchestration_journal', {})
            need(cover.get('integrity') == 'ok' and cover.get('mode') == 'segmented'
                 and cover.get('active_snapshot') == cover.get('active_restore')
                 and cover.get('active_snapshot', {}).get('integrity') == 'ok', 'FULL_JOURNAL_PROOF')
    return True


def execute(I, s, auth, candidate, payload, *, check_only=False):
    with auth['locks']():
        scope = preflight(I, s, candidate, payload)
    print('AUDIT_HEALTH_NATIVE_READER_ROOT_PREFLIGHT=PASS', flush=True)
    print('EXACT_SCOPE_SHA256=' + digest(canonical(scope)), flush=True)
    print(json.dumps(scope, sort_keys=True), flush=True)
    if check_only:
        return
    actor = auth['owner'](scope)
    need(actor == s.OWNER, 'INDEPENDENT_LICENSED_OWNER_REQUIRED')
    tx = None
    timer_pause_started = False
    try:
        with auth['locks']():
            need(preflight(I, s, candidate, payload) == scope, 'STATE_CHANGED_DURING_APPROVAL')
            RECORD.mkdir(mode=0o700)
            os.chown(RECORD, 0, 0)
            RECORD.chmod(0o700)
            tx = InstallTransaction(RECORD / 'transaction.json', digest(canonical(scope)))
            atomic(RECORD / 'approval.json', canonical({
                'scope': scope, 'scope_sha256': digest(canonical(scope)), 'owner_oid': actor,
                'independently_verified_entra_owner': True,
                'approved_at': datetime.now(timezone.utc).isoformat(),
            }), 0o400)
            # Approval is outside rollback entries and survives every failure.
            timer_pause_started = True
            I.command(['/usr/bin/systemctl', 'stop', *TIMERS])
            need(all(props(I, x)['MainPID'] == '0' for x in SERVICES), 'HEALTH_RACED_TIMER_STOP')
            for source, filename in FILES.items():
                if filename in BEFORE:
                    tx.replace(NATIVE / filename, payload[source], 0o444)
                else:
                    tx.write(NATIVE / filename, payload[source], 0o444)
            need(preserved_audit(s) == scope['preserved_audit'], 'FROZEN_AUDIT_CHANGED')
            need(unit_configuration(I) == scope['unit_configuration_sha256'], 'HEALTH_UNITS_CHANGED')
            I.command(['/usr/bin/systemctl', 'start', *TIMERS])
        started = time.time()
        I.command(['/usr/bin/systemctl', 'start', SERVICES[1]], timeout=5500)
        I.command(['/usr/bin/systemctl', 'start', SERVICES[0]], timeout=90)
        verify_fresh_proofs(s, started)
        # Exercise the ordinary Root maintenance entry; its original source/policy pins remain intact.
        I.command(['/usr/bin/systemctl', 'start', 'jason-audit-journal-maintenance.service'], timeout=5500)
        need(props(I, 'jason-audit-journal-maintenance.service')['Result'] == 'success',
             'SCHEDULED_MAINTENANCE_FAILED')
        observed = []
        for index in range(3):
            if index:
                time.sleep(2)
            I.command(['/usr/bin/systemctl', 'start', 'jason-production-drift-watchdog.service'])
            drift = json.loads(raw_file(s.STATE / 'production-drift.json', 0o600))
            stamp = datetime.fromisoformat(drift['observed_at'].replace('Z', '+00:00'))
            need(drift.get('status') == 'pass' and drift.get('problems') == []
                 and drift.get('observed_at') not in observed and stamp.tzinfo is not None
                 and stamp.timestamp() >= started
                 and 0 <= (datetime.now(timezone.utc) - stamp).total_seconds() <= 180,
                 'DISTINCT_NATIVE_DRIFT_PASS_REQUIRED')
            observed.append(drift['observed_at'])
        I.command([*I.USER, '/usr/bin/python3', '-I', '-B', '-c', s.native_revalidation_code()], timeout=130)
        control = json.loads(raw_file(s.STATE / 'production-control-state.json', 0o600))
        need(control.get('circuit_breaker', {}).get('state') == 'closed', 'NATIVE_BREAKER_NOT_CLOSED')
        need(s.protected_peer_inventory() == scope['protected_peers'], 'PROTECTED_PEERS_CHANGED')
        need(preserved_audit(s) == scope['preserved_audit'], 'FROZEN_AUDIT_CHANGED')
        need(unit_configuration(I) == scope['unit_configuration_sha256'], 'HEALTH_UNITS_CHANGED')
        for source, filename in FILES.items():
            need(digest(raw_file(NATIVE / filename, 0o444)) == digest(payload[source]), 'INSTALLED_READBACK')
        tx.state['outcome'] = 'accepted'
        tx.persist()
        print('AUDIT_HEALTH_NATIVE_PRIVATE_READER=OPERATIONALLY_VERIFIED', flush=True)
    except BaseException as exc:
        if tx is not None:
            try:
                with auth['locks']():
                    I.command(['/usr/bin/systemctl', 'stop', *TIMERS, *SERVICES], timeout=120)
                    tx.rollback()
                    need(preserved_audit(s) == scope['preserved_audit'], 'ROLLBACK_AUDIT_CHANGED')
                    for name, expected in BEFORE.items():
                        need(digest(raw_file(NATIVE / name, 0o444)) == expected, 'ROLLBACK_NATIVE_FAILED')
                    I.command(['/usr/bin/systemctl', 'start', *TIMERS])
                print('AUDIT_HEALTH_READER_ROLLBACK=EXACT_ORIGINAL_FILES_VERIFIED', flush=True)
            except BaseException:
                print('AUDIT_HEALTH_READER_ROLLBACK=FAILED_CLOSED_REQUIRES_ROOT_REVIEW', flush=True)
                raise
        elif timer_pause_started:
            I.command(['/usr/bin/systemctl', 'start', *TIMERS])
        raise exc
