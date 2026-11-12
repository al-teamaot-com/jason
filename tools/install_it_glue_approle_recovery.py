#!/usr/bin/env python3
"""Root-owned, source-pinned install of *inert* IT Glue READ AppRole recovery.

Invoked only by existing signed native host reconciliation for an exact SHA.
Installs reviewed source, never reads credentials or performs OpenBao requests.
No service, timer, Docker, network, release-freeze or policy mutations.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import stat
import tempfile
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RELEASE_ROOT = Path("/opt/jason/releases")
CURRENT = Path("/opt/jason/current")
TARGET = Path("/usr/local/lib/jason")
FILES = ("it_glue_approle_recovery.py", "provider_secret_provision.py")


class InstallDenied(PermissionError):
    pass


def _trusted_source(sha: str, *, release_root: Path = RELEASE_ROOT,
                    current: Path = CURRENT) -> Path:
    if os.geteuid() != 0:
        raise InstallDenied("ROOT_ONLY_IT_GLUE_RECOVERY_INSTALL")
    if not SHA_RE.fullmatch(sha):
        raise InstallDenied("EXACT_SOURCE_REVISION_REQUIRED")
    source = release_root / sha
    expected_script = source / "tools" / "install_it_glue_approle_recovery.py"
    if (Path(__file__).resolve() != expected_script
            or source.resolve(strict=True) != current.resolve(strict=True)):
        raise InstallDenied("NATIVE_CURRENT_RELEASE_SOURCE_REQUIRED")
    for part in (release_root, source, source / "tools"):
        info = os.lstat(part)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
                or info.st_gid != 0 or info.st_mode & 0o002):
            raise InstallDenied("RELEASE_SOURCE_PATH_UNSAFE")
    for filename in FILES:
        path = source / "tools" / filename
        meta = os.lstat(path)
        if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != 0
                or meta.st_gid != 0 or meta.st_mode & 0o002):
            raise InstallDenied("RELEASE_SOURCE_FILE_UNSAFE")
    return source


def _atomic_install(src: Path, dst: Path, *, root_uid: int = 0,
                    root_gid: int = 0) -> str:
    source = src.read_bytes()
    if not source or len(source) > 2_000_000:
        raise InstallDenied("REVIEWED_SOURCE_SIZE_INVALID")
    info = os.lstat(dst.parent)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != root_uid or info.st_mode & 0o022:
        raise InstallDenied("ROOT_LIBRARY_DIR_UNSAFE")
    if os.path.lexists(dst):
        current = os.lstat(dst)
        if not stat.S_ISREG(current.st_mode) or current.st_uid != root_uid:
            raise InstallDenied("ROOT_LIBRARY_FILE_UNSAFE")
    fd, temporary = tempfile.mkstemp(prefix=".itglue-root-", dir=dst.parent)
    try:
        os.fchown(fd, root_uid, root_gid)
        os.fchmod(fd, 0o500)
        with os.fdopen(fd, "wb") as out:
            out.write(source)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, dst)
        parentfd = os.open(dst.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parentfd)
        finally:
            os.close(parentfd)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)
    if dst.read_bytes() != source:
        raise InstallDenied("ROOT_INSTALLED_SOURCE_MISMATCH")
    return hashlib.sha256(source).hexdigest()


def install(sha: str) -> dict[str, object]:
    source = _trusted_source(sha)
    if TARGET.is_symlink() or not TARGET.is_dir():
        raise InstallDenied("ROOT_LIBRARY_DIR_UNSAFE")
    digests: dict[str, str] = {}
    for file in FILES:
        digests[file] = _atomic_install(source / "tools" / file, TARGET / file)
    return {
        "status": "pass", "source_revision": sha,
        "installed": sorted(digests),
        "sha256": digests,
        "root_only": True, "provider_secret_values_read": False,
        "provider_secret_values_written": False, "runtime_restarted": False,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Install dormant IT Glue READ AppRole recovery")
    p.add_argument("--source-revision", required=True)
    args = p.parse_args(argv)
    try:
        outcome = install(args.source_revision)
    except Exception as exc:
        label = str(exc) if isinstance(exc, InstallDenied) else "INSTALL_" + type(exc).__name__
        print("DENIED: " + label)
        return 1
    import json
    print(json.dumps(outcome, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
