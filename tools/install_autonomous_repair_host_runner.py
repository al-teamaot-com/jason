#!/usr/bin/env python3
"""Install Jason's rootless autonomous repair host runner for the current user."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


def _copy(source: Path, destination: Path, mode: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".tmp")
    shutil.copyfile(source, temp)
    os.chmod(temp, mode)
    os.replace(temp, destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("/home/al/projects/jason"))
    parser.add_argument("--spool", type=Path, default=Path("/var/lib/jason/openclaw/autonomous-repair"))
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()

    repo = args.repo.expanduser().resolve()
    spool = args.spool.expanduser().resolve()
    home = Path.home()

    runner_source = repo / "tools" / "autonomous_repair_host_runner.py"
    unit_source = repo / "infrastructure" / "openclaw-operations" / "systemd" / "user"
    if not runner_source.is_file():
        raise SystemExit("autonomous repair host runner source is missing")
    for name in (
        "jason-autonomous-repair-runner.service",
        "jason-autonomous-repair-runner.path",
    ):
        if not (unit_source / name).is_file():
            raise SystemExit(f"systemd source unit is missing: {name}")

    install_root = home / ".local" / "lib" / "jason"
    user_units = home / ".config" / "systemd" / "user"
    _copy(
        runner_source,
        install_root / "autonomous_repair_host_runner.py",
        0o700,
    )
    for name in (
        "jason-autonomous-repair-runner.service",
        "jason-autonomous-repair-runner.path",
    ):
        _copy(unit_source / name, user_units / name, 0o600)

    for name in ("requests", "processing", "results"):
        (spool / name).mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(spool / name, 0o700)
    os.chmod(spool, 0o700)

    if args.activate:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(
            [
                "systemctl",
                "--user",
                "enable",
                "--now",
                "jason-autonomous-repair-runner.path",
            ],
            check=True,
        )
        subprocess.run(
            [
                "systemctl",
                "--user",
                "is-active",
                "--quiet",
                "jason-autonomous-repair-runner.path",
            ],
            check=True,
        )

    print(f"RUNNER_PATH={install_root / 'autonomous_repair_host_runner.py'}")
    print(f"SPOOL_PATH={spool}")
    print(f"ACTIVATED={'yes' if args.activate else 'no'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
