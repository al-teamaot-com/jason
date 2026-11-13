"""One fail-closed second-drive placement policy for new Jason engineering worktrees.

Old registered Git worktrees stay at their existing paths. Never move a live
worktree, link a legacy path, or fall back to the primary filesystem.
"""
from __future__ import annotations

import os
import re
import stat
from pathlib import Path

ARCHIVE_MOUNT = Path("/srv/jason/archive")
ARCHIVE_ROOT = ARCHIVE_MOUNT / "engineering-worktrees"
LEGACY_ROOT = Path("/home/al/jason-worktrees")
FAMILIES = frozenset({
    "support-repair",
    "support-repair-closure",
    "owner-approved-development",
    "todo-closure",
    "autonomous-repair",
    "documentation-reconciliation",
})
_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,149}\Z")
GIB = 1024 ** 3


class EngineeringStorageUnavailable(RuntimeError):
    pass


def _component(value: str) -> str:
    if not isinstance(value, str) or not _COMPONENT.fullmatch(value):
        raise EngineeringStorageUnavailable("invalid engineering worktree component")
    return value


def _family(value: str) -> str:
    if value not in FAMILIES:
        raise EngineeringStorageUnavailable("unapproved worktree family")
    return value


def path_for(family: str, name: str) -> Path:
    """Reuse an existing legacy worktree, otherwise select the second disk."""
    family, name = _family(family), _component(name)
    old_root = LEGACY_ROOT / family
    old = old_root / name
    if old_root.is_symlink() or old.is_symlink():
        raise EngineeringStorageUnavailable("legacy worktree symlink denied")
    if old.exists():
        if not old.is_dir():
            raise EngineeringStorageUnavailable("legacy worktree path is not a directory")
        return old
    return ARCHIVE_ROOT / family / name


def archive_path(family: str, name: str) -> Path:
    """New ephemeral worktrees always use archive (never recreate old paths)."""
    return ARCHIVE_ROOT / _family(family) / _component(name)


def _check_archive() -> None:
    mount = ARCHIVE_MOUNT
    if mount.is_symlink() or not mount.is_dir() or not os.path.ismount(mount):
        raise EngineeringStorageUnavailable("independent archive mount unavailable")
    if mount.stat().st_dev == Path("/").stat().st_dev:
        raise EngineeringStorageUnavailable("archive aliases primary filesystem")
    vfs = os.statvfs(mount)
    free = vfs.f_bavail * vfs.f_frsize
    used = (vfs.f_blocks - vfs.f_bfree) * vfs.f_frsize
    allocatable_total = free + used
    if (allocatable_total <= 0 or free < 20 * GIB or
            used * 100 >= allocatable_total * 80 or
            (vfs.f_files and vfs.f_favail < 10000)):
        raise EngineeringStorageUnavailable("archive capacity or inode reserve insufficient")


def _private_directory(path: Path) -> None:
    if path.is_symlink():
        raise EngineeringStorageUnavailable("engineering worktree root symlink denied")
    if not path.exists():
        path.mkdir(mode=0o700)
    st = path.lstat()
    if (not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid() or
            stat.S_IMODE(st.st_mode) not in (0o700, 0o2700) or
            st.st_dev != ARCHIVE_MOUNT.stat().st_dev):
        raise EngineeringStorageUnavailable("engineering worktree root identity denied")


def prepare_parent(path: Path) -> None:
    """Validate device and headroom before creating or resuming a worktree."""
    path = Path(path)
    if path.is_symlink():
        raise EngineeringStorageUnavailable("worktree symlink denied")
    parent = path.parent
    if parent.parent == LEGACY_ROOT and parent.name in FAMILIES:
        if not path.is_dir() or parent.is_symlink():
            raise EngineeringStorageUnavailable("new legacy-primary worktree denied")
        return
    if parent.parent != ARCHIVE_ROOT or parent.name not in FAMILIES:
        raise EngineeringStorageUnavailable("unapproved engineering worktree path")
    _check_archive()
    _private_directory(ARCHIVE_ROOT)
    _private_directory(parent)
    if path.exists() and (not path.is_dir() or path.stat().st_dev != ARCHIVE_MOUNT.stat().st_dev):
        raise EngineeringStorageUnavailable("worktree path identity denied")


def prepare_family(family: str) -> Path:
    """Called by the existing governed installer, before sandboxed service start."""
    family = _family(family)
    _check_archive()
    _private_directory(ARCHIVE_ROOT)
    result = ARCHIVE_ROOT / family
    _private_directory(result)
    return result
