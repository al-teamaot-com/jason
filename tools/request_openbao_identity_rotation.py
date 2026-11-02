#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import time
from pathlib import Path
from uuid import uuid4

APPROVED_PROVIDERS = ('autotask_read', 'dnsfilter')

ROOT = Path('/var/lib/jason/openclaw/identity-lifecycle')
CURRENT = Path('/opt/jason/current')
SHA = re.compile(r'[0-9a-f]{40}\Z')


def _current_revision() -> str:
    revision = CURRENT.resolve(strict=True).name.casefold()
    if not SHA.fullmatch(revision):
        raise RuntimeError('production source link is not exact SHA')
    return revision


def request_lifecycle_action(*, action: str, provider: str, reason: str, timeout_seconds: float = 120.0) -> dict:
    if action == 'rotate':
        if provider not in APPROVED_PROVIDERS:
            raise ValueError('provider is not approved for identity lifecycle')
    elif action == 'bootstrap_from_init':
        if provider != 'identity_lifecycle':
            raise ValueError('bootstrap provider sentinel invalid')
    else:
        raise ValueError('unsupported identity lifecycle action')
    reason = reason.strip()
    if not 3 <= len(reason) <= 300:
        raise ValueError('bounded reason required')
    request_id = uuid4().hex
    requests = ROOT / 'requests'
    results = ROOT / 'results'
    if not requests.is_dir() or not results.is_dir():
        raise RuntimeError('governed identity lifecycle worker is not installed')
    request_path = requests / (request_id + '.json')
    result_path = results / (request_id + '.json')
    revision = _current_revision()
    payload = {
        'request_id': request_id,
        'action': action,
        'provider': provider,
        'reason': reason,
        'source_revision': revision,
        'release_id': ('release-' + revision[:16]) if action == 'bootstrap_from_init' else '',
    }
    fd, name = tempfile.mkstemp(prefix='.identity-request-', dir=requests)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name, 0o600)
        os.replace(name, request_path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    try:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if result_path.is_file():
                result = json.loads(result_path.read_text(encoding='utf-8'))
                if result.get('request_id') != request_id:
                    raise RuntimeError('identity lifecycle response id mismatch')
                if result.get('success') is not True:
                    raise RuntimeError('identity lifecycle rotation rejected: ' + str(result.get('detail') or 'unknown')[:300])
                return result
            time.sleep(0.25)
        raise TimeoutError('identity lifecycle result timed out')
    finally:
        result_path.unlink(missing_ok=True)


def request_rotation(provider: str, reason: str, timeout_seconds: float = 120.0) -> dict:
    return request_lifecycle_action(
        action='rotate', provider=provider, reason=reason, timeout_seconds=timeout_seconds
    )


def main() -> int:
    parser = argparse.ArgumentParser(description='Request a bounded root-governed OpenBao identity rotation')
    parser.add_argument('provider', choices=APPROVED_PROVIDERS)
    parser.add_argument('--reason', required=True)
    args = parser.parse_args()
    result = request_rotation(args.provider, args.reason)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
