#!/usr/bin/env python3
"""Install the stable rootless Jason Release Manager host service."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = Path.home() / ".local" / "lib" / "jason"
UNIT_DIR = Path.home() / ".config" / "systemd" / "user"
STATE = Path("/var/lib/jason/openclaw/release-manager")
SOURCE_REPO = Path("/home/al/projects/jason")
APPROVAL_WORKTREE = LIB / "release-approval-source"
APPROVAL_OVERRIDE = "10-canonical-release-scope.conf"


def copy_mode(source: Path, destination: Path, mode: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    os.chmod(destination, mode)



def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args], text=True, capture_output=True,
        timeout=75, check=check,
    )


def _git_common_dir(repo: Path) -> Path:
    raw = _git(repo, "rev-parse", "--git-common-dir").stdout.strip()
    if not raw:
        raise RuntimeError("approval source has no canonical Git common directory")
    value = Path(raw)
    return (value if value.is_absolute() else repo / value).resolve()


def ensure_authoritative_approval_worktree() -> None:
    """Bind approval-only scope review to the canonical shared Git registry.

    The separate managed engineering clone has a different worktree inventory.
    Never use it to verify exact release-scope receipts; an isolated clone
    would silently ignore concurrent dirty worktrees and fail closed later.
    This worktree has one stable path across forward releases and is never
    deleted or force-reset to hide dirty work.
    """
    revision = ROOT.name
    if not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise RuntimeError("approval worktree requires exact immutable release SHA")
    if SOURCE_REPO.is_symlink() or not SOURCE_REPO.is_dir():
        raise RuntimeError("authoritative Project Jason Git directory missing")
    canonical = _git_common_dir(SOURCE_REPO)
    if canonical != (SOURCE_REPO / ".git").resolve() or not canonical.is_dir():
        raise RuntimeError("canonical Project Jason Git registry is not a directory")
    # The pinned immutable SHA must exist in the canonical source and be on
    # protected main. Fetch only if needed; never switch its dirty worktree.
    if _git(SOURCE_REPO, "cat-file", "-e", revision + "^{commit}", check=False).returncode != 0:
        _git(SOURCE_REPO, "fetch", "--no-tags", "origin", "main")
    _git(SOURCE_REPO, "cat-file", "-e", revision + "^{commit}")
    if _git(SOURCE_REPO, "merge-base", "--is-ancestor", revision, "origin/main", check=False).returncode != 0:
        raise RuntimeError("approval worktree revision is not on protected main")

    if APPROVAL_WORKTREE.is_symlink():
        raise RuntimeError("approval worktree must not be a symlink")
    if APPROVAL_WORKTREE.exists():
        if not APPROVAL_WORKTREE.is_dir() or _git_common_dir(APPROVAL_WORKTREE) != canonical:
            raise RuntimeError("approval worktree is not in authoritative Git registry")
        if _git(APPROVAL_WORKTREE, "status", "--porcelain").stdout.strip():
            raise RuntimeError("approval worktree has uncommitted changes")
        observed = _git(APPROVAL_WORKTREE, "rev-parse", "HEAD").stdout.strip()
        if observed != revision:
            _git(APPROVAL_WORKTREE, "checkout", "--detach", revision)
    else:
        APPROVAL_WORKTREE.parent.mkdir(parents=True, exist_ok=True)
        _git(SOURCE_REPO, "worktree", "add", "--detach", str(APPROVAL_WORKTREE), revision)
    if (_git_common_dir(APPROVAL_WORKTREE) != canonical
            or _git(APPROVAL_WORKTREE, "rev-parse", "HEAD").stdout.strip() != revision
            or _git(APPROVAL_WORKTREE, "status", "--porcelain").stdout.strip()):
        raise RuntimeError("approval worktree exact-source verification failed")
    if not (APPROVAL_WORKTREE / "tools/manual_release_scope.py").is_file():
        raise RuntimeError("approval worktree lacks canonical scope reviewer")



def install_approval_only_rollback_override() -> None:
    """Keep the source-reviewed approval-only command after LKG unit restore.

    The old LKG installer restores its own base .service but does not remove
    systemd drop-ins. This exact reviewed override preserves authoritative
    Git-worktree scope after a failed candidate while production is frozen.
    Refuse symlinks, unknown existing files, or wrong ownership. Never modify
    a different unit or an existing unreviewed override.
    """
    source = (ROOT / "infrastructure/openclaw-operations/systemd/user"
              / "jason-release-approval-only.service.d" / APPROVAL_OVERRIDE)
    if source.is_symlink() or not source.is_file():
        raise RuntimeError("approval rollback override source must be a reviewed regular file")
    reviewed = source.read_bytes()
    expected = (
        b"[Service]\n"
        b"ExecStart=\n"
        b"ExecStart=/usr/bin/python3 /home/al/.local/lib/jason/release_manager_host_runner.py "
        b"--repo /home/al/.local/lib/jason/release-approval-source "
        b"--state-root /var/lib/jason/openclaw/release-manager approval-only-held\n"
        b"WorkingDirectory=/home/al/.local/lib/jason/release-approval-source\n"
    )
    if reviewed != expected:
        raise RuntimeError("approval rollback override differs from reviewed exact content")
    if UNIT_DIR.is_symlink() or not UNIT_DIR.is_dir():
        raise RuntimeError("systemd user-unit directory is not an ordinary directory")
    destination_dir = UNIT_DIR / "jason-release-approval-only.service.d"
    if destination_dir.is_symlink():
        raise RuntimeError("approval rollback override directory is a symlink")
    destination_dir.mkdir(mode=0o755, exist_ok=True)
    info = destination_dir.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) & 0o022):
        raise RuntimeError("approval rollback override directory is not safely owned")
    destination = destination_dir / APPROVAL_OVERRIDE
    if destination.is_symlink():
        raise RuntimeError("approval rollback override target is a symlink")
    if destination.exists():
        info = destination.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o644
                or destination.read_bytes() != reviewed):
            raise RuntimeError("existing approval rollback override is not reviewed")
    else:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(destination, flags, 0o644)
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(reviewed)
                output.flush()
                os.fsync(output.fileno())
        except Exception:
            try:
                destination.unlink()
            except OSError:
                pass
            raise
        if destination.read_bytes() != reviewed:
            raise RuntimeError("approval rollback override readback failed")


def install_approval_only_units(*, activate: bool = False) -> bool:
    """Install only the reviewed offer units, never update a running controller.

    Native host reconciliation calls this after root policy staging and before
    required-unit verification. Full Release Manager installation reuses it.
    """
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
        ensure_authoritative_approval_worktree()
        install_approval_only_rollback_override()
        for unit_name in ("jason-release-approval-only.service",
                          "jason-release-approval-only.timer"):
            copy_mode(
                ROOT / "infrastructure" / "openclaw-operations" / "systemd"
                / "user" / unit_name, UNIT_DIR / unit_name, 0o644,
            )

    if not approval_timer_declared:
        return False
    uid = os.getuid()
    env = os.environ.copy()
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
    env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{uid}/bus")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True, env=env)
    if activate:
        subprocess.run(
            ["systemctl", "--user", "enable", "--now", "jason-release-approval-only.timer"],
            check=True, env=env,
        )
        subprocess.run(
            ["systemctl", "--user", "is-active", "--quiet", "jason-release-approval-only.timer"],
            check=True, env=env,
        )
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--approval-units-only", action="store_true")
    args = parser.parse_args()
    if args.approval_units_only:
        if os.geteuid() == 0:
            raise RuntimeError("approval user units must be installed as their existing owner")
        installed = install_approval_only_units(activate=args.activate)
        print("JASON_APPROVAL_UNITS_INSTALL=" + ("PASS" if installed else "NOT_DECLARED"))
        return 0

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
    # The installed PM invokes the genuine authenticated MCP read acceptance
    # gate before release close. Its source-bound helper must be installed
    # atomically with the entrypoint on all future native N -> N+1 upgrades.
    copy_mode(ROOT / "tools" / "production_read_canary_gate.py",
              LIB / "production_read_canary_gate.py", 0o644)
    copy_mode(ROOT / "tools" / "worker_execution_enrollment.py", LIB / "worker_execution_enrollment.py", 0o644)
    # One native release transaction owns OpenClaw Workboard activation and
    # rollback. Install both reviewed helpers with the manager entrypoint.
    copy_mode(ROOT / "tools" / "openclaw_workboard_release_scope.py",
              LIB / "openclaw_workboard_release_scope.py", 0o644)
    copy_mode(ROOT / "tools" / "openclaw_workboard_release_surface.py",
              LIB / "openclaw_workboard_release_surface.py", 0o644)
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

    approval_timer_declared = install_approval_only_units()

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
