#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, load_pem_public_key

DEFAULT_REGISTRY = Path('/var/lib/jason/openclaw/trusted-keys/registry.json')


def fingerprint(path: Path) -> str:
    key = load_pem_public_key(path.read_bytes())
    der = key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(der).hexdigest()


def load_registry(path: Path) -> dict:
    payload = {'version': 1, 'keys': []}
    if path.exists():
        payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload.get('keys'), list):
        raise ValueError('existing registry keys field is invalid')
    return payload


def write_registry(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = {'version': 1, 'keys': sorted(payload['keys'], key=lambda item: item['key_id'])}
    path.write_text(json.dumps(normalized, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    path.chmod(0o600)


def register(args) -> int:
    actual = fingerprint(args.public_key)
    if actual != args.expected_fingerprint:
        print(json.dumps({'status':'fail','reason':'fingerprint_mismatch','actual_fingerprint':actual}, sort_keys=True))
        return 2
    payload = load_registry(args.registry)
    record = {
        'key_id': args.key_id,
        'machine_identity': args.machine_identity,
        'public_key_path': str(args.public_key),
        'sha256_fingerprint': actual,
        'status': 'active',
    }
    keys = [item for item in payload['keys'] if item.get('key_id') != args.key_id]
    keys.append(record)
    payload['keys'] = keys
    write_registry(args.registry, payload)
    print(json.dumps({
        'status': 'pass',
        'action': 'openclaw_public_key_registered',
        'key_id': args.key_id,
        'machine_identity': args.machine_identity,
        'fingerprint': actual,
        'registry': str(args.registry),
    }, sort_keys=True))
    return 0


def revoke(args) -> int:
    payload = load_registry(args.registry)
    changed = False
    for item in payload['keys']:
        if item.get('key_id') == args.key_id:
            if item.get('status', 'active') != 'revoked':
                item['status'] = 'revoked'
                changed = True
            break
    else:
        print(json.dumps({'status':'fail','action':'openclaw_public_key_revoke','reason':'key_not_found','key_id':args.key_id}, sort_keys=True))
        return 2
    write_registry(args.registry, payload)
    print(json.dumps({
        'status': 'pass',
        'action': 'openclaw_public_key_revoked',
        'key_id': args.key_id,
        'changed': changed,
        'reason': args.reason,
    }, sort_keys=True))
    return 0


def list_keys(args) -> int:
    payload = load_registry(args.registry)
    safe = [
        {
            'key_id': item.get('key_id'),
            'machine_identity': item.get('machine_identity'),
            'sha256_fingerprint': item.get('sha256_fingerprint'),
            'status': item.get('status', 'active'),
        }
        for item in payload['keys']
    ]
    print(json.dumps({'status':'pass','registry':str(args.registry),'keys':safe}, indent=2, sort_keys=True))
    return 0


def lifecycle_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Govern OpenClaw trusted public signing keys for Jason')
    p.add_argument('--registry', type=Path, default=DEFAULT_REGISTRY)
    sub = p.add_subparsers(dest='command', required=True)

    add = sub.add_parser('register')
    add.add_argument('--key-id', required=True)
    add.add_argument('--machine-identity', required=True)
    add.add_argument('--public-key', type=Path, required=True)
    add.add_argument('--expected-fingerprint', required=True)
    add.set_defaults(func=register)

    revoke_p = sub.add_parser('revoke')
    revoke_p.add_argument('--key-id', required=True)
    revoke_p.add_argument('--reason', required=True)
    revoke_p.set_defaults(func=revoke)

    listing = sub.add_parser('list')
    listing.set_defaults(func=list_keys)
    return p


def legacy_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Register an OpenClaw public signing key for Jason')
    p.add_argument('--registry', type=Path, default=DEFAULT_REGISTRY)
    p.add_argument('--key-id', required=True)
    p.add_argument('--machine-identity', required=True)
    p.add_argument('--public-key', type=Path, required=True)
    p.add_argument('--expected-fingerprint', required=True)
    return p


def main() -> int:
    lifecycle_commands = {'register', 'revoke', 'list'}
    command = next((item for item in sys.argv[1:] if not item.startswith('-')), None)
    if command in lifecycle_commands:
        args = lifecycle_parser().parse_args()
        return args.func(args)
    return register(legacy_parser().parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
