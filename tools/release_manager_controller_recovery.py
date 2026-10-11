#!/usr/bin/env python3
"""Fail-closed operator-owned controller repair, never a production promotion."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import os
import re
import subprocess
import tempfile
from pathlib import Path

SHA = re.compile(r"[0-9a-f]{40}\Z")
DEFAULT_REPO = Path('/home/al/.local/lib/jason/engineering-worker-source')
DEFAULT_TARGET = Path('/home/al/.local/lib/jason/release_manager_host_runner.py')


def git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.DEVNULL)


def recover(repo: Path, target: Path, revision: str, *, dry_run: bool = True) -> dict:
    if not SHA.fullmatch(revision):
        raise ValueError('exact candidate revision required')
    if repo != DEFAULT_REPO or repo.resolve() != DEFAULT_REPO.resolve() or target != DEFAULT_TARGET:
        raise ValueError('only canonical managed source and controller permitted')
    remote = git(repo, 'rev-parse', 'refs/remotes/origin/main').decode().strip()
    if remote != revision:
        raise ValueError('revision must match refreshed protected main')
    expected = git(repo, 'show', f'{revision}:tools/release_manager_host_runner.py')
    if b'def _read_protected_snapshot(' not in expected:
        raise ValueError('candidate controller missing protected readback')
    current = target.read_bytes()
    expected_digest = hashlib.sha256(expected).hexdigest()
    result = {'candidate_sha': revision, 'candidate_digest': expected_digest,
              'previous_digest': hashlib.sha256(current).hexdigest(), 'changed': current != expected}
    if dry_run or current == expected:
        return result
    if target.is_symlink() or target.stat().st_uid != os.getuid():
        raise PermissionError('controller must be operator-owned regular file')
    # Serialize with the same lock honored by production promotions.
    lock = Path('/var/lib/jason/openclaw/release-manager/production-transaction.lock')
    with lock.open('a+') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        backup = target.with_name(target.name + '.recovery-backup-' + result['previous_digest'][:16])
        backup.write_bytes(current)
        backup.chmod(0o600)
        fd, temp_name = tempfile.mkstemp(dir=target.parent, prefix='.controller-recovery-')
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(expected)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temp_name, 0o755)
            if hashlib.sha256(Path(temp_name).read_bytes()).hexdigest() != expected_digest:
                raise ValueError('candidate copy checksum mismatch')
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected_digest:
            raise ValueError('installed controller readback mismatch')
        result['backup'] = str(backup)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--revision', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    print(recover(DEFAULT_REPO, DEFAULT_TARGET, args.revision, dry_run=not args.apply))


if __name__ == '__main__':
    main()
