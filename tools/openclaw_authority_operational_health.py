#!/usr/bin/env python3
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic

DEFAULT_AUTHORITY = Path('/var/lib/jason/authority/authority.sqlite3')
DEFAULT_REPLAY = Path('/var/lib/jason/openclaw/replay.sqlite3')
DEFAULT_SECURITY = Path('/var/lib/jason/openclaw/security-audit.sqlite3')
# Must follow the same exact ledger path as BOTH runtime writer containers
# after a governed release. Without an explicit rollout it remains legacy.
DEFAULT_ORCH = Path(os.environ.get(
    'JASON_ORCHESTRATION_EVENTS_DB',
    '/var/lib/jason/openclaw/orchestration-events.sqlite3',
))
DEFAULT_REGISTRY = Path('/var/lib/jason/openclaw/trusted-keys/registry.json')


def mode(path: Path) -> str | None:
    if not path.exists():
        return None
    return oct(path.stat().st_mode & 0o777)


def sqlite_integrity(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        return str(connection.execute('PRAGMA integrity_check').fetchone()[0])


def authority_counts(path: Path) -> dict[str, int]:
    with sqlite3.connect(path) as connection:
        tables = {
            'identities': 'identities',
            'grants': 'authority_grants',
            'approvals': 'approvals',
            'contexts': 'execution_contexts',
            'delegations': 'delegations',
        }
        result = {}
        for key, table in tables.items():
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            result[key] = 0 if exists is None else int(
                connection.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            )
        return result


def active_delegation_state(path: Path) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    active = expired = inactive = 0
    with sqlite3.connect(path) as connection:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='delegations'"
        ).fetchone()
        if exists is None:
            return {'active': 0, 'expired_active_records': 0, 'inactive': 0}
        for (payload,) in connection.execute('SELECT payload FROM delegations'):
            data = json.loads(payload)
            if data.get('status') != 'active':
                inactive += 1
                continue
            until = datetime.fromisoformat(data['effective_until'])
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            if until <= now:
                expired += 1
            else:
                active += 1
    return {'active': active, 'expired_active_records': expired, 'inactive': inactive}


def registry_health(path: Path) -> dict[str, object]:
    if not path.exists():
        return {'present': False, 'active_records': 0}
    data = json.loads(path.read_text(encoding='utf-8'))
    records = data.get('keys', data if isinstance(data, list) else [])
    if isinstance(records, dict):
        records = list(records.values())
    if not isinstance(records, list):
        raise ValueError('trusted-key registry records are invalid')
    active = sum(1 for item in records if str(item.get('status', 'active')) == 'active')
    return {'present': True, 'active_records': active, 'mode': mode(path)}


def backup_restore_proof(source: Path, temp_root: Path | None = None) -> dict[str, object]:
    directory = str(temp_root) if temp_root is not None else None
    with tempfile.TemporaryDirectory(prefix='jason-authority-backup-', dir=directory) as td:
        backup = Path(td) / 'authority.backup.sqlite3'
        restored = Path(td) / 'authority.restored.sqlite3'
        with sqlite3.connect(source) as src, sqlite3.connect(backup) as dst:
            src.backup(dst)
        os.chmod(backup, 0o600)
        shutil.copy2(backup, restored)
        os.chmod(restored, 0o600)
        live_counts = authority_counts(source)
        backup_counts = authority_counts(backup)
        restored_counts = authority_counts(restored)
        return {
            'backup_integrity': sqlite_integrity(backup),
            'restore_integrity': sqlite_integrity(restored),
            'backup_mode': mode(backup),
            'restore_mode': mode(restored),
            'counts_match': backup_counts == restored_counts,
            'live_source_counts': live_counts,
            'backup_counts': backup_counts,
            'restored_counts': restored_counts,
            'live_source_matches_snapshot_at_observation': live_counts == backup_counts,
        }


def _stage_complete(label: str, start: float) -> float:
    """Secret-free stage timing retained even if the outer 60-minute job times out."""
    elapsed = round(monotonic() - start, 3)
    # The wrapper captures stderr and only admits known, complete stage
    # markers to failed-timeout evidence; these lines are never PASS proof.
    print(f'JASON_FULL_INTEGRITY_STAGE_V1|{label}|{elapsed}', file=sys.stderr, flush=True)
    return elapsed


def run(args: argparse.Namespace) -> int:
    files = {
        'authority': args.authority_database,
        'replay': args.replay_database,
        'security_audit': args.security_audit,
        'orchestration_audit': args.orchestration_audit,
    }
    file_state = {}
    failures = []
    stage_seconds: dict[str, float] = {}

    # The 36+ GB orchestration audit dominates elapsed time. Start its
    # unchanged FULL PRAGMA integrity_check before the authority checks and
    # complete authority backup/restore independently while it runs.
    # Exactly one additional thread: no daemon, extra signing capability,
    # provider access, permanent worker, checkpoint or weakened quick_check.
    # Two independent SQLite connections preserve normal WAL reader safety.
    # The existing outer 3600-second subprocess boundary remains strict.
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix='jason-audit-integrity') as pool:
        orchestration = files['orchestration_audit']
        orchestration_present = orchestration.exists()
        orchestration_started = monotonic()
        audit_check = pool.submit(sqlite_integrity, orchestration) if orchestration_present else None

        for name in ('authority', 'replay', 'security_audit'):
            path = files[name]
            present = path.exists()
            current_mode = mode(path)
            started = monotonic()
            integrity = sqlite_integrity(path) if present else None
            if present:
                stage_seconds[name] = _stage_complete(name, started)
            file_state[name] = {
                'path': str(path), 'present': present,
                'mode': current_mode, 'integrity': integrity,
            }
            if not present:
                failures.append(f'{name}_missing')
            elif current_mode != '0o600':
                failures.append(f'{name}_permissions')
            elif integrity != 'ok':
                failures.append(f'{name}_integrity')

        delegation = active_delegation_state(args.authority_database) if args.authority_database.exists() else {}
        started = monotonic()
        backup = backup_restore_proof(args.authority_database, args.backup_temp_root) if args.authority_database.exists() else {}
        if args.authority_database.exists():
            stage_seconds['authority_backup_restore'] = _stage_complete('authority_backup_restore', started)

        registry = registry_health(args.key_registry)
        if not registry.get('present'):
            failures.append('key_registry_missing')
        elif registry.get('mode') != '0o600':
            failures.append('key_registry_permissions')
        elif int(registry.get('active_records', 0) or 0) < 1:
            failures.append('key_registry_no_active_keys')

        integrity = audit_check.result() if audit_check is not None else None
        if audit_check is not None:
            stage_seconds['orchestration_audit'] = _stage_complete('orchestration_audit', orchestration_started)
        current_mode = mode(orchestration)
        file_state['orchestration_audit'] = {
            'path': str(orchestration), 'present': orchestration_present,
            'mode': current_mode, 'integrity': integrity,
        }
        if not orchestration_present:
            failures.append('orchestration_audit_missing')
        elif current_mode != '0o600':
            failures.append('orchestration_audit_permissions')
        elif integrity != 'ok':
            failures.append('orchestration_audit_integrity')

    if backup and not (
        backup.get('backup_integrity') == 'ok'
        and backup.get('restore_integrity') == 'ok'
        and backup.get('backup_mode') == '0o600'
        and backup.get('restore_mode') == '0o600'
        and backup.get('counts_match') is True
    ):
        failures.append('authority_backup_restore')

    report = {
        'status': 'pass' if not failures else 'fail',
        'files': file_state,
        'authority_counts': authority_counts(args.authority_database) if args.authority_database.exists() else {},
        'delegations': delegation,
        'trusted_key_registry': registry,
        'backup_restore_proof': backup,
        'failures': failures,
        'completed_stage_seconds': stage_seconds,
        'provider_contacted': False,
        'provider_credentials_used': False,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 2


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Check deployed OpenClaw/JKD-001 state and prove SQLite backup/restore integrity')
    p.add_argument('--authority-database', type=Path, default=DEFAULT_AUTHORITY)
    p.add_argument('--replay-database', type=Path, default=DEFAULT_REPLAY)
    p.add_argument('--security-audit', type=Path, default=DEFAULT_SECURITY)
    p.add_argument('--orchestration-audit', type=Path, default=DEFAULT_ORCH)
    p.add_argument('--key-registry', type=Path, default=DEFAULT_REGISTRY)
    p.add_argument('--backup-temp-root', type=Path, default=None)
    return p


if __name__ == '__main__':
    raise SystemExit(run(parser().parse_args()))
