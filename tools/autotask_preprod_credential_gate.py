#!/usr/bin/env python3
"""Inspect test credential metadata only, without reading any secret values.

A passing check is not proof of provider authority, least-privilege test
identity, requester impersonation, or a successful live provider canary.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path

FORBIDDEN = (
    '/opt/jason/bootstrap',
    '/run/jason-runtime-credentials',
    '/run/jason-secrets',
    '/var/lib/jason',
)
SECRET_NAMES = ('role_id', 'secret_id')


def _result(reason: str) -> dict:
    return {
        'ready': reason == 'ISOLATION_METADATA_CHECK_PASSED_NOT_AUTHORIZATION_PROOF',
        'reason': reason,
    }


def check(root: Path) -> dict:
    # Do not allow ".." components to disguise an ancestor or a production
    # credential source. The path, not credential contents, is examined.
    root = root.absolute()
    if '..' in root.parts:
        return _result('NON_CANONICAL_CREDENTIAL_DIRECTORY')
    try:
        if not root.is_dir():
            return _result('PRIVATE_DIRECTORY_MISSING_OR_SYMLINK')
        for ancestor in (root, *root.parents):
            if ancestor.is_symlink():
                return _result('SYMLINK_IN_CREDENTIAL_PATH')
        resolved = root.resolve(strict=True)
        for forbidden in FORBIDDEN:
            base = Path(forbidden)
            if resolved == base or base in resolved.parents:
                return _result('PRODUCTION_CREDENTIAL_PATH_FORBIDDEN')

        owner = os.geteuid()
        directory = resolved.stat()
        if directory.st_uid != owner:
            return _result('CREDENTIAL_DIRECTORY_OWNER_MISMATCH')
        if not stat.S_ISDIR(directory.st_mode) or stat.S_IMODE(directory.st_mode) & 0o077:
            return _result('DIRECTORY_PERMISSIONS_TOO_BROAD')

        for name in SECRET_NAMES:
            path = resolved / name
            if path.is_symlink() or not path.is_file():
                return _result('ISOLATED_CREDENTIAL_NOT_PRESENT')
            metadata = path.stat()
            if metadata.st_uid != owner:
                return _result('CREDENTIAL_FILE_OWNER_MISMATCH')
            if (not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_nlink != 1
                    or stat.S_IMODE(metadata.st_mode) & 0o077
                    or not 0 < metadata.st_size <= 16384):
                return _result('CREDENTIAL_METADATA_INVALID')
    except (OSError, RuntimeError, ValueError):
        # Never print file paths, contents, or OS diagnostics that could expose
        # test credential source details to a shared pipeline log.
        return _result('CREDENTIAL_METADATA_UNAVAILABLE')
    return _result('ISOLATION_METADATA_CHECK_PASSED_NOT_AUTHORIZATION_PROOF')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', required=True, type=Path)
    args = parser.parse_args()
    result = check(args.directory)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result['ready'] else 1)


if __name__ == '__main__':
    main()
