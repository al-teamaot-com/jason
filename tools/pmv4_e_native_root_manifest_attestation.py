#!/usr/bin/env python3
"""Root-owned, read-only attestation of one exact typed Stage E manifest.

Source-only until an independently authorized installer seals this file at
/opt/jason/pmv4-e-trusted/tools/. No Owner proof, release authority or
systemd action is created here. Never trust a caller's JSON as signed scope.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import stat
from typing import Any

from tools import pmv4_e_native_release_contract as contract
from tools import pmv4_e_exact_release_packet as packet

TRUST_ROOT = Path("/opt/jason/pmv4-e-trusted")
INSTALLED = TRUST_ROOT / "tools/pmv4_e_native_root_manifest_attestation.py"
RELEASE_ROOT = Path("/var/lib/jason/independent-component-release/releases")


class StageERootAttestationDenied(PermissionError):
    pass


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise StageERootAttestationDenied("PMV4_E_ROOT_ATTEST_" + reason)


def _regular(path: Path, *, production: bool) -> bytes:
    try:
        x = path.lstat()
        need(not path.is_symlink() and stat.S_ISREG(x.st_mode)
             and x.st_nlink == 1 and 0 < x.st_size < 1024 * 1024
             and x.st_mode & 0o022 == 0,
             "ROOT_FILE_UNTRUSTED")
        if production:
            need(x.st_uid == 0 and x.st_gid == 0
                 and stat.S_IMODE(x.st_mode) == 0o444,
                 "ROOT_FILE_NOT_IMMUTABLE")
        raw = path.read_bytes()
        need(len(raw) == x.st_size, "FILE_CHANGED_DURING_READ")
        return raw
    except StageERootAttestationDenied:
        raise
    except OSError as exc:
        raise StageERootAttestationDenied(
            "PMV4_E_ROOT_ATTEST_FILE_NOT_READABLE") from exc


def _directory(path: Path, *, production: bool) -> None:
    try:
        x = path.lstat()
        need(stat.S_ISDIR(x.st_mode) and not path.is_symlink()
             and x.st_mode & 0o022 == 0, "ROOT_DIRECTORY_UNTRUSTED")
        if production:
            need(x.st_uid == 0 and x.st_gid == 0
                 and stat.S_IMODE(x.st_mode) == 0o555,
                 "ROOT_DIRECTORY_NOT_IMMUTABLE")
    except StageERootAttestationDenied:
        raise
    except OSError as exc:
        raise StageERootAttestationDenied(
            "PMV4_E_ROOT_ATTEST_DIRECTORY_NOT_READABLE") from exc


def inspect(*, source_root: Path = TRUST_ROOT,
            release_dir: Path,
            production: bool = True) -> dict[str, Any]:
    """Attest exact sealed file inventory, source scope and native release mode.

    This is only a source-integrity prerequisite; even success does not mean
    protected root policy, C/D/A1, breaker, freeze, signed Owner or host locks
    have passed. The caller must independently enforce those release gates.
    """
    source_root = Path(source_root)
    release_dir = Path(release_dir)
    if production:
        need(os.geteuid() == 0
             and source_root == TRUST_ROOT
             and Path(__file__).resolve() == INSTALLED
             and not Path(__file__).is_symlink(),
             "CANONICAL_PRIVILEGED_INSTALL_REQUIRED")
        need(release_dir.parent == RELEASE_ROOT
             and release_dir.name.isascii()
             and len(release_dir.name) == 40
             and all(c in "0123456789abcdef" for c in release_dir.name),
             "RELEASE_DIRECTORY_OUT_OF_SCOPE")
    _directory(source_root, production=production)
    _directory(release_dir, production=production)
    for parent in (source_root / "tools", source_root / "config",
                   source_root / "infrastructure"):
        _directory(parent, production=production)
    source_paths: set[str] = set()
    for path in source_root.rglob("*"):
        relative = path.relative_to(source_root).as_posix()
        if path.is_symlink():
            raise StageERootAttestationDenied(
                "PMV4_E_ROOT_ATTEST_SOURCE_SYMLINK_DENIED")
        if path.is_dir():
            _directory(path, production=production)
        elif path.is_file():
            _regular(path, production=production)
            source_paths.add(relative)
        else:
            raise StageERootAttestationDenied(
                "PMV4_E_ROOT_ATTEST_SOURCE_OBJECT_UNREVIEWED")
    need(source_paths == set(packet.REVIEWED_PATHS),
         "SOURCE_INVENTORY_NOT_EXACT")
    manifest_file = release_dir / "manifest.json"
    scope_file = release_dir / "source-scope.json"
    need(set(path.name for path in release_dir.iterdir())
         == {"manifest.json", "source-scope.json"},
         "RELEASE_RECORD_INVENTORY_NOT_EXACT")
    try:
        manifest = json.loads(_regular(manifest_file, production=production))
        scope = json.loads(_regular(scope_file, production=production))
    except (ValueError, TypeError) as exc:
        raise StageERootAttestationDenied(
            "PMV4_E_ROOT_ATTEST_JSON_INVALID") from exc
    need(type(manifest) is dict and type(scope) is dict,
         "JSON_OBJECT_REQUIRED")
    if production:
        need(manifest.get("candidate_sha") == release_dir.name,
             "RELEASE_DIRECTORY_SHA_MISMATCH")
    need(type(scope.get("exact_replacement_files_sha256")) is dict,
         "SOURCE_HASH_MAP_INVALID")
    for rel in packet.REVIEWED_PATHS:
        actual = sha256(_regular(source_root / rel,
                                 production=production)).hexdigest()
        need(scope.get("exact_replacement_files_sha256", {}).get(rel)
             == actual,
             "SOURCE_FILE_BYTES_CHANGED")
    try:
        record = contract.validate(
            manifest, scope, source_root=source_root,
        )
    except (contract.StageEManifestDenied, packet.StageEReleasePacketDenied,
            ValueError, TypeError) as exc:
        raise StageERootAttestationDenied(
            "PMV4_E_ROOT_ATTEST_EXACT_SOURCE_SCOPE_INVALID") from exc
    return {
        "status": "root_source_attested_no_release_authority",
        "candidate_sha": record["candidate_sha"],
        "rollback_sha": record["rollback_sha"],
        "scope_sha256": record["scope_sha256"],
        "manifest_sha256": record["manifest_sha256"],
        "file_count": record["source_files_verified"],
        "source_sha256": sha256(packet.canonical(
            scope["exact_replacement_files_sha256"])).hexdigest(),
        "production_mutations": False,
        "release_authorized": False,
        "owner_proof_issued": False,
        "root_preflight_complete": False,
    }
