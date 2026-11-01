#!/usr/bin/env python3
from __future__ import annotations

import os
import pwd
import shutil
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ROOT = Path('/var/lib/jason/openclaw/identity-lifecycle')


def install() -> None:
    if os.geteuid() != 0:
        raise PermissionError('root install required')
    al = pwd.getpwnam('al')
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chown(ROOT, 0, 0)
    os.chmod(ROOT, 0o700)
    for name in ('requests', 'results'):
        path = ROOT / name
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chown(path, al.pw_uid, al.pw_gid)
        os.chmod(path, 0o700)
    lock = ROOT / 'worker.lock'
    if not lock.exists():
        lock.touch(mode=0o600)
    os.chown(lock, 0, 0)
    os.chmod(lock, 0o600)

    lifecycle_credentials = Path('/var/lib/jason/runtime-secrets/openbao/identity-lifecycle-approle')
    lifecycle_credentials.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chown(lifecycle_credentials, 0, 0)
    os.chmod(lifecycle_credentials, 0o700)

    lib = Path('/usr/local/lib/jason')
    lib.mkdir(parents=True, exist_ok=True, mode=0o755)
    for name in ('provider_secret_provision.py', 'openbao_identity_lifecycle.py', 'openbao_identity_lifecycle_worker.py'):
        destination = lib / name
        shutil.copyfile(BASE / 'tools' / name, destination)
        os.chown(destination, 0, 0)
        os.chmod(destination, 0o755)

    for source_name, command_name in (
        ('request_openbao_identity_rotation.py', 'jason-openbao-identity-rotate'),
        ('request_openbao_identity_bootstrap.py', 'jason-openbao-identity-bootstrap'),
    ):
        command = Path('/usr/local/bin') / command_name
        shutil.copyfile(BASE / 'tools' / source_name, command)
        os.chown(command, 0, 0)
        os.chmod(command, 0o755)

    units = Path('/etc/systemd/system')
    for suffix in ('service', 'timer'):
        name = 'jason-openbao-identity-lifecycle.' + suffix
        destination = units / name
        shutil.copyfile(BASE / 'infrastructure/openclaw-operations/systemd' / name, destination)
        os.chown(destination, 0, 0)
        os.chmod(destination, 0o644)

    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', '--now', 'jason-openbao-identity-lifecycle.timer'], check=True)
    subprocess.run(['systemctl', 'start', 'jason-openbao-identity-lifecycle.service'], check=True)
    print('OPENBAO_IDENTITY_LIFECYCLE_INSTALL=PASS')


if __name__ == '__main__':
    install()
