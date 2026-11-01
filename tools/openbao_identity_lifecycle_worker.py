#!/usr/bin/env python3
from __future__ import annotations

import fcntl
import json
import os
import pwd
import re
import stat
import tempfile
from pathlib import Path

from openbao_identity_lifecycle import PROFILES, bootstrap_from_init, rotate

ROOT = Path('/var/lib/jason/openclaw/identity-lifecycle')
REQUESTS = ROOT / 'requests'
RESULTS = ROOT / 'results'
LOCK = ROOT / 'worker.lock'
CURRENT = Path('/opt/jason/current')
RELEASE_RECORDS = Path('/var/lib/jason/openclaw/release-manager/records')
REQUEST_ID = re.compile(r'[0-9a-f]{32}\Z')
SHA = re.compile(r'[0-9a-f]{40}\Z')


def _write_json(path: Path, value: dict, uid: int, gid: int) -> None:
    fd, name = tempfile.mkstemp(prefix='.identity-result-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.chown(name, uid, gid)
        os.chmod(name, 0o600)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _read_request(path: Path) -> dict:
    if path.suffix != '.json' or not REQUEST_ID.fullmatch(path.stem):
        raise ValueError('invalid request filename')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        al = pwd.getpwnam('al')
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != al.pw_uid
                or info.st_mode & 0o077):
            raise PermissionError('invalid requester ownership or mode')
        with os.fdopen(fd, 'r', encoding='utf-8', closefd=False) as handle:
            request = json.load(handle)
    finally:
        os.close(fd)
    expected = {'request_id', 'action', 'provider', 'reason', 'source_revision', 'release_id'}
    if not isinstance(request, dict) or set(request) != expected:
        raise ValueError('invalid request contract')
    if request.get('request_id') != path.stem:
        raise ValueError('request id mismatch')
    action = request.get('action')
    provider = request.get('provider')
    if action == 'rotate':
        if provider not in PROFILES:
            raise ValueError('provider is not approved for identity lifecycle')
    elif action == 'bootstrap_from_init':
        if provider != 'identity_lifecycle':
            raise ValueError('bootstrap provider sentinel invalid')
    else:
        raise ValueError('unsupported identity lifecycle action')
    revision = str(request.get('source_revision') or '')
    if not SHA.fullmatch(revision):
        raise ValueError('exact source revision required')
    reason = str(request.get('reason') or '')
    if not 3 <= len(reason) <= 300 or any(ord(ch) < 32 for ch in reason):
        raise ValueError('bounded reason required')
    return request


def _verify_bootstrap_authority(request: dict) -> None:
    release_id = str(request.get('release_id') or '')
    revision = str(request.get('source_revision') or '')
    base_id = 'release-' + revision[:16]
    if release_id != base_id and not re.fullmatch(re.escape(base_id) + r'-retry-[1-9][0-9]{0,2}', release_id):
        raise ValueError('bootstrap release identity mismatch')
    path = RELEASE_RECORDS / (release_id + '.json')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o002:
            raise PermissionError('bootstrap release record protection invalid')
        with os.fdopen(fd, 'r', encoding='utf-8', closefd=False) as handle:
            record = json.load(handle)
    finally:
        os.close(fd)
    candidate = str((record.get('release_candidate') or {}).get('candidate_sha') or '')
    owner = record.get('owner_approval') or {}
    changed = set(str(value) for value in (record.get('changed_files') or []))
    required = {
        'tools/openbao_identity_lifecycle.py',
        'tools/openbao_identity_lifecycle_worker.py',
        'tools/install_openbao_identity_lifecycle.py',
    }
    if (candidate != revision
            or record.get('risk_profile') != 'production_control_core'
            or record.get('state') not in {'production_eligible', 'production', 'closed'}
            or owner.get('approved') is not True
            or owner.get('candidate_sha') != revision
            or not str(owner.get('source') or '').startswith('authenticated_mobile_teams_owner:relapproval-')
            or not required.issubset(changed)):
        raise PermissionError('bootstrap lacks exact authenticated Teams release authority')


def _current_revision() -> str:
    try:
        revision = CURRENT.resolve(strict=True).name.casefold()
    except OSError as exc:
        raise ValueError('production source link unavailable') from exc
    if not SHA.fullmatch(revision):
        raise ValueError('production source link is not exact SHA')
    return revision


def process() -> None:
    if os.geteuid() != 0:
        raise PermissionError('identity lifecycle worker is root-only')
    al = pwd.getpwnam('al')
    with LOCK.open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for path in sorted(REQUESTS.glob('*.json')):
            try:
                request = _read_request(path)
                if request['source_revision'] != _current_revision():
                    raise ValueError('identity request source revision is stale')
                if request['action'] == 'rotate':
                    outcome = rotate(str(request['provider']))
                else:
                    _verify_bootstrap_authority(request)
                    outcome = bootstrap_from_init()
                response = {
                    'request_id': request['request_id'],
                    'success': True,
                    'action': request['action'],
                    'provider': request['provider'],
                    'source_revision': request['source_revision'],
                    'runtime_refresh_required': bool(outcome.get('runtime_refresh_required')),
                    'initial_admin_token_revoked': bool(outcome.get('initial_admin_token_revoked')),
                    'provider_api_credentials_changed': False,
                    'secret_values_exposed': False,
                }
            except Exception as exc:
                response = {
                    'request_id': path.stem,
                    'success': False,
                    'detail': type(exc).__name__ + ': ' + str(exc)[:250],
                    'secret_values_exposed': False,
                }
            _write_json(RESULTS / (path.stem + '.json'), response, al.pw_uid, al.pw_gid)
            path.unlink(missing_ok=True)


if __name__ == '__main__':
    process()
