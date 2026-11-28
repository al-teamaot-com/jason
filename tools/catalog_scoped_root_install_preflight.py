#!/usr/bin/env python3
"""Read-only exact catalog root installer preflight; NEVER installs root files.

This tool is only preparatory evidence for a separately authenticated Owner-
approved root install. It cannot deploy, restart, unfreeze, grant privileges,
consume an Owner proof, or create a production-eligible release.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any, Callable, Mapping

from tools.catalog_scoped_promotion_bundle import FILES
from implementation.kernel.signed_owner_release import read_pinned_root_owner_public_key

SHA = re.compile(r"^[0-9a-f]{40}$")
HEX = re.compile(r"^[0-9a-f]{64}$")
ROOT_WORKER = Path("/usr/local/lib/jason/release_host_reconcile_worker.py")
ROOT_BUNDLE = Path("/usr/local/lib/jason/catalog-scoped-promotion")
OWNER_PIN = Path("/etc/jason-owner-release/verified-owner-public-key.json")
FREEZE = Path("/var/lib/jason/openclaw/release-manager/production-deployment-freeze")
HOST_STATE = Path("/var/lib/jason/openclaw/release-manager")
ROOT_POLICY = Path("/etc/jason-owner-release/catalog-scoped-promotion-installed.json")
AUTH_DIRECTORY = Path("/var/lib/jason/authority/catalog-scoped-release")
SYSTEMD = Path("/etc/systemd/system")
EXACT_FILE_SET = frozenset(FILES)
REQUIRED_FILE_COUNT = 17
EXPECTED_FREEZE = "bdae4fdb8749fe2c595817896c7adeab0800bef0e0436897c97ec847b47d197f"
SCOPED_ACTION = "catalog-scoped-root-installer-readonly-plan-v1"


class CatalogRootPreflightDenied(PermissionError):
    """Fail closed without altering the host."""


def _fail(code: str) -> None:
    raise CatalogRootPreflightDenied("CATALOG_ROOT_PREFLIGHT_" + code)


def _sha(value: Any, kind: str, pattern: re.Pattern = HEX) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        _fail(kind + "_INVALID")
    return value


def _canonical(data: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(data), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _private_file(path: Path, *, expected_owner: int | None = None,
                  mode: int | None = None, max_bytes: int = 100_000) -> bytes:
    if path.is_symlink() or not path.is_file():
        _fail("FILE_MISSING_OR_SYMLINK")
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_mode & 0o022 or not 1 <= info.st_size <= max_bytes
            or (expected_owner is not None and info.st_uid != expected_owner)
            or (mode is not None and stat.S_IMODE(info.st_mode) != mode)):
        _fail("FILE_UNTRUSTED")
    data = path.read_bytes()
    if len(data) != info.st_size:
        _fail("FILE_CHANGED_DURING_READ")
    return data


def _git(repo: Path, *args: str) -> bytes:
    done = subprocess.run(
        ["git", "-c", f"safe.directory={repo}", "-C", str(repo), *args],
        capture_output=True, check=False, timeout=45,
    )
    if done.returncode:
        _fail("GIT_EVIDENCE_MISSING")
    return done.stdout


def _target_for(relative: str) -> Path:
    if relative == "tools/release_host_reconcile_worker.py":
        return ROOT_WORKER
    if relative.startswith("infrastructure/openclaw-operations/systemd/"):
        return SYSTEMD / relative.rsplit("/", 1)[-1]
    return ROOT_BUNDLE / relative


def inspect_staged_exact_bundle(
    stage: Path, *, expected_source_sha: str, expected_bundle_sha256: str,
    committed_blob: Callable[[str], bytes],
) -> dict[str, Any]:
    """Independently compare every staged byte against the protected Git blob."""
    _sha(expected_source_sha, "SOURCE_SHA", SHA)
    _sha(expected_bundle_sha256, "BUNDLE_DIGEST")
    if stage.is_symlink() or not stage.is_dir():
        _fail("STAGE_MISSING_OR_SYMLINK")
    mode = stage.lstat()
    if mode.st_uid != os.getuid() or stat.S_IMODE(mode.st_mode) != 0o700:
        _fail("STAGE_OWNER_OR_MODE")
    raw = _private_file(stage / "SOURCE_ONLY_MANIFEST.json",
                        expected_owner=os.getuid(), mode=0o600)
    try:
        manifest = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise CatalogRootPreflightDenied("CATALOG_ROOT_PREFLIGHT_MANIFEST_JSON") from exc
    if (not isinstance(manifest, dict)
            or set(manifest) != {
                "schema_version", "status", "source_sha", "files",
                "release_approval_recorded", "production_mutations",
                "root_installation_authorized", "bundle_sha256"
            }
            or manifest["schema_version"] != "1.0"
            or manifest["status"] != "source_only_not_installed"
            or manifest["source_sha"] != expected_source_sha
            or manifest["release_approval_recorded"] is not False
            or manifest["production_mutations"] is not False
            or manifest["root_installation_authorized"] is not False
            or manifest["bundle_sha256"] != expected_bundle_sha256):
        _fail("MANIFEST_CONTRACT_CHANGED")
    content = dict(manifest)
    content.pop("bundle_sha256")
    if sha256(_canonical(content)).hexdigest() != expected_bundle_sha256:
        _fail("MANIFEST_DIGEST_MISMATCH")
    files = manifest["files"]
    if not isinstance(files, dict) or set(files) != EXACT_FILE_SET:
        _fail("STAGED_SOURCE_SCOPE_INVALID")
    if len(files) != REQUIRED_FILE_COUNT:
        _fail("STAGED_FILE_COUNT")
    target_paths: set[str] = set()
    targets = []
    for relative in sorted(EXACT_FILE_SET):
        entry = files[relative]
        if (not isinstance(entry, dict) or set(entry) != {"sha256", "bytes"}
                or not isinstance(entry["bytes"], int)
                or not 1 <= entry["bytes"] <= 500_000):
            _fail("STAGED_FILE_ENTRY_INVALID")
        _sha(entry["sha256"], "FILE_DIGEST")
        child = stage / relative
        raw_file = _private_file(child, expected_owner=os.getuid(), max_bytes=500_000)
        if (len(raw_file) != entry["bytes"]
                or sha256(raw_file).hexdigest() != entry["sha256"]
                or raw_file != committed_blob(relative)):
            _fail("STAGED_FILE_OR_GIT_BLOB_CHANGED")
        destination = str(_target_for(relative))
        if destination in target_paths:
            _fail("DUPLICATE_ROOT_DESTINATION")
        target_paths.add(destination)
        targets.append({
            "source_relative": relative,
            "root_target": destination,
            "sha256": entry["sha256"],
            "bytes": len(raw_file),
        })
    return {
        "schema_version": "1.0",
        "source_sha": expected_source_sha,
        "source_only_bundle_sha256": expected_bundle_sha256,
        "file_count": REQUIRED_FILE_COUNT,
        "targets": targets,
        "installer_not_present": True,
    }


def preflight_live(
    *, repo: Path, stage: Path, expected_source_sha: str,
    expected_bundle_sha256: str, old_worker_sha256: str,
) -> dict[str, Any]:
    """Host observations only: no writes and no mutable approval input."""
    _sha(old_worker_sha256, "ROLLBACK_WORKER_DIGEST")
    repo = repo.resolve()
    if repo.is_symlink() or not repo.is_dir():
        _fail("REPOSITORY_INVALID")
    remote = _git(repo, "ls-remote", "origin", "refs/heads/main").decode().split()
    if remote != [expected_source_sha, "refs/heads/main"]:
        _fail("PROTECTED_MAIN_CHANGED")
    local = _git(repo, "rev-parse", "refs/remotes/origin/main").decode().strip()
    if local != expected_source_sha:
        _fail("LOCAL_PROTECTED_REF_STALE")
    origin = _git(repo, "remote", "get-url", "origin").decode().strip()
    if origin not in (
        "https://github.com/al-teamaot-com/jason.git",
        "https://github.com/al-teamaot-com/jason",
        "git@github.com:al-teamaot-com/jason.git",
    ):
        _fail("GITHUB_ORIGIN_MISMATCH")
    plan = inspect_staged_exact_bundle(
        stage, expected_source_sha=expected_source_sha,
        expected_bundle_sha256=expected_bundle_sha256,
        committed_blob=lambda relative: _git(repo, "show",
                                             f"{expected_source_sha}:{relative}"),
    )
    worker = _private_file(ROOT_WORKER, expected_owner=0, max_bytes=200_000)
    if sha256(worker).hexdigest() != old_worker_sha256:
        _fail("ROLLBACK_WORKER_CHANGED")
    state = HOST_STATE.lstat()
    if (HOST_STATE.is_symlink() or not stat.S_ISDIR(state.st_mode)
            or stat.S_IMODE(state.st_mode) != 0o700):
        _fail("RELEASE_STATE_UNTRUSTED")
    freeze = _private_file(FREEZE, expected_owner=state.st_uid, mode=0o600,
                          max_bytes=4096)
    freeze_sha = sha256(freeze).hexdigest()
    if freeze_sha != EXPECTED_FREEZE:
        _fail("PRODUCTION_FREEZE_CHANGED")
    try:
        frozen = json.loads(freeze)
    except ValueError as exc:
        raise CatalogRootPreflightDenied("CATALOG_ROOT_PREFLIGHT_FREEZE_UNPARSEABLE") from exc
    if (frozen.get("status") != "active"
            or frozen.get("scope") != "manual-and-automatic-production-promotions"):
        _fail("FREEZE_NOT_ACTIVE")
    read_pinned_root_owner_public_key(OWNER_PIN)
    if ROOT_POLICY.exists() or ROOT_BUNDLE.exists() or AUTH_DIRECTORY.exists():
        _fail("ROOT_CATALOG_ALREADY_PRESENT")
    for name in ("jason-catalog-scoped-recovery.service",
                 "jason-catalog-scoped-recovery.timer"):
        if (SYSTEMD / name).exists():
            _fail("ROOT_TIMER_ALREADY_PRESENT")
    base = {
        "schema_version": "1.0",
        "action": SCOPED_ACTION,
        "source_sha": expected_source_sha,
        "rollback_source_sha": "d1b8c196dadd4b672ec8ba47075f27bb61c98d63",
        "file_bundle_sha256": expected_bundle_sha256,
        "old_root_worker_sha256": old_worker_sha256,
        "original_freeze_sha256": freeze_sha,
        "target_entries": plan["targets"],
        "no_broad_main_runtime_change": True,
        "automatic_rollback_watchdog_required": True,
        "authenticated_owner_exact_action_required": True,
        "root_installation_authorized": False,
        "production_mutations": False,
    }
    return {
        "status": "ROOT_INSTALL_PREFLIGHT_ONLY_NOT_APPROVED",
        "root_installation_authorized": False,
        "production_mutations": False,
        "source_sha": expected_source_sha,
        "staged_file_count": plan["file_count"],
        "source_bundle_sha256": expected_bundle_sha256,
        "prior_root_worker_sha256": old_worker_sha256,
        "freeze_sha256": freeze_sha,
        "root_install_manifest_sha256": sha256(_canonical(base)).hexdigest(),
        "requested_installer_action": SCOPED_ACTION,
        "owner_signed_release_proof_required": True,
        "rollback_verification_required": True,
        "root_staging_targets": plan["targets"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--bundle-sha256", required=True)
    parser.add_argument("--old-worker-sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(preflight_live(
        repo=args.repo, stage=args.stage,
        expected_source_sha=args.source_sha,
        expected_bundle_sha256=args.bundle_sha256,
        old_worker_sha256=args.old_worker_sha256,
    ), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
