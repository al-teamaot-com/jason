#!/usr/bin/env python3
"""Produce exact read-only root-install evidence for catalog runtime/MCP.

NOT a privileged installer, signer or an authorization. No --apply operation.
Every planned mutation is held behind a separate Owner-signed exact-action
release and independently enforced Production Manager root-side checks.
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
import sys
from typing import Any, Mapping

# Support both `python -m tools.catalog_scoped_root_install_plan` and direct
# operator invocation. This read-only utility has no privileged apply path.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.catalog_scoped_promotion_bundle import FILES, git as source_git
from tools.catalog_scoped_promotion import (
    ADMISSION_RECEIPT_SHA256, historical_receipt_verified, make_offer,
)
from tools.catalog_scoped_release_admission import (
    load_manifest, verify_native_preflights,
)

SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
ROOT_BUNDLE = Path("/usr/local/lib/jason/catalog-scoped-promotion")
ROOT_WORKER = Path("/usr/local/lib/jason/release_host_reconcile_worker.py")
POLICY = Path("/etc/jason-owner-release/catalog-scoped-promotion-installed.json")
STATE = Path("/var/lib/jason/openclaw/release-manager")
ROOT_STATE = Path("/var/lib/jason/catalog-scoped-promotion")
OWNER_HANDOFF = Path("/var/lib/jason/authority/catalog-scoped-release")
OWNER_PUBKEY = Path("/etc/jason-owner-release/verified-owner-public-key.json")
DEPLOYED_HOST = Path("/opt/jason/current")
FROZEN_MARKER = STATE / "production-deployment-freeze"
SYSTEMD = Path("/etc/systemd/system")
POLICY_FIELDS = frozenset({
    "schema_version", "action", "source_sha", "host_module_sha256",
    "catalog_core_sha256", "admission_module_sha256", "native_deployer_sha256",
    "root_readback_guard_sha256", "native_root_control_supported",
    "automatic_recovery_installed", "no_global_owner_elevation",
    "recovery_module_sha256", "recovery_service_sha256",
    "recovery_timer_sha256", "root_worker_sha256",
})

class CatalogRootInstallPlanDenied(PermissionError):
    pass


def deny(code: str) -> None:
    raise CatalogRootInstallPlanDenied("CATALOG_ROOT_INSTALL_" + code)


def digest(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def canonical(data: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(data), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def repo_revision(repo: Path) -> str:
    data = source_git(repo, "ls-remote", "origin", "refs/heads/main")
    chunks = data.decode("ascii").strip().split()
    if len(chunks) != 2 or chunks[1] != "refs/heads/main" or not SHA.fullmatch(chunks[0]):
        deny("PROTECTED_MAIN_REFERENCE_INVALID")
    return chunks[0]


def root_policy(source_sha: str, blobs: Mapping[str, bytes]) -> dict[str, Any]:
    mapping = {
        "host_module_sha256": "tools/catalog_scoped_promotion_host.py",
        "catalog_core_sha256": "tools/catalog_scoped_promotion.py",
        "admission_module_sha256": "tools/catalog_scoped_release_admission.py",
        "native_deployer_sha256": "tools/deploy_live_container.py",
        "root_readback_guard_sha256": "tools/catalog_scoped_control_readback.py",
        "recovery_module_sha256": "tools/catalog_scoped_promotion_recovery.py",
        "root_worker_sha256": "tools/release_host_reconcile_worker.py",
        "recovery_service_sha256": "infrastructure/openclaw-operations/systemd/jason-catalog-scoped-recovery.service",
        "recovery_timer_sha256": "infrastructure/openclaw-operations/systemd/jason-catalog-scoped-recovery.timer",
    }
    result: dict[str, Any] = {
        "schema_version": "1.0",
        "action": "catalog-scoped-runtime-mcp-one-release-v1",
        "source_sha": source_sha,
        "native_root_control_supported": True,
        "automatic_recovery_installed": True,
        "no_global_owner_elevation": True,
    }
    for key, relative in mapping.items():
        if relative not in blobs:
            deny("MISSING_NATIVE_CONTROL_SOURCE")
        result[key] = digest(blobs[relative])
    if set(result) != POLICY_FIELDS:
        deny("INSTALLED_POLICY_SCHEMA_INVALID")
    return result


def target_for_source(relative: str) -> dict[str, str]:
    if relative not in FILES or relative.startswith("/") or ".." in Path(relative).parts:
        deny("UNREVIEWED_SOURCE_PATH")
    if relative == "tools/release_host_reconcile_worker.py":
        install = ROOT_WORKER
        mode = "0755"
    elif relative.startswith("infrastructure/openclaw-operations/systemd/"):
        install = SYSTEMD / Path(relative).name
        mode = "0644"
    else:
        install = ROOT_BUNDLE / relative
        mode = "0644"
    return {"source": relative, "destination": str(install),
            "uid": "root", "gid": "root", "mode": mode}


def check_existing_host(*, installed_worker: Path = ROOT_WORKER,
                        owner_public_key: Path = OWNER_PUBKEY,
                        host_pointer: Path = DEPLOYED_HOST,
                        freeze: Path = FROZEN_MARKER,
                        expected_rollback: str,
                        expected_freeze_sha256: str) -> dict[str, Any]:
    if not isinstance(expected_rollback, str) or not SHA.fullmatch(expected_rollback):
        deny("ROLLBACK_SOURCE_INVALID")
    if not isinstance(expected_freeze_sha256, str) or not DIGEST.fullmatch(expected_freeze_sha256):
        deny("FROZEN_MARKER_HASH_INVALID")
    if installed_worker.is_symlink() or not installed_worker.is_file():
        deny("EXISTING_ROOT_WORKER_MISSING")
    worker_info = installed_worker.lstat()
    if (worker_info.st_uid != 0 or not stat.S_ISREG(worker_info.st_mode)
            or stat.S_IMODE(worker_info.st_mode) != 0o755 or worker_info.st_nlink != 1):
        deny("EXISTING_ROOT_WORKER_UNTRUSTED")
    if owner_public_key.is_symlink() or not owner_public_key.is_file():
        deny("PINNED_OWNER_PUBKEY_UNAVAILABLE")
    key_info = owner_public_key.lstat()
    if (key_info.st_uid != 0 or not stat.S_ISREG(key_info.st_mode)
            or key_info.st_mode & 0o022):
        deny("PINNED_OWNER_PUBKEY_UNTRUSTED")
    try:
        actual_host_sha = host_pointer.resolve(strict=True).name
    except OSError as exc:
        raise CatalogRootInstallPlanDenied("CATALOG_ROOT_INSTALL_HOST_POINTER_INVALID") from exc
    if actual_host_sha != expected_rollback:
        deny("HOST_REVISION_CHANGED")
    if freeze.is_symlink() or not freeze.is_file():
        deny("ORIGINAL_PRODUCTION_FREEZE_NOT_ACTIVE")
    frozen = freeze.read_bytes()
    if digest(frozen) != expected_freeze_sha256:
        deny("ORIGINAL_PRODUCTION_FREEZE_CHANGED")
    return {
        "rollback_host_revision": actual_host_sha,
        "root_worker_before_sha256": digest(installed_worker.read_bytes()),
        "pinned_owner_pubkey_file_sha256": digest(owner_public_key.read_bytes()),
        "freeze_sha256": digest(frozen),
        "live_root_install_verified": False,
        "root_state_readback_required": True,
    }


def build_install_plan(
    repo: Path, fresh_receipt: Mapping[str, Any],
    historical_receipt: Mapping[str, Any],
    host_evidence: Mapping[str, Any], *,
    expected_source_sha: str,
) -> dict[str, Any]:
    if not isinstance(expected_source_sha, str) or not SHA.fullmatch(expected_source_sha):
        deny("SOURCE_SHA_REQUIRED")
    main_sha = repo_revision(repo)
    if main_sha != expected_source_sha:
        deny("PROTECTED_MAIN_MOVED")
    manifest = load_manifest(repo, main_sha=main_sha)
    historical_receipt_verified(historical_receipt, manifest)
    offer = make_offer(manifest, historical_receipt, fresh_receipt)
    if offer["protected_main_sha"] != main_sha:
        deny("OFFER_NOT_CURRENT_PROTECTED_MAIN")
    for name, expected in (("rollback_host_revision", manifest["rollback_sha"]),
                           ("freeze_sha256", manifest["freeze_sha256"])):
        if host_evidence.get(name) != expected:
            deny("LIVE_HOST_OR_FREEZE_DRIFT")
    if (host_evidence.get("live_root_install_verified") is not False
            or host_evidence.get("root_state_readback_required") is not True):
        deny("ROOT_INSTALL_EVIDENCE_SCOPE_INVALID")
    blobs = {rel: source_git(repo, "show", f"{main_sha}:{rel}") for rel in FILES}
    if any(not b or len(b) > 500_000 for b in blobs.values()):
        deny("ROOT_BUNDLE_SOURCE_UNAVAILABLE")
    policy = root_policy(main_sha, blobs)
    plan = {
        "schema_version": "1.0",
        "status": "SOURCE_ONLY_ROOT_INSTALL_PREPARED_NOT_AUTHORIZED",
        "source_sha": main_sha,
        "immutable_candidate_snapshot_sha": offer["candidate_sha"],
        "rollback_source_sha": offer["rollback_sha"],
        "catalog_scope_sha256": offer["scope_sha256"],
        "original_admission_receipt_sha256": ADMISSION_RECEIPT_SHA256,
        "fresh_admission_receipt_sha256": offer["fresh_admission_receipt_sha256"],
        "signed_promotion_manifest_sha256": offer["manifest_sha256"],
        "runtime_image_id": offer["runtime_image_id"],
        "mcp_image_id": offer["mcp_image_id"],
        "rollback_runtime_image_id": offer["rollback_runtime_image_id"],
        "rollback_mcp_image_id": offer["rollback_mcp_image_id"],
        "freeze_sha256": offer["freeze_sha256"],
        "host_readback": dict(host_evidence),
        "root_policy_after_separate_approval": policy,
        "root_file_plan": [dict(target_for_source(rel), sha256=digest(blobs[rel]))
                           for rel in sorted(FILES)],
        "directories_after_separate_approval": [
            {"path": str(ROOT_STATE), "owner": "root", "mode": "0700"},
            *[{"path": str(ROOT_STATE / part), "owner": "root", "mode": "0700"}
              for part in ("offers", "transactions", "consumed-owner-approvals", "freeze-backups")],
            {"path": str(OWNER_HANDOFF), "owner": "al", "mode": "0700"},
            *[{"path": str(OWNER_HANDOFF / part), "owner": "al", "mode": "0700"}
              for part in ("offers", "owner-approvals")],
        ],
        "root_policy_target": str(POLICY),
        "rollback_root_worker_sha256": host_evidence["root_worker_before_sha256"],
        "recovery_timer_name": "jason-catalog-scoped-recovery.timer",
        "rollback_original_worker_required": True,
        "signed_exact_root_install_approval_required": True,
        "signed_separate_image_promotion_approval_required": True,
        "separate_autotask_provider_test_write_approval_required": True,
        "root_state_readback_after_install_required": True,
        "production_mutations": False,
        "provider_writes": False,
        "owner_approval_recorded": False,
        "installation_executable_in_source_only_mode": False,
    }
    plan["install_plan_sha256"] = digest(canonical(plan))
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only, no deployment option")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--fresh-receipt", type=Path, required=True)
    parser.add_argument("--historical-receipt", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.expanduser().resolve()
    manifest = load_manifest(repo, main_sha=args.expected_source_sha)
    evidence = check_existing_host(
        expected_rollback=manifest["rollback_sha"],
        expected_freeze_sha256=manifest["freeze_sha256"],
    )
    plan = build_install_plan(
        repo, json.loads(args.fresh_receipt.read_text()),
        json.loads(args.historical_receipt.read_text()), evidence,
        expected_source_sha=args.expected_source_sha,
    )
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
