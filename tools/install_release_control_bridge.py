#!/usr/bin/env python3
"""Install the root-owned, read-only release-control evidence publisher."""
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def install() -> None:
    if os.geteuid() != 0:
        raise PermissionError("root privileges required")
    destination = Path("/usr/local/lib/jason/release_control_bridge_worker.py")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "tools/release_control_bridge_worker.py", destination)
    os.chown(destination, 0, 0)
    os.chmod(destination, 0o755)
    for suffix in ("service", "timer"):
        name = "jason-release-control-readback." + suffix
        dst = Path("/etc/systemd/system") / name
        shutil.copyfile(ROOT / "infrastructure/openclaw-operations/systemd" / name, dst)
        os.chown(dst, 0, 0)
        os.chmod(dst, 0o644)
    snapshot = Path("/var/lib/jason/openclaw/release-manager/protected-readback")
    snapshot.mkdir(parents=True, exist_ok=True, mode=0o700)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", "--now", "jason-release-control-readback.timer"], check=True)
    subprocess.run(["systemctl", "start", "jason-release-control-readback.service"], check=True)
    print("JASON_PROTECTED_READBACK_INSTALL=PASS")


if __name__ == "__main__":
    install()
