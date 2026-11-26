#!/usr/bin/env python3
"""Non-production Stage A control installation/rollback acceptance.

All writes are confined to a private, clearly marked temporary sandbox.
No production apply command or root authority exists in this module.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile
from typing import Any

from tools import pmv4_stage_a_packet as packet

LAB_MARKER = ".pmv4-stage-a-source-only"


def _sandbox(path: Path) -> Path:
    path = Path(path)
    temporary = Path(tempfile.gettempdir()).resolve(strict=True)
    if (not path.is_absolute() or ".." in path.parts or path.is_symlink()
            or not path.is_dir() or path.resolve(strict=True) != path
            or temporary not in path.parents):
        raise ValueError("STAGE_A_NONPRODUCTION_SANDBOX_REQUIRED")
    if (path.stat().st_uid != os.geteuid()
            or stat.S_IMODE(path.stat().st_mode) & 0o077
            or (path / LAB_MARKER).is_symlink()
            or not (path / LAB_MARKER).is_file()
            or (path / LAB_MARKER).read_text() != "stage-a-temporary-test-only"):
        raise ValueError("STAGE_A_NONPRODUCTION_SANDBOX_UNTRUSTED")
    return path


def _mapped(sandbox: Path, absolute: str) -> Path:
    if not isinstance(absolute, str) or not absolute.startswith("/"):
        raise ValueError("STAGE_A_LAB_PATH_INVALID")
    if not any(absolute == prefix or absolute.startswith(prefix + "/")
               for prefix in (packet.ROOT, packet.HOST_CODE, packet.ETC)):
        raise ValueError("STAGE_A_LAB_PROTECTED_BOUNDARY")
    target = sandbox / absolute.lstrip("/")
    # A forged symlink in an otherwise private /tmp laboratory must never
    # redirect a simulated host write to /var, /etc, /opt or another tenant.
    ancestor = target.parent
    while ancestor != sandbox:
        if ancestor.is_symlink():
            raise ValueError("STAGE_A_LAB_PATH_TRAVERSAL")
        if sandbox not in ancestor.parents:
            raise ValueError("STAGE_A_LAB_PATH_ESCAPE")
        ancestor = ancestor.parent
    return target


def _expected_file_data(repo: Path, row: dict[str, Any]) -> bytes:
    if row["source"] == "constant":
        return packet.STATIC_DOCS[row["path"]][0]
    source = repo / row["source"]
    if not source.is_file() or source.is_symlink():
        raise ValueError("STAGE_A_LAB_SOURCE_CHANGED")
    data = source.read_bytes()
    if packet._digest(data) != row["sha256"]:
        raise ValueError("STAGE_A_LAB_SOURCE_HASH_CHANGED")
    return data


def sandbox_setup(path: Path) -> Path:
    path = Path(path)
    if not path.is_absolute() or path.exists() or path.is_symlink():
        raise ValueError("STAGE_A_LAB_ALREADY_EXISTS_OR_NONCANONICAL")
    temporary = Path(tempfile.gettempdir()).resolve()
    if temporary not in path.parents or path.parent.resolve(strict=True) != path.parent:
        raise ValueError("STAGE_A_LAB_OUTSIDE_TEMP")
    path.mkdir(mode=0o700)
    (path / LAB_MARKER).write_text("stage-a-temporary-test-only")
    return _sandbox(path)


def stage(repo: Path, root: Path, scope: dict[str, Any],
          *, stop_after_files: int | None = None,
          root_metadata: bool = False) -> dict[str, Any]:
    root = _sandbox(root)
    if root_metadata and os.geteuid() != 0:
        raise PermissionError("STAGE_A_LAB_REAL_ROOT_METADATA_REQUIRED")
    if scope != packet.build_scope(repo, scope["candidate_sha"]):
        raise ValueError("STAGE_A_LAB_SCOPE_DRIFT")
    for directory in scope["directories"]:
        p = _mapped(root, directory["path"])
        if p.exists() or p.is_symlink():
            raise ValueError("STAGE_A_LAB_PREEXISTING_TARGET")
    for row in scope["files"]:
        p = _mapped(root, row["path"])
        if p.exists() or p.is_symlink():
            raise ValueError("STAGE_A_LAB_PREEXISTING_TARGET")
    if _mapped(root, packet.CURRENT).exists() or _mapped(root, packet.CURRENT).is_symlink():
        raise ValueError("STAGE_A_LAB_PREEXISTING_CURRENT")
    for directory in scope["directories"]:
        p = _mapped(root, directory["path"])
        p.mkdir(parents=True, exist_ok=False)
        if root_metadata:
            os.chown(p, directory["uid"], directory["gid"])
        p.chmod(int(directory["mode"], 8))
    count = 0
    for row in scope["files"]:
        p = _mapped(root, row["path"])
        data = _expected_file_data(repo, row)
        with p.open("xb") as file:
            file.write(data)
        if root_metadata:
            os.chown(p, row["uid"], row["gid"])
        p.chmod(int(row["mode"], 8))
        count += 1
        if stop_after_files is not None and count == stop_after_files:
            raise InterruptedError("STAGE_A_LAB_SYNTHETIC_INTERRUPTION")
    _mapped(root, packet.CURRENT).symlink_to(packet.CURRENT_TARGET)
    verify(repo, root, scope, root_metadata=root_metadata)
    return {"status": "lab_installed_verified", "source_sha": scope["candidate_sha"],
            "file_count": count, "source_only": True, "production_mutation": False,
            "root_metadata_checked": root_metadata}


def verify(repo: Path, root: Path, scope: dict[str, Any],
           *, allow_partial: bool = False,
           root_metadata: bool = False) -> dict[str, Any]:
    root = _sandbox(root)
    if root_metadata and os.geteuid() != 0:
        raise PermissionError("STAGE_A_LAB_REAL_ROOT_METADATA_REQUIRED")
    expected = set()
    found = set()
    for directory in scope["directories"]:
        p = _mapped(root, directory["path"])
        expected.add(p)
        if p.exists():
            meta = p.lstat()
            if (p.is_symlink() or not p.is_dir()
                    or stat.S_IMODE(meta.st_mode) != int(directory["mode"], 8)
                    or (root_metadata and (meta.st_uid, meta.st_gid)
                        != (directory["uid"], directory["gid"]))):
                raise ValueError("STAGE_A_LAB_DIRECTORY_DRIFT")
        elif not allow_partial:
            raise ValueError("STAGE_A_LAB_DIRECTORY_MISSING")
    for row in scope["files"]:
        p = _mapped(root, row["path"])
        expected.add(p)
        if p.exists():
            meta = p.lstat()
            if (p.is_symlink() or not p.is_file()
                    or stat.S_IMODE(meta.st_mode) != int(row["mode"], 8)
                    or (root_metadata and (meta.st_uid, meta.st_gid)
                        != (row["uid"], row["gid"]))
                    or packet._digest(p.read_bytes()) != row["sha256"]):
                raise ValueError("STAGE_A_LAB_FILE_TAMPERED")
        elif not allow_partial:
            raise ValueError("STAGE_A_LAB_FILE_MISSING")
    target = _mapped(root, packet.CURRENT)
    expected.add(target)
    if target.is_symlink():
        if os.readlink(target) != packet.CURRENT_TARGET:
            raise ValueError("STAGE_A_LAB_POINTER_TAMPERED")
    elif target.exists() or not allow_partial:
        raise ValueError("STAGE_A_LAB_CURRENT_MISSING")
    for prefix in (packet.ROOT, packet.HOST_CODE, packet.ETC):
        base = _mapped(root, prefix)
        if base.exists():
            found.add(base)
            found.update(base.rglob("*"))
    if found - expected:
        raise ValueError("STAGE_A_LAB_UNDECLARED_OBJECT")
    # No trust/signer, legacy source, provider keys or alternate control
    # planes may appear anywhere in this accepted file inventory.
    return {"status": "verified", "files": len(scope["files"]),
            "directories": len(scope["directories"]), "source_only": True}


def rollback(repo: Path, root: Path, scope: dict[str, Any],
             *, allow_partial: bool = False,
             root_metadata: bool = False) -> dict[str, Any]:
    # Verify the ENTIRE target inventory before deleting even one inode.
    # A foreign file, new symlink or changed hash causes fail-closed refusal.
    verify(repo, root, scope, allow_partial=allow_partial,
           root_metadata=root_metadata)
    current = _mapped(root, packet.CURRENT)
    if current.is_symlink():
        current.unlink()
    for row in scope["files"]:
        p = _mapped(root, row["path"])
        if p.is_file():
            p.chmod(0o600)
            p.unlink()
    for directory in sorted(scope["directories"],
                            key=lambda item: len(Path(item["path"]).parts),
                            reverse=True):
        p = _mapped(root, directory["path"])
        if p.exists():
            p.chmod(0o700)
            p.rmdir()
    for prefix in (packet.ROOT, packet.HOST_CODE, packet.ETC):
        p = _mapped(root, prefix)
        if p.exists() or p.is_symlink():
            raise ValueError("STAGE_A_LAB_EMPTY_BASELINE_NOT_RESTORED")
    return {"status": "empty_baseline_restored",
            "rollback_sha": packet.EMPTY_BASELINE, "source_only": True,
            "production_mutation": False}
