#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_REGISTRY = Path('/var/lib/jason/openclaw/trusted-keys/registry.json')
DEFAULT_CONTAINER = 'openclaw-openclaw-gateway-1'
DEFAULT_MACHINE_ID = 'svc-openclaw-gateway'


def run(cmd: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, input=input_text, text=True, capture_output=True, check=False)


def registry_records(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding='utf-8'))
    records = data.get('keys', [])
    if not isinstance(records, list):
        raise ValueError('trusted key registry keys field is invalid')
    return records


def active_key_ids(path: Path) -> list[str]:
    return sorted(
        str(item['key_id'])
        for item in registry_records(path)
        if item.get('status', 'active') == 'active'
    )


def sign_inside_container(container: str, key_path: str, payload: dict) -> dict:
    script = r'''
const fs = require('fs');
const crypto = require('crypto');
const keyPath = process.argv[1];
const envelope = JSON.parse(fs.readFileSync(0, 'utf8'));
const body = {};
for (const name of Object.keys(envelope).sort()) {
  if (name !== 'signature') body[name] = envelope[name];
}
const canonical = JSON.stringify(body);
const signature = crypto.sign(null, Buffer.from(canonical, 'utf8'), fs.readFileSync(keyPath));
envelope.signature = signature.toString('base64');
process.stdout.write(JSON.stringify(envelope));
'''
    result = run(['docker', 'exec', '-i', container, 'node', '-e', script, key_path], input_text=json.dumps(payload))
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or 'container signing failed')
    return json.loads(result.stdout)


def verify_with_registry(repo: Path, registry: Path, envelope: dict) -> tuple[bool, str]:
    code = r'''
import json, sys
from jason_openclaw.key_registry import FileBackedTrustedKeyRegistry
registry, payload = sys.argv[1], sys.stdin.read()
envelope = json.loads(payload)
auth = FileBackedTrustedKeyRegistry(registry).build_authenticator()
try:
    identity = auth.authenticate(envelope)
except Exception as exc:
    print(type(exc).__name__ + ':' + str(exc))
    raise SystemExit(2)
print(identity)
'''
    env = os.environ.copy()
    env['PYTHONPATH'] = f"{repo / 'implementation/connectors/openclaw/src'}:{repo / 'implementation'}"
    result = subprocess.run(
        [sys.executable, '-c', code, str(registry)],
        input=json.dumps(envelope),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    return result.returncode == 0, result.stdout.strip() or result.stderr.strip()


def test_envelope(key_id: str) -> dict:
    return {
        'request_id': f'rotation-proof-{key_id}',
        'correlation_id': f'rotation-proof-{key_id}',
        'key_id': key_id,
        'capability': 'jason.synthetic.health',
        'requested_mode': 'observe',
        'arguments': {'synthetic': True, 'rotation_proof': True},
        'principal': {
            'principal_id': DEFAULT_MACHINE_ID,
            'channel': 'openclaw',
            'external_user_id': DEFAULT_MACHINE_ID,
            'organization_id': 'aot',
            'client_id': None,
            'authentication_assurance': 'machine_authenticated',
        },
    }


def main() -> int:
    p = argparse.ArgumentParser(description='Verify overlap-first OpenClaw Ed25519 key rotation invariants')
    p.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument('--registry', type=Path, default=DEFAULT_REGISTRY)
    p.add_argument('--container', default=DEFAULT_CONTAINER)
    p.add_argument('--old-key-id', required=True)
    p.add_argument('--old-key-path', required=True)
    p.add_argument('--new-key-id', required=True)
    p.add_argument('--new-key-path', required=True)
    p.add_argument('--expect-old-revoked', action='store_true')
    args = p.parse_args()

    active = active_key_ids(args.registry)
    expected_new = args.new_key_id in active
    expected_old = args.old_key_id in active

    results = {
        'registry_active_keys': active,
        'new_key_registered_active': expected_new,
        'old_key_registered_active': expected_old,
        'expect_old_revoked': args.expect_old_revoked,
        'provider_contacted': False,
        'provider_credentials_used': False,
    }

    new_signed = sign_inside_container(args.container, args.new_key_path, test_envelope(args.new_key_id))
    new_ok, new_detail = verify_with_registry(args.repo, args.registry, new_signed)
    results['new_key_verification'] = {'accepted': new_ok, 'detail': new_detail}

    old_signed = sign_inside_container(args.container, args.old_key_path, test_envelope(args.old_key_id))
    old_ok, old_detail = verify_with_registry(args.repo, args.registry, old_signed)
    results['old_key_verification'] = {'accepted': old_ok, 'detail': old_detail}

    if args.expect_old_revoked:
        passed = expected_new and (not expected_old) and new_ok and (not old_ok)
    else:
        passed = expected_new and expected_old and new_ok and old_ok

    results['status'] = 'pass' if passed else 'fail'
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0 if passed else 2


if __name__ == '__main__':
    raise SystemExit(main())
