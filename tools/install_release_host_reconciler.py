#!/usr/bin/env python3
"""Install the bounded root-owned Jason host release reconciliation boundary."""

from __future__ import annotations

import grp
import os
import pwd
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYSTEMD = Path("/etc/systemd/system")
LIB = Path("/usr/local/lib/jason")
SPOOL = Path("/var/lib/jason/openclaw/release-manager/host-reconcile")


def install(source: Path, destination: Path, mode: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    os.chown(destination, 0, 0)
    os.chmod(destination, mode)


def main() -> int:
    if os.geteuid() != 0:
        raise SystemExit("root privileges are required")

    al = pwd.getpwnam("al")
    jason_gid = grp.getgrnam("jason").gr_gid

    for path in (SPOOL, SPOOL / "requests", SPOOL / "results"):
        path.mkdir(parents=True, exist_ok=True)
        os.chown(path, al.pw_uid, jason_gid)
        os.chmod(path, 0o750)

    install(
        ROOT / "tools" / "release_host_reconcile_worker.py",
        LIB / "release_host_reconcile_worker.py",
        0o755,
    )
    for name in (
        "jason-release-host-reconcile.service",
        "jason-release-host-reconcile.path",
    ):
        install(
            ROOT / "infrastructure" / "openclaw-operations" / "systemd" / name,
            SYSTEMD / name,
            0o644,
        )

    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(
        ["systemctl", "enable", "--now", "jason-release-host-reconcile.path"],
        check=True,
    )
    state = subprocess.check_output(
        ["systemctl", "is-active", "jason-release-host-reconcile.path"],
        text=True,
    ).strip()
    if state != "active":
        raise RuntimeError("release host reconciliation path unit is not active")

    print("JASON_RELEASE_HOST_RECONCILER_INSTALL=PASS")
    print("SPOOL=" + str(SPOOL))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
