#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


def _copy(source: Path, destination: Path, mode: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + '.tmp')
    shutil.copyfile(source, temp)
    os.chmod(temp, mode)
    os.replace(temp, destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, default=Path('/home/al/projects/jason'))
    parser.add_argument('--spool', type=Path, default=Path('/var/lib/jason/openclaw/support-repair'))
    parser.add_argument('--activate', action='store_true')
    args = parser.parse_args()

    repo = args.repo.expanduser().resolve()
    spool = args.spool.expanduser().resolve()
    home = Path.home()
    runner = repo / 'tools' / 'support_repair_host_worker.py'
    development_runner = repo / 'tools' / 'owner_approved_development_worker.py'
    unit_root = repo / 'infrastructure' / 'openclaw-operations' / 'systemd' / 'user'
    units = ('jason-support-repair-worker.service', 'jason-support-repair-worker.timer')
    if not runner.is_file():
        raise SystemExit('support repair host worker source is missing')
    if not development_runner.is_file():
        raise SystemExit('owner-approved development worker source is missing')
    for unit in units:
        if not (unit_root / unit).is_file():
            raise SystemExit(f'systemd source unit is missing: {unit}')

    install_root = home / '.local' / 'lib' / 'jason'
    user_units = home / '.config' / 'systemd' / 'user'
    _copy(runner, install_root / 'support_repair_host_worker.py', 0o700)
    _copy(development_runner, install_root / 'owner_approved_development_worker.py', 0o700)
    for unit in units:
        _copy(unit_root / unit, user_units / unit, 0o600)

    for path in (
        spool,
        spool / 'reasoning',
        spool / 'reasoning' / 'requests',
        spool / 'reasoning' / 'responses',
    ):
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path, 0o700)

    if args.activate:
        subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', '--user', 'enable', '--now', 'jason-support-repair-worker.timer'], check=True)
        subprocess.run(['systemctl', '--user', 'is-active', '--quiet', 'jason-support-repair-worker.timer'], check=True)

    print(f"WORKER_PATH={install_root / 'support_repair_host_worker.py'}")
    print(f"SPOOL_PATH={spool}")
    print(f"ACTIVATED={'yes' if args.activate else 'no'}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
