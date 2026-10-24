#!/usr/bin/env python3
"""Install the stable rootless Jason Release Manager host service."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = Path.home() / ".local" / "lib" / "jason"
UNIT_DIR = Path.home() / ".config" / "systemd" / "user"
STATE = Path("/var/lib/jason/openclaw/release-manager")


def copy_mode(source: Path, destination: Path, mode: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    os.chmod(destination, mode)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()

    LIB.mkdir(parents=True, exist_ok=True)
    UNIT_DIR.mkdir(parents=True, exist_ok=True)
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    source_link = LIB / "release-manager-source"
    if source_link.is_symlink() or source_link.exists():
        if source_link.is_dir() and not source_link.is_symlink():
            raise RuntimeError("release-manager-source exists and is not a symlink")
        source_link.unlink()
    source_link.symlink_to(ROOT, target_is_directory=True)

    copy_mode(ROOT / "tools" / "release_manager_host_runner.py", LIB / "release_manager_host_runner.py", 0o755)
    copy_mode(ROOT / "tools" / "release_manager_gate.py", LIB / "release_manager_gate.py", 0o644)
    copy_mode(ROOT / "tools" / "worker_execution_enrollment.py", LIB / "worker_execution_enrollment.py", 0o644)
    copy_mode(
        ROOT / "infrastructure" / "openclaw-operations" / "systemd" / "user" / "jason-release-manager.service",
        UNIT_DIR / "jason-release-manager.service",
        0o644,
    )
    copy_mode(
        ROOT / "infrastructure" / "openclaw-operations" / "systemd" / "user" / "jason-release-manager.timer",
        UNIT_DIR / "jason-release-manager.timer",
        0o644,
    )

    # Two-phase protected root-policy bootstrap (#1993): stage the reviewed
    # migrator without installing any new user unit before the root worker can
    # independently recognize that exact owner/CCC reviewed unit delta.
    desired = json.loads((ROOT / "config/production-desired-state.json").read_text())
    approval_timer_declared = (
        "jason-release-approval-only.timer" in desired["required_user_units"])
    approval_service_declared = (
        "jason-release-approval-only.service" in desired["allowed_user_units"])
    if approval_timer_declared != approval_service_declared:
        raise RuntimeError("held-only Teams approval systemd policy is incomplete")
    if approval_timer_declared:
        for unit_name in ("jason-release-approval-only.service",
                          "jason-release-approval-only.timer"):
            copy_mode(
                ROOT / "infrastructure" / "openclaw-operations" / "systemd"
                / "user" / unit_name, UNIT_DIR / unit_name, 0o644,
            )

    uid = os.getuid()
    systemd_env = os.environ.copy()
    systemd_env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
    systemd_env.setdefault(
        "DBUS_SESSION_BUS_ADDRESS",
        f"unix:path=/run/user/{uid}/bus",
    )
    subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        check=True,
        env=systemd_env,
    )
    if args.activate:
        # The new timer is not activated by the helper-bootstrap release:
        # it must be both declared and root-migration-approved first.
        timers = ["jason-release-manager.timer"]
        if approval_timer_declared:
            timers.append("jason-release-approval-only.timer")
        for timer_name in timers:
            subprocess.run(
                ["systemctl", "--user", "enable", "--now", timer_name],
                check=True, env=systemd_env,
            )
    print("JASON_RELEASE_MANAGER_INSTALL=PASS")
    print("STATE_ROOT=" + str(STATE))
    print("TIMER_ACTIVATED=" + ("YES" if args.activate else "NO"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
