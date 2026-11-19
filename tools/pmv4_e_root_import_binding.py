#!/usr/bin/env python3
"""Read-only import boundary for original native root + reviewed Stage E code.

Never load a COPY of the generic controller from Stage E's staged source:
its constructor is deliberately bound to the preexisting immutable
/opt/jason/independent-component-release/trusted/tools source path.

The installed UID0 Stage E entrypoint calls this once before importing any
tools/implementation package. No approval, root write, sysadmin service,
credential or provider action is created by this module.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import re
import stat
import sys
import types
from typing import Any, Mapping

NATIVE = Path("/opt/jason/independent-component-release/trusted")
STAGE_E = Path("/opt/jason/pmv4-e-trusted")
ENTRY = STAGE_E / "tools/pmv4_e_root_import_binding.py"
NATIVE_FILES = (
    "tools/independent_component_release.py",
    "tools/independent_component_host_adapter.py",
    "tools/independent_component_release_root.py",
    "implementation/kernel/signed_owner_release.py",
)
STAGE_FILES = (
    "tools/pmv4_e_signed_native_ledger.py",
    "tools/pmv4_e_root_import_binding.py",
    "tools/pmv4_e_native_root_manifest_attestation.py",
    "tools/pmv4_e_native_release_contract.py",
    "tools/pmv4_e_native_systemd_adapter.py",
    "tools/pmv4_e_systemd_root_ops.py",
    "tools/pmv4_e_native_backend_bridge.py",
    "tools/pmv4_e_exact_release_packet.py",
)
DIGEST = re.compile(r"^[0-9a-f]{64}$")
PACKAGES = ("tools", "implementation", "implementation.kernel")


class StageERootImportDenied(PermissionError):
    pass


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise StageERootImportDenied("PMV4_E_ROOT_IMPORT_" + reason)


def _checked_dir(path: Path, *, production: bool) -> None:
    try:
        info = path.lstat()
        need(not path.is_symlink() and stat.S_ISDIR(info.st_mode)
             and info.st_mode & 0o022 == 0,
             "DIRECTORY_MUTABLE_OR_UNTRUSTED")
        if production:
            need(info.st_uid == 0 and info.st_gid == 0,
                 "DIRECTORY_NOT_ROOT")
    except StageERootImportDenied:
        raise
    except OSError as exc:
        raise StageERootImportDenied(
            "PMV4_E_ROOT_IMPORT_DIRECTORY_UNAVAILABLE") from exc


def _checked_file(path: Path, *, production: bool,
                  expected_sha: str) -> None:
    need(type(expected_sha) is str and
         DIGEST.fullmatch(expected_sha) is not None,
         "EXPECTED_DIGEST_INVALID")
    try:
        info = path.lstat()
        need(not path.is_symlink() and stat.S_ISREG(info.st_mode)
             and info.st_nlink == 1 and info.st_size > 0
             and info.st_size < 1_000_000 and
             info.st_mode & 0o022 == 0,
             "NATIVE_FILE_MUTABLE_OR_UNTRUSTED")
        if production:
            need(info.st_uid == 0 and info.st_gid == 0
                 and stat.S_IMODE(info.st_mode) == 0o444,
                 "NATIVE_FILE_NOT_IMMUTABLE")
        need(sha256(path.read_bytes()).hexdigest() == expected_sha,
             "NATIVE_FILE_BYTES_CHANGED")
    except StageERootImportDenied:
        raise
    except OSError as exc:
        raise StageERootImportDenied(
            "PMV4_E_ROOT_IMPORT_NATIVE_FILE_UNAVAILABLE") from exc


def prepare(*, native_root: Path, stage_root: Path,
            approved_hashes: Mapping[str, str],
            production: bool = True) -> dict[str, Any]:
    """Bind native package search to original root first, staged PMv4 second.

    Approval data must originate in the previously root-attested exact
    manifest. This method itself does not issue or verify an Owner signature.
    """
    native_root, stage_root = Path(native_root), Path(stage_root)
    if production:
        here = Path(__file__)
        info = here.lstat()
        need(os.geteuid() == 0 and here == ENTRY
             and here.resolve() == ENTRY and not here.is_symlink()
             and info.st_uid == 0 and info.st_gid == 0
             and stat.S_IMODE(info.st_mode) == 0o444
             and native_root == NATIVE and stage_root == STAGE_E,
             "CANONICAL_ROOT_INSTALLED_REQUIRED")
    need(isinstance(approved_hashes, Mapping) and
         all(type(k) is str and type(v) is str
             for k, v in approved_hashes.items()),
         "HASH_BINDING_NOT_A_MAP")
    for base in (native_root, stage_root):
        _checked_dir(base, production=production)
        _checked_dir(base / "tools", production=production)
        _checked_dir(base / "implementation", production=production)
        _checked_dir(base / "implementation/kernel",
                     production=production)
    for name in NATIVE_FILES:
        need(name in approved_hashes, "NATIVE_SOURCE_HASH_NOT_REVIEWED")
        _checked_file(native_root / name, production=production,
                      expected_sha=approved_hashes[name])
    for name in STAGE_FILES:
        need(name in approved_hashes, "STAGE_SOURCE_HASH_NOT_REVIEWED")
        _checked_file(stage_root / name, production=production,
                      expected_sha=approved_hashes[name])
    for name in PACKAGES:
        # Python's existing module cache must never override our deliberately
        # constructed root module search path, including submodules.
        need(name not in sys.modules and
             not any(k.startswith(name + ".") for k in sys.modules),
             "PREEXISTING_MODULE_NAMESPACE")
    for name in PACKAGES:
        parts = name.split(".")
        original = native_root.joinpath(*parts)
        stage = stage_root.joinpath(*parts)
        pkg = types.ModuleType(name)
        pkg.__package__ = name
        pkg.__path__ = [str(original), str(stage)]
        pkg.__spec__ = None
        sys.modules[name] = pkg
        if "." in name:
            parent = sys.modules[name.rsplit(".", 1)[0]]
            setattr(parent, name.rsplit(".", 1)[1], pkg)
    return {
        "status": "original_native_module_first_and_stage_e_import_bound",
        "native_root": str(native_root),
        "stage_root": str(stage_root),
        "original_native_module_verified": True,
        "original_signer_verified": True,
        "source_bytes_verified": len(NATIVE_FILES) + len(STAGE_FILES),
        "release_authorized": False,
        "root_actions": False,
        "owner_approval_issued": False,
    }
