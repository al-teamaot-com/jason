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


def main(*, stage_only: bool = False) -> int:
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
    if stage_only:
        # Called only by the exact immutable host reconciliation after
        # materializing its release directory and managed Git source, BEFORE
        # candidate-only services are copied/started. Stage reviewed units
        # as ALLOWED but not yet REQUIRED to keep the independent watchdog
        # truthful throughout the bounded transition.
        import protected_root_policy_migration as migration
        candidate = ROOT.name
        control = migration._json(migration._root_only(
            migration.ROOT / "production-control-state.json"))
        baseline = (((control.get("last_known_good") or {}).get("manifest") or {})
                    .get("revision"))
        if (not migration.SHA.fullmatch(candidate)
                or not isinstance(baseline, str)
                or not migration.SHA.fullmatch(baseline)):
            raise RuntimeError("stage-only requires exact immutable candidate and root LKG")
        if candidate != baseline:
            old = migration._source_policy(baseline)
            new = migration._source_policy(candidate)
            marker = "jason-openclaw-authority-full-integrity.timer"
            if (marker in new["required_system_units"]
                    and marker not in old["required_system_units"]):
                result = migration.stage_for_candidate(candidate, baseline)
                print("JASON_ROOT_POLICY_STAGING=" + result)
        print("JASON_ROOT_HOST_RECONCILER_STAGE_ONLY=PASS")
        return 0

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
    import sys
    if sys.argv[1:] == ["--stage-only"]:
        raise SystemExit(main(stage_only=True))
    if sys.argv[1:]:
        raise SystemExit("usage: install_release_host_reconciler.py [--stage-only]")
    raise SystemExit(main())
