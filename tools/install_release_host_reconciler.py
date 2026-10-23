#!/usr/bin/env python3
"""Install the bounded root-owned Jason host release reconciliation boundary."""

from __future__ import annotations

import grp
import os
import pwd
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYSTEMD = Path("/etc/systemd/system")
LIB = Path("/usr/local/lib/jason")
SPOOL = Path("/var/lib/jason/openclaw/release-manager/host-reconcile")


def install(source: Path, destination: Path, mode: int) -> None:
    """Atomically install one root-owned file; never expose a partial worker."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".jason-root-install-", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as output, source.open("rb") as inp:
            shutil.copyfileobj(inp, output)
            output.flush()
            os.fchown(output.fileno(), 0, 0)
            os.fchmod(output.fileno(), mode)
            os.fsync(output.fileno())
        os.replace(temporary, destination)
        handle = os.open(destination.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(handle)
        finally:
            os.close(handle)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    if os.geteuid() != 0:
        raise SystemExit("root privileges are required")

    al = pwd.getpwnam("al")
    jason_gid = grp.getgrnam("jason").gr_gid

    for path in (SPOOL, SPOOL / "requests", SPOOL / "results"):
        path.mkdir(parents=True, exist_ok=True)
        os.chown(path, al.pw_uid, jason_gid)
        os.chmod(path, 0o750)

    # Stage the audited helper first: never expose a newly installed root
    # worker that cannot yet restore protected policy during rollback.
    install(
        ROOT / "tools" / "protected_root_policy_migration.py",
        LIB / "protected_root_policy_migration.py",
        0o755,
    )
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
