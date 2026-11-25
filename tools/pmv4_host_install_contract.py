#!/usr/bin/env python3
"""Trusted PMv4 host installation contract and offline staging/inspection.

This module deliberately has NO production install/enable/update operation.
Only the separately authenticated native root release manager may install
a reviewed exact immutable bundle, provision signer/trust and transition
protected desired state. A source worktree or ChatGPT command cannot serve
as release authority. Preproduction staging is confined to an isolated path.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any

from tools.pmv4_host_release_guard import IndependentHostGuard
from tools.pmv4_shadow_release import PRODUCTION_ROOT, TRUST_PATH

BUNDLE_FILES = (
    "tools/pmv4_shadow_host_runtime.py",
    "tools/pmv4_shadow_release.py",
    "tools/pmv4_host_release_guard.py",
    "tools/pmv4_shadow_docker_adapter.py",
    "tools/pmv4_shadow_ci.py",
    "implementation/kernel/__init__.py",
    "implementation/kernel/signed_owner_release.py",
)
HOST_CODE = Path("/usr/local/lib/jason/pmv4-trusted")
AUDIENCE = Path("/etc/jason/pmv4-shadow/entra-audience.json")
SIGNER = Path("/var/lib/jason/runtime-secrets/owner-release/private_key")
HOST_LOCK = PRODUCTION_ROOT / "control/host-mutation.lock"
HOST_INSTALL_REQUIREMENTS = {
    str(PRODUCTION_ROOT): ("directory", 0, True),
    str(PRODUCTION_ROOT / "control"): ("directory", 0, True),
    str(PRODUCTION_ROOT / "releases"): ("directory", 0, True),
    str(PRODUCTION_ROOT / "receipts"): ("directory", 0, True),
    str(PRODUCTION_ROOT / "control/signed-owner-decisions"): ("directory", 0, True),
    str(HOST_LOCK): ("file", 0, True),
    str(TRUST_PATH): ("file", 0, True),
    str(AUDIENCE): ("file", 0, True),
    str(SIGNER): ("file", 1000, True),  # existing service-owned signer, not duplicated
}


def reviewed_code_manifest(repo: Path) -> dict[str, Any]:
    """Hash all and only the trusted, non-secret source modules."""
    files = []
    for relative in BUNDLE_FILES:
        file = repo / relative
        if file.is_symlink() or not file.is_file():
            raise ValueError("PMV4_INSTALL_SOURCE_MISSING_OR_SYMLINK")
        files.append({"path": relative, "sha256": sha256(file.read_bytes()).hexdigest()})
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return {"schema_version": "1.0", "component": "pmv4-host-release",
            "files": files, "bundle_sha256": sha256(canonical).hexdigest(),
            "production_install_authorized": False}


def _nonproduction_stage_root(target: Path, *, allow_existing: bool = False) -> Path:
    target = Path(target)
    if not target.is_absolute() or ".." in target.parts:
        raise ValueError("PMV4_STAGE_PATH_UNTRUSTED")
    if target == PRODUCTION_ROOT or PRODUCTION_ROOT in target.parents:
        raise ValueError("PMV4_STAGE_PRODUCTION_TARGET_DENIED")
    if target == HOST_CODE or HOST_CODE in target.parents:
        raise ValueError("PMV4_STAGE_TRUSTED_CODE_TARGET_DENIED")
    if target == Path("/etc") or Path("/etc") in target.parents:
        raise ValueError("PMV4_STAGE_SYSTEM_POLICY_TARGET_DENIED")
    # Only staging in a fresh operator-owned temporary work directory.
    permitted = Path(tempfile.gettempdir()).resolve()
    try:
        resolved_parent = target.parent.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError("PMV4_STAGE_UNTRUSTED_PARENT") from exc
    if (permitted not in target.parents or resolved_parent != target.parent
            or (resolved_parent != permitted and
                permitted not in resolved_parent.parents)):
        raise ValueError("PMV4_STAGE_OUTSIDE_TEMP_DENIED")
    if target.is_symlink() or (target.exists() and not allow_existing):
        raise ValueError("PMV4_STAGE_EXISTING_TARGET_DENIED")
    return target


def stage_lab_bundle(repo: Path, target: Path) -> dict[str, Any]:
    """Stage a non-executable synthetic host bundle for hash/rollback tests."""
    target = _nonproduction_stage_root(target)
    manifest = reviewed_code_manifest(repo)
    target.mkdir(mode=0o700)
    for entry in manifest["files"]:
        source = repo / entry["path"]
        dest = target / entry["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest, follow_symlinks=False)
        os.chmod(dest, 0o400)
    report = verify_lab_bundle(target, manifest)
    return {**report, "production_install_authorized": False,
            "lab_target": str(target)}


def verify_lab_bundle(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("component") != "pmv4-host-release" or manifest.get(
        "production_install_authorized"
    ) is not False:
        raise ValueError("PMV4_INSTALL_MANIFEST_UNTRUSTED")
    allowed = set(BUNDLE_FILES)
    actual = set()
    for p in path.rglob("*"):
        if p.is_symlink():
            raise ValueError("PMV4_INSTALL_SYMLINK_IN_BUNDLE")
        if p.is_file():
            actual.add(p.relative_to(path).as_posix())
            if stat.S_IMODE(p.stat().st_mode) != 0o400:
                raise ValueError("PMV4_INSTALL_CODE_MODE_DRIFT")
    if actual != allowed or {x.get("path") for x in manifest.get("files", [])} != allowed:
        raise ValueError("PMV4_INSTALL_FILE_SCOPE_DRIFT")
    for entry in manifest["files"]:
        if sha256((path / entry["path"]).read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError("PMV4_INSTALL_CODE_HASH_DRIFT")
    return {"status": "lab_bundle_verified",
            "file_count": len(allowed),
            "bundle_sha256": manifest["bundle_sha256"],
            "production_installed": False}


def rollback_lab_bundle(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Prove initial empty-baseline rollback without deleting foreign files."""
    path = _nonproduction_stage_root(path, allow_existing=True)
    if path.is_symlink() or not path.is_dir():
        raise ValueError("PMV4_LAB_ROLLBACK_TARGET_INVALID")
    verify_lab_bundle(path, manifest)  # hash, scope and modes before removal
    for relative in BUNDLE_FILES:
        (path / relative).unlink()
    # rmdir fails closed if any foreign file appeared during the operation.
    for directory in sorted(
        (p for p in path.rglob("*") if p.is_dir()),
        key=lambda p: len(p.parts), reverse=True,
    ):
        directory.rmdir()
    path.rmdir()
    if path.exists():
        raise ValueError("PMV4_LAB_ROLLBACK_READBACK_FAILED")
    return {
        "status": "empty_baseline_restored",
        "baseline_sha": "0" * 40,
        "production_mutation": False,
        "production_installed": False,
    }


def inspect_live() -> dict[str, Any]:
    """Read-only evidence; never infer trust from a missing protected file."""
    details = {}
    for name, (kind, expected_uid, no_group_write) in HOST_INSTALL_REQUIREMENTS.items():
        p = Path(name)
        try:
            meta = p.lstat()
            valid = (
                not p.is_symlink()
                and (stat.S_ISREG(meta.st_mode) if kind == "file"
                     else stat.S_ISDIR(meta.st_mode))
                and (expected_uid < 0 or meta.st_uid == expected_uid)
                and (not no_group_write or not (meta.st_mode & 0o022))
            )
            if p == SIGNER:
                # Never read/expose the private key. Service-specific owner
                # must be independently verified at install time.
                valid = valid and stat.S_IMODE(meta.st_mode) == 0o400
            if p == HOST_LOCK:
                valid = valid and stat.S_IMODE(meta.st_mode) == 0o600
            details[name] = "present_metadata_valid" if valid else "untrusted"
        except (OSError, PermissionError):
            details[name] = "absent_or_unreadable"
    try:
        core = IndependentHostGuard().core_health_evidence()
    except (OSError, PermissionError, ValueError) as exc:
        core = {"status": "unavailable", "reason": type(exc).__name__}
    guard = IndependentHostGuard()
    return {
        "status": "inspection_only",
        "production_mutation": False, "production_install_authorized": False,
        "host_items": details, "core_health": core,
        "release_gate": guard.protected_release_status(),
        "cross_release_lock_ready": guard.host_mutation_quiescent(),
        "installation_complete": False if not all(
            x == "present_metadata_valid" for x in details.values()
        ) else None,  # require signed readback beyond metadata before PASS
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--plan", action="store_true")
    p.add_argument("--inspect-live", action="store_true")
    p.add_argument("--lab-stage", type=Path)
    p.add_argument("--lab-rollback", type=Path)
    args = p.parse_args()
    repo = Path(__file__).resolve().parents[1]
    if sum(bool(x) for x in (
        args.plan, args.inspect_live, args.lab_stage, args.lab_rollback,
    )) != 1:
        p.error("choose exactly one inspection/lab operation")
    if args.plan:
        result = reviewed_code_manifest(repo)
    elif args.inspect_live:
        result = inspect_live()
    elif args.lab_stage:
        result = stage_lab_bundle(repo, args.lab_stage)
    else:
        result = rollback_lab_bundle(args.lab_rollback, reviewed_code_manifest(repo))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
