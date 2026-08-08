#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path('/var/lib/jason/authority/authority.sqlite3')


def parse_payload(value: str) -> dict:
    return json.loads(value)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def list_delegations(database: Path) -> int:
    now = now_utc()
    output = []
    with sqlite3.connect(database) as connection:
        rows = connection.execute('SELECT delegation_id,payload FROM delegations ORDER BY delegation_id').fetchall()
        for delegation_id, payload in rows:
            data = parse_payload(payload)
            until = datetime.fromisoformat(data['effective_until'])
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            output.append({
                'delegation_id': delegation_id,
                'delegator_id': data.get('delegator_id'),
                'delegate_id': data.get('delegate_id'),
                'organization_id': data.get('organization_id'),
                'client_id': data.get('client_id'),
                'capability': data.get('capability'),
                'maximum_mode': data.get('maximum_mode'),
                'status': data.get('status'),
                'expired': until <= now,
                'effective_until': data.get('effective_until'),
            })
    print(json.dumps({'status':'pass','delegations':output}, indent=2, sort_keys=True))
    return 0


def deactivate_expired(database: Path, recorded_by: str, correlation_id: str) -> int:
    now = now_utc()
    changed: list[str] = []
    with sqlite3.connect(database) as connection:
        rows = connection.execute('SELECT delegation_id,payload FROM delegations').fetchall()
        for delegation_id, payload in rows:
            data = parse_payload(payload)
            if data.get('status') != 'active':
                continue
            until = datetime.fromisoformat(data['effective_until'])
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            if until > now:
                continue
            data['status'] = 'expired'
            connection.execute(
                'UPDATE delegations SET payload=? WHERE delegation_id=?',
                (json.dumps(data, sort_keys=True, separators=(',', ':')), delegation_id),
            )
            connection.execute(
                '''INSERT INTO authority_audit(event_type,correlation_id,principal_id,organization_id,capability,outcome,reason_codes)
                   VALUES (?,?,?,?,?,?,?)''',
                (
                    'authority.delegation.expired',
                    correlation_id,
                    recorded_by,
                    str(data['organization_id']),
                    str(data['capability']),
                    'expired',
                    json.dumps(('delegation_effective_until_elapsed',)),
                ),
            )
            changed.append(str(delegation_id))
        connection.commit()
    print(json.dumps({
        'status': 'pass',
        'action': 'deactivate_expired_delegations',
        'changed': changed,
        'changed_count': len(changed),
    }, sort_keys=True))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description='Governed JKD-001 delegation maintenance')
    p.add_argument('--database', type=Path, default=DEFAULT_DB)
    sub = p.add_subparsers(dest='command', required=True)

    listing = sub.add_parser('list')
    listing.set_defaults(func=lambda args: list_delegations(args.database))

    cleanup = sub.add_parser('deactivate-expired')
    cleanup.add_argument('--recorded-by', required=True)
    cleanup.add_argument('--correlation-id', required=True)
    cleanup.set_defaults(func=lambda args: deactivate_expired(args.database, args.recorded_by, args.correlation_id))

    args = p.parse_args()
    try:
        return args.func(args)
    except Exception as exc:
        print(json.dumps({'status':'fail','error_type':type(exc).__name__,'message':str(exc)}, sort_keys=True))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
