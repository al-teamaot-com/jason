#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


def copy(source: Path, destination: Path, mode: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".tmp")
    shutil.copyfile(source, temp)
    os.chmod(temp, mode)
    os.replace(temp, destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("/home/al/projects/jason"))
    parser.add_argument("--root", type=Path, default=Path("/var/lib/jason/openclaw/self-heal"))
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()

    repo = args.repo.expanduser().resolve()
    root = args.root.expanduser().resolve()
    home = Path.home()
    source = repo / "tools" / "jason_self_heal_watchdog.py"
    unit_root = repo / "infrastructure" / "openclaw-operations" / "systemd" / "user"
    units = ("jason-self-heal-watchdog.service", "jason-self-heal-watchdog.timer")
    if not source.is_file():
        raise SystemExit("self-heal watchdog source is missing")
    for unit in units:
        if not (unit_root / unit).is_file():
            raise SystemExit(f"systemd source unit is missing: {unit}")

    install_root = home / ".local" / "lib" / "jason"
    user_units = home / ".config" / "systemd" / "user"
    copy(source, install_root / "jason_self_heal_watchdog.py", 0o700)
    for unit in units:
        copy(unit_root / unit, user_units / unit, 0o600)

    for path in (root, root / "incidents", root / "escalations", root / "notifications"):
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path, 0o700)

    if args.activate:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(
            ["systemctl", "--user", "enable", "--now", "jason-self-heal-watchdog.timer"],
            check=True,
        )
        subprocess.run(
            ["systemctl", "--user", "is-active", "--quiet", "jason-self-heal-watchdog.timer"],
            check=True,
        )

    print(f"WATCHDOG_PATH={install_root / 'jason_self_heal_watchdog.py'}")
    print(f"STATE_ROOT={root}")
    print(f"ACTIVATED={'yes' if args.activate else 'no'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
