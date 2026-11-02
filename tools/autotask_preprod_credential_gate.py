#!/usr/bin/env python3
"""Check isolation metadata only. Never open secret files or contact providers."""
import argparse
import json
import os
from pathlib import Path

FORBIDDEN = ('/opt/jason/bootstrap', '/run/jason-runtime-credentials', '/run/jason-secrets', '/var/lib/jason')


def check(root: Path) -> dict:
    root = root.absolute()
    if root.is_symlink() or not root.is_dir():
        return {'ready': False, 'reason': 'PRIVATE_DIRECTORY_MISSING_OR_SYMLINK'}
    resolved = root.resolve()
    if any(str(resolved) == p or str(resolved).startswith(p + '/') for p in FORBIDDEN):
        return {'ready': False, 'reason': 'PRODUCTION_CREDENTIAL_PATH_FORBIDDEN'}
    if root.stat().st_mode & 0o077:
        return {'ready': False, 'reason': 'DIRECTORY_PERMISSIONS_TOO_BROAD'}
    for name in ('role_id', 'secret_id'):
        p = root / name
        if p.is_symlink() or not p.is_file():
            return {'ready': False, 'reason': 'ISOLATED_CREDENTIAL_NOT_PRESENT'}
        stat = p.stat()
        if stat.st_mode & 0o077 or stat.st_size == 0 or stat.st_size > 16384:
            return {'ready': False, 'reason': 'CREDENTIAL_METADATA_INVALID'}
    return {'ready': True, 'reason': 'ISOLATION_METADATA_CHECK_PASSED_NOT_AUTHORIZATION_PROOF'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', required=True, type=Path)
    args = parser.parse_args()
    result = check(args.directory)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result['ready'] else 1)


if __name__ == '__main__':
    main()
