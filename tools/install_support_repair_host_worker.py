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
    todo_intake_runner = repo / 'tools' / 'todo_engineering_intake.py'
    todo_release_bridge = repo / 'tools' / 'todo_release_bridge.py'
    unit_root = repo / 'infrastructure' / 'openclaw-operations' / 'systemd' / 'user'
    units = ('jason-support-repair-worker.service', 'jason-support-repair-worker.timer')
    if not runner.is_file():
        raise SystemExit('support repair host worker source is missing')
    if not development_runner.is_file():
        raise SystemExit('owner-approved development worker source is missing')
    if not todo_intake_runner.is_file():
        raise SystemExit('TODO engineering intake worker source is missing')
    if not todo_release_bridge.is_file():
        raise SystemExit('TODO release bridge source is missing')
    for unit in units:
        if not (unit_root / unit).is_file():
            raise SystemExit(f'systemd source unit is missing: {unit}')

    install_root = home / '.local' / 'lib' / 'jason'
    user_units = home / '.config' / 'systemd' / 'user'
    source_link = install_root / 'engineering-worker-source'
    if source_link.is_symlink() or source_link.exists():
        if source_link.is_dir() and not source_link.is_symlink():
            raise RuntimeError('engineering-worker-source exists and is not a symlink')
        source_link.unlink()
    source_link.parent.mkdir(parents=True, exist_ok=True)
    source_link.symlink_to(repo, target_is_directory=True)
    _copy(runner, install_root / 'support_repair_host_worker.py', 0o700)
    _copy(development_runner, install_root / 'owner_approved_development_worker.py', 0o700)
    _copy(todo_intake_runner, install_root / 'todo_engineering_intake.py', 0o700)
    _copy(todo_release_bridge, install_root / 'todo_release_bridge.py', 0o700)
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

    uid = os.getuid()
    systemd_env = os.environ.copy()
    systemd_env.setdefault('XDG_RUNTIME_DIR', f'/run/user/{uid}')
    systemd_env.setdefault(
        'DBUS_SESSION_BUS_ADDRESS',
        f'unix:path=/run/user/{uid}/bus',
    )

    if args.activate:
        subprocess.run(
            ['systemctl', '--user', 'daemon-reload'],
            check=True,
            env=systemd_env,
        )
        subprocess.run(
            ['systemctl', '--user', 'enable', '--now', 'jason-support-repair-worker.timer'],
            check=True,
            env=systemd_env,
        )
        subprocess.run(
            ['systemctl', '--user', 'is-active', '--quiet', 'jason-support-repair-worker.timer'],
            check=True,
            env=systemd_env,
        )

    print(f"WORKER_PATH={install_root / 'support_repair_host_worker.py'}")
    print(f"SPOOL_PATH={spool}")
    print(f"ACTIVATED={'yes' if args.activate else 'no'}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
