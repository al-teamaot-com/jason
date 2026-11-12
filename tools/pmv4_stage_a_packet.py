#!/usr/bin/env python3
"""PMv4 Stage A root-bootstrap scope, root recovery audit and offline rollback.

SOURCE-ONLY. There is intentionally no production apply/enable or root
authorization operation in this CLI. A trusted existing native root release
controller must validate a *separate exact-action signed Owner decision*,
hold the legacy transaction lease, independently re-read root evidence,
install from an immutable exact-source release, and verify protected desired
state. This tool can describe and test that scope, not grant authority.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any

from tools.pmv4_host_install_contract import BUNDLE_FILES, reviewed_code_manifest
from tools.pmv4_shadow_release import EMPTY_BASELINE
from tools.pmv4_host_release_guard import IndependentHostGuard
from implementation.kernel.signed_owner_release import (
    read_pinned_root_owner_public_key, OwnerReleaseProofDenied,
)

SHA = re.compile(r"^[0-9a-f]{40}$")
AUDIENCE = "9b9996e9-5c34-48b7-948c-f44f89352f89"
HOST_CODE = "/usr/local/lib/jason/pmv4-trusted"
ROOT = "/var/lib/jason/pmv4-shadow"
ETC = "/etc/jason/pmv4-shadow"
RELEASE_STATE = Path("/var/lib/jason/openclaw/release-manager")
RECOVERY = Path("/var/lib/jason/openclaw/support-repair/release-breaker-recovery-state.json")
FREEZE = RELEASE_STATE / "production-deployment-freeze"
HOLD = RELEASE_STATE / "auto-promotion-incident-hold"
TRUST = "/etc/jason-owner-release/verified-owner-public-key.json"
SIGNER = "/var/lib/jason/runtime-secrets/owner-release/private_key"
LIVE_LKG = Path("/opt/jason/current")
INITIAL_SHADOW = ROOT + "/releases/" + EMPTY_BASELINE

# Only new PMv4-owned objects may be created/removed in Stage A bootstrap.
# Existing /etc/jason, /usr/local/lib/jason, /opt/jason and the legacy
# production tree are PARENTS/BOUNDARIES, never recursive write targets.
DIRECTORIES = (
    (HOST_CODE, 0o755, 0, 0),
    (HOST_CODE + "/tools", 0o755, 0, 0),
    (HOST_CODE + "/implementation", 0o755, 0, 0),
    (HOST_CODE + "/implementation/kernel", 0o755, 0, 0),
    (ROOT, 0o750, 0, 1000),
    (ROOT + "/control", 0o750, 0, 1000),
    (ROOT + "/control/signed-owner-decisions", 0o770, 0, 1000),
    (ROOT + "/releases", 0o750, 0, 1000),
    (INITIAL_SHADOW, 0o750, 0, 1000),
    (ROOT + "/receipts", 0o750, 0, 1000),
    (ETC, 0o750, 0, 1000),
)
STATIC_DOCS = {
    ROOT + "/control/host-mutation.lock": (b"", 0o600, 0, 0),
    ROOT + "/control/shadow-release.lock": (b"", 0o600, 0, 0),
    ROOT + "/control/shadow-freeze.json": (
        b'{"schema_version":"1.0","service":"jason-pmv4-shadow","status":"active"}',
        0o640, 0, 1000,
    ),
    INITIAL_SHADOW + "/baseline.json": (
        b'{"baseline":"no_prior_shadow_runtime","schema_version":"1.0","service":"jason-pmv4-shadow"}',
        0o640, 0, 1000,
    ),
    ETC + "/entra-audience.json": (
        b'{"audience":"' + AUDIENCE.encode() +
        b'","schema_version":"1.0","service":"jason-pmv4-shadow"}',
        0o640, 0, 1000,
    ),
}
COMPOSE = ROOT + "/control/docker-compose.yml"
CURRENT = ROOT + "/current"
CURRENT_TARGET = "releases/" + EMPTY_BASELINE
NO_TOUCH = (
    "/opt/jason/current",
    "/var/lib/jason/openclaw",
    TRUST,
    SIGNER,
    "/etc/systemd/system",
    "/home/al/.config/systemd/user",
)
LATER_STAGE = (
    ROOT + "/control/approved-manifest.json",
    ROOT + "/control/reviewed-scope.json",
    ROOT + "/control/gateway-token",
    ROOT + "/releases/<approved-candidate>/bundle",
    "/etc/systemd/system/jason-pmv4-shadow.service",
    "jason-mcp-pilot runtime projection and issuer activation",
    "jason-pmv4-shadow-gateway container activation",
    "independent breaker-recovery timer enablement",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def _digest(value: bytes) -> str:
    return sha256(value).hexdigest()


def _require_sha(value: str) -> str:
    if not isinstance(value, str) or SHA.fullmatch(value) is None:
        raise ValueError("STAGE_A_EXACT_SOURCE_SHA_REQUIRED")
    return value


def verify_exact_repository_head(repo: Path, source_sha: str) -> None:
    """Reject stale, dirty or caller-invented source identities on CLI output."""
    _require_sha(source_sha)
    try:
        head = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            text=True, timeout=8,
        ).strip()
        changed = subprocess.check_output(
            ["git", "-C", str(repo), "status", "--porcelain",
             "--untracked-files=normal"],
            text=True, timeout=8,
        ).strip()
    except (subprocess.SubprocessError, OSError) as exc:
        raise ValueError("STAGE_A_GIT_SOURCE_NOT_ATTESTED") from exc
    if head != source_sha or changed:
        raise ValueError("STAGE_A_GIT_SOURCE_NOT_PINNED_AND_CLEAN")


def _scope_file_rows(repo: Path) -> list[dict[str, Any]]:
    data = []
    bundle = reviewed_code_manifest(repo)
    for entry in bundle["files"]:
        data.append({
            "path": HOST_CODE + "/" + entry["path"],
            "source": entry["path"],
            "sha256": entry["sha256"], "mode": "0400", "uid": 0, "gid": 0,
        })
    for path, (value, mode, uid, gid) in STATIC_DOCS.items():
        data.append({"path": path, "source": "constant", "sha256": _digest(value),
                     "mode": f"{mode:04o}", "uid": uid, "gid": gid})
    compose = repo / "config/pmv4-shadow/docker-compose.yml"
    if compose.is_symlink() or not compose.is_file():
        raise ValueError("STAGE_A_COMPOSE_SOURCE_INVALID")
    data.append({"path": COMPOSE, "source": "config/pmv4-shadow/docker-compose.yml",
                 "sha256": _digest(compose.read_bytes()),
                 "mode": "0640", "uid": 0, "gid": 1000})
    return sorted(data, key=lambda row: row["path"])


def build_scope(repo: Path, candidate_sha: str) -> dict[str, Any]:
    _require_sha(candidate_sha)
    code_manifest = reviewed_code_manifest(repo)
    scope = {
        "schema_version": "1.0",
        "phase": "stage-a0-independent-trusted-host-bootstrap",
        "candidate_sha": candidate_sha,
        "rollback_sha": EMPTY_BASELINE,
        "rollback_semantics": "remove-only-new-stage-a-objects-after-verified-journal",
        "host_code_bundle_sha256": code_manifest["bundle_sha256"],
        "directories": [
            {"path": p, "mode": f"{mode:04o}", "uid": uid, "gid": gid}
            for p, mode, uid, gid in DIRECTORIES
        ],
        "files": _scope_file_rows(repo),
        "symlinks": [{"path": CURRENT, "target": CURRENT_TARGET}],
        "never_mutate": list(NO_TOUCH),
        "excluded_until_separate_approved_activation": list(LATER_STAGE),
        "production_services_restart": False,
        "production_freeze_change": False,
        "breaker_mutation": False,
        "owner_issuer_enabled": False,
        "provider_writes": False,
        "install_approval_required": True,
        "installer_authority": "native-root-signed-exact-owner-transaction-only",
    }
    scope["scope_sha256"] = _digest(_canonical(scope))
    return scope


def _trusted_root_file(path: Path) -> bool:
    try:
        meta = path.lstat()
    except OSError:
        return False
    return (stat.S_ISREG(meta.st_mode) and not path.is_symlink()
            and meta.st_uid == 0 and stat.S_IMODE(meta.st_mode) == 0o600
            and meta.st_nlink == 1)


def _json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("STAGE_A_EVIDENCE_PATH_UNTRUSTED")
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("STAGE_A_EVIDENCE_JSON_INVALID")
    return data


def _service_signer_metadata_acceptable() -> bool:
    # Never read or fingerprint private signing material, even for readiness.
    try:
        key = Path(SIGNER)
        meta = key.lstat()
        return (not key.is_symlink() and stat.S_ISREG(meta.st_mode)
                and meta.st_uid == 1000 and stat.S_IMODE(meta.st_mode) == 0o400)
    except OSError:
        return False


def _root_trust_acceptable() -> bool:
    try:
        read_pinned_root_owner_public_key(Path(TRUST), require_root_owned=True)
        return True
    except (OwnerReleaseProofDenied, OSError, ValueError, TypeError):
        return False


def _existing_target_state() -> dict[str, str]:
    result = {}
    for target in (HOST_CODE, ROOT, ETC):
        try:
            Path(target).lstat()
        except FileNotFoundError:
            result[target] = "absent"
        except PermissionError:
            result[target] = "unknown_requires_root_readback"
        except OSError:
            result[target] = "unknown_requires_root_readback"
        else:
            result[target] = "preexisting_target_requires_reconciliation"
    return result


def recovery_readback(*, now: datetime | None = None) -> dict[str, Any]:
    """Read-only delegated root readback; root must revalidate at install."""
    at = now or datetime.now(timezone.utc)
    control_path = RELEASE_STATE / "protected-readback/production-control-state.json"
    drift_path = RELEASE_STATE / "protected-readback/production-drift.json"
    control = _json(control_path)
    drift = _json(drift_path)
    recovery = _json(RECOVERY)
    source = LIVE_LKG.resolve(strict=True).name
    last_good = ((control.get("last_known_good") or {}).get("manifest") or {})
    breaker = control.get("circuit_breaker") or {}
    observations = recovery.get("clean_observations") or []
    observed = datetime.fromisoformat(str(drift.get("observed_at", "")).replace("Z","+00:00"))
    age = (at - observed).total_seconds()
    timestamps = [
        datetime.fromisoformat(str(item).replace("Z", "+00:00"))
        for item in observations
    ]
    timestamps = sorted(timestamps)
    clean = (
        len(set(timestamps)) >= 3
        and all((b-a).total_seconds() >= 15
                for a,b in zip(timestamps, timestamps[1:]))
        and recovery.get("status") == "root_verified_closed"
        and recovery.get("last_revalidation_attempt", {}).get("result") == "root_verified_closed"
        and recovery.get("last_revalidation_attempt", {}).get("revision") == source
    )
    protected_root_metadata = all(_trusted_root_file(RELEASE_STATE / name)
                                  for name in ("production-control-state.json",
                                               "production-drift.json"))
    current_meta = all(x.is_file() and not x.is_symlink()
                       for x in (FREEZE, HOLD))
    release_gate = IndependentHostGuard().protected_release_status()
    existing_targets = _existing_target_state()
    trust_ok = _root_trust_acceptable()
    signer_ok = _service_signer_metadata_acceptable()
    native_revalidation = control.get("last_revalidation") or {}
    return {
        "schema_version": "1.0",
        "evidence_class": "read_only_delegated_root_readback",
        "root_files_uid0_mode0600": protected_root_metadata,
        "pinned_root_public_trust_verified": trust_ok,
        "existing_private_signer_metadata_verified_without_reading_key": signer_ok,
        "last_native_revalidation_complete": native_revalidation.get("complete") is True,
        "last_native_revalidation_revision": native_revalidation.get("revision"),
        "live_production_sha": source,
        "lkg_revision": last_good.get("revision"),
        "runtime_revision": last_good.get("runtime_revision"),
        "mcp_revision": last_good.get("mcp_revision"),
        "breaker_state": breaker.get("state"),
        "breaker_revalidated_revision": breaker.get("revalidated_revision"),
        "breaker_revalidated_at": breaker.get("updated_at"),
        "recovery_observation_count": len(set(timestamps)),
        "recovery_observations_valid": clean,
        "root_drift_status": drift.get("status"),
        "root_drift_problems": drift.get("problems"),
        "drift_observed_at": drift.get("observed_at"),
        "drift_age_seconds": round(age),
        "freeze_present": current_meta,
        "freeze_sha256": _digest(FREEZE.read_bytes()) if FREEZE.is_file() else None,
        "promotion_hold_sha256": _digest(HOLD.read_bytes()) if HOLD.is_file() else None,
        "legacy_lock_present": (RELEASE_STATE/"production-transaction.lock").is_file(),
        "current_release_gate": release_gate,
        "stage_a_targets": existing_targets,
        "stage_a_empty_baseline_verified": all(
            value == "absent" for value in existing_targets.values()
        ),
        "production_install_authorized": False,
        "installation_ready": False,
        "root_only_target_parent_verification_needed": not all(
            value == "absent" for value in existing_targets.values()
        ),
        "protected_main_exact_ci_required_at_install": True,
        "signed_exact_stage_a_owner_decision_required": True,
        "native_governed_installer_required": True,
        "needs_fresh_native_root_revalidation_before_install": True,
        "preflight_evidence_satisfied": (
            protected_root_metadata
            and trust_ok and signer_ok
            and native_revalidation.get("complete") is True
            and native_revalidation.get("revision") == source
            and last_good.get("complete") is True
            and last_good.get("revision") == source
            and last_good.get("runtime_revision") == source
            and last_good.get("mcp_revision") == source
            and breaker.get("state") == "closed"
            and breaker.get("revalidated_revision") == source
            and clean and drift.get("status") == "pass"
            and drift.get("problems") == []
            and 0 <= age <= 120
            and current_meta
            and (RELEASE_STATE/"production-transaction.lock").is_file()
            and release_gate.get("ready") is True
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--scope", action="store_true")
    parser.add_argument("--recovery-readback", action="store_true")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    verify_exact_repository_head(repo, args.source_sha)
    if args.scope == args.recovery_readback:
        parser.error("choose exactly one read-only operation")
    scope = build_scope(repo, args.source_sha)
    if args.scope:
        result = scope
    else:
        result = {"scope_sha256": scope["scope_sha256"],
                  "candidate_sha": args.source_sha,
                  "recovery": recovery_readback()}
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
