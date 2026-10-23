#!/usr/bin/env python3
"""Exact-release root drift-policy migration with symmetric rollback.

Root-only, invoked from an immutable candidate during native host reconciliation
and by the already installed root-owned reconciler before downgrading.
Never runs through a provider or grants release authority. A missing or
mismatched owner approval, CCC review, protected source or exact diff fails.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SHA = re.compile(r"[0-9a-f]{40}\Z")
ROOT = Path("/var/lib/jason/openclaw/release-manager")
POLICY = Path("/etc/jason/release-readback-recovery/production-desired-state.json")
MANAGED_GIT = Path("/home/al/.local/lib/jason/engineering-source-repo")
LEDGER_DIR = Path("/etc/jason/release-readback-recovery/approved-migrations")
ACTIVE = LEDGER_DIR / "active.json"
CCC_REVIEW = Path("/var/lib/jason/ccc/material-review.json")
UNIT_FIELDS = (
    "required_system_units", "allowed_system_units",
    "required_user_units", "allowed_user_units",
)
# The ONLY permitted migration for incident #1974. Never infer wider root
# permission from a candidate's self-declared desired-state JSON.
APPROVED_DELTA = {
    "required_system_units": frozenset(
        {"jason-openclaw-authority-full-integrity.timer"}
    ),
    "allowed_system_units": frozenset(
        {"jason-openclaw-authority-full-integrity.service"}
    ),
    "required_user_units": frozenset(),
    "allowed_user_units": frozenset(
        {"jason-openclaw-recovery-source-bridge.service",
         "jason-openclaw-recovery-source-bridge.timer"}
    ),
}


# Stage the timer as ALLOWED, never REQUIRED, until the root host script
# confirms systemd activation. Other reviewed additions are also allowed.
# This closes the watchdog race from installed-but-undeclared candidate units.
STAGED_DELTA = {
    "required_system_units": frozenset(),
    "allowed_system_units": APPROVED_DELTA["allowed_system_units"] | APPROVED_DELTA["required_system_units"],
    "required_user_units": frozenset(),
    "allowed_user_units": APPROVED_DELTA["allowed_user_units"],
}


class MigrationRefused(RuntimeError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha(value: object) -> str:
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise MigrationRefused("exact 40-character source SHA required")
    return value


def _root_only(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != 0
                or st.st_mode & 0o077 or st.st_size > 131072):
            raise MigrationRefused("root-only regular file, mode 0600, required")
        with os.fdopen(fd, "rb", closefd=False) as file:
            return file.read()
    finally:
        os.close(fd)


def _json(data: bytes) -> dict:
    parsed = json.loads(data)
    if not isinstance(parsed, dict) or parsed.get("schema_version") != "1.0":
        raise MigrationRefused("protected release-policy schema is invalid")
    return parsed


def _safe_units(policy: dict) -> None:
    for key in UNIT_FIELDS:
        items = policy.get(key)
        if (not isinstance(items, list) or len(items) != len(set(map(str, items)))
                or any(not isinstance(x, str)
                       or not re.fullmatch(r"jason-[a-z0-9_.@-]{1,120}", x)
                       for x in items)):
            raise MigrationRefused("unsafe unit field: " + key)


def _reviewed_git_policy(revision: str) -> dict:
    """Immutable Git commit content for read-only PRE-INSTALL preview.

    At host-reconcile preflight the candidate /opt/jason/releases/<sha>
    DOES NOT YET EXIST. Read only the previously verified main-ancestor
    Git object, never an editable checkout, and never change root policy.
    Actual APPLY still requires the root-owned immutable release directory.
    """
    _sha(revision)
    command = [
        "/usr/bin/git", "-c", f"safe.directory={MANAGED_GIT}",
        "-C", str(MANAGED_GIT),
        "show", f"{revision}:config/production-desired-state.json",
    ]
    try:
        data = subprocess.check_output(
            command, stderr=subprocess.DEVNULL, timeout=15
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise MigrationRefused("protected exact-source desired state unavailable") from exc
    if len(data) > 131072:
        raise MigrationRefused("protected exact-source desired state too large")
    policy = _json(data)
    _safe_units(policy)
    return policy


def _source_policy(revision: str) -> dict:
    revision = _sha(revision)
    folder = Path("/opt/jason/releases") / revision
    # Validate every path component BEFORE reading bytes as root, rejecting
    # Git symlinks and any mutable non-root content.
    directory = folder / "config"
    path = directory / "production-desired-state.json"
    for item in (folder, directory):
        info = item.lstat()
        if (not stat.S_ISDIR(info.st_mode) or item.is_symlink()
                or info.st_uid != 0 or info.st_mode & 0o022):
            raise MigrationRefused("immutable source directory is not root-controlled")
    if folder.resolve() != folder or directory.resolve() != directory:
        raise MigrationRefused("immutable source path is not canonical")
    meta = path.lstat()
    if (not stat.S_ISREG(meta.st_mode) or path.is_symlink()
            or meta.st_uid != 0 or meta.st_mode & 0o022
            or meta.st_size > 131072):
        raise MigrationRefused("immutable source policy file is not securely rooted")
    policy = _json(path.read_bytes())
    _safe_units(policy)
    return policy


def _planned_delta(previous: dict, candidate: dict) -> None:
    _safe_units(previous)
    _safe_units(candidate)
    if set(previous) != set(candidate):
        raise MigrationRefused("candidate changed desired-state policy keys")
    for key in previous:
        if key not in UNIT_FIELDS:
            if previous[key] != candidate[key]:
                raise MigrationRefused("unreviewed non-unit policy change: " + key)
            continue
        original = set(previous[key])
        after = set(candidate[key])
        if original - after or after - original != APPROVED_DELTA[key]:
            raise MigrationRefused("unapproved desired-state unit delta: " + key)


def _approval(candidate_sha: str, rollback_sha: str) -> None:
    release_id = "release-" + candidate_sha[:16]
    record = json.loads((ROOT / "records" / (release_id + ".json")).read_text())
    owner = record.get("owner_approval") or {}
    manifest = record.get("release_manifest") or {}
    if (record.get("state") != "production"
            or owner.get("approved") is not True
            or owner.get("candidate_sha") != candidate_sha
            or manifest.get("candidate_sha") != candidate_sha
            or manifest.get("rollback_sha") != rollback_sha
            or record.get("risk_profile") != "production_control_core"):
        raise MigrationRefused("exact owner-approved production release record required")
    review = json.loads(CCC_REVIEW.read_text())
    if (review.get("source_revision") != candidate_sha
            or review.get("status") != "approved"
            or review.get("recorded_by") != "person-al"):
        raise MigrationRefused("exact owner-reviewed CCC material evidence required")
    control = _json(_root_only(ROOT / "production-control-state.json"))
    lkg = (control.get("last_known_good") or {}).get("manifest") or {}
    if (lkg.get("revision") != rollback_sha or lkg.get("complete") is not True
            or (control.get("circuit_breaker") or {}).get("state") != "closed"):
        raise MigrationRefused("root protected last-known-good and breaker are not aligned")


def _atomic(path: Path, value: bytes) -> None:
    fd, temp = tempfile.mkstemp(prefix=".root-policy-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            os.fchown(handle.fileno(), 0, 0)
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        dfd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _ledger_dir() -> None:
    if not LEDGER_DIR.is_dir() or LEDGER_DIR.is_symlink():
        if LEDGER_DIR.exists():
            raise MigrationRefused("protected migration directory is unsafe")
        LEDGER_DIR.mkdir(mode=0o700)
    info = LEDGER_DIR.stat()
    if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
        raise MigrationRefused("root-owned migration directory mode 0700 required")


def _require_root() -> None:
    if os.geteuid() != 0:
        raise MigrationRefused("root authority required")


def _current_root_policy() -> tuple[bytes, dict]:
    original = _root_only(POLICY)
    policy = _json(original)
    _safe_units(policy)
    return original, policy


def preview_exact_migration(candidate_sha: str, rollback_sha: str) -> str:
    """Read-only host preflight for the reviewed, candidate-bound unit delta.

    This never changes root policy or a release record. The immutable host
    reconciler still must apply the signed plan and independently re-check
    coverage before it can report success.
    """
    _require_root()
    candidate_sha, rollback_sha = _sha(candidate_sha), _sha(rollback_sha)
    _approval(candidate_sha, rollback_sha)
    # The candidate host release directory is created AFTER this preview.
    # A root-only immutable release file is required later at actual APPLY.
    old = _reviewed_git_policy(rollback_sha)
    new = _reviewed_git_policy(candidate_sha)
    _planned_delta(old, new)
    original, root = _current_root_policy()
    if set(root) != set(old):
        raise MigrationRefused("root recovery policy shape differs from protected source")
    for key in old:
        if key not in UNIT_FIELDS and root[key] != old[key]:
            raise MigrationRefused("unreviewed independent root policy change: " + key)
    for field in UNIT_FIELDS:
        known = set(old[field])
        actual = set(root[field])
        if not known.issubset(actual):
            raise MigrationRefused("root policy lost a known-good declaration: " + field)
        if actual.intersection(APPROVED_DELTA[field]):
            raise MigrationRefused("candidate-only unit already present without migration receipt")
    if ACTIVE.exists():
        raise MigrationRefused("preexisting root migration requires independent review")
    return "OWNER_CCC_REVIEWED_DELTA_ONLY"


def _overlay_policy(root_policy: dict, additions: dict[str, frozenset[str]]) -> bytes:
    result = dict(root_policy)
    for key in UNIT_FIELDS:
        result[key] = sorted(set(root_policy[key]) | additions[key])
    return (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()


def _receipt_match(receipt: dict, candidate_sha: str, rollback_sha: str) -> None:
    if (receipt.get("candidate_sha") != candidate_sha
            or receipt.get("rollback_sha") != rollback_sha
            or receipt.get("reviewed_delta") != {
                key: sorted(value) for key, value in APPROVED_DELTA.items()
            }):
        raise MigrationRefused("root migration receipt belongs to another release")


def stage_for_candidate(candidate_sha: str, rollback_sha: str) -> str:
    """Audited short-lived ALLOWED-only policy stage before unit installation.

    A full required timer is NOT declared until later full host activation.
    Active policy is always individually checked against its phase hash.
    """
    _require_root()
    candidate_sha, rollback_sha = _sha(candidate_sha), _sha(rollback_sha)
    _approval(candidate_sha, rollback_sha)
    previous = _source_policy(rollback_sha)
    candidate = _source_policy(candidate_sha)
    _planned_delta(previous, candidate)
    _ledger_dir()
    if ACTIVE.exists():
        receipt = _json(_root_only(ACTIVE))
        _receipt_match(receipt, candidate_sha, rollback_sha)
        raw, _ = _current_root_policy()
        phase = receipt.get("phase")
        if phase == "staged" and digest(raw) == receipt.get("staged_sha256"):
            return "ALREADY_STAGED"
        if phase == "applied" and digest(raw) == receipt.get("applied_sha256"):
            return "ALREADY_APPLIED"
        raise MigrationRefused("prior migration phase or root bytes require recovery")

    original, root_policy = _current_root_policy()
    if set(root_policy) != set(previous):
        raise MigrationRefused("root recovery policy differs in structure from old source")
    for key in root_policy:
        if key not in UNIT_FIELDS and root_policy[key] != previous[key]:
            raise MigrationRefused("unreviewed non-unit root recovery policy difference: " + key)
        if key in UNIT_FIELDS:
            current = set(root_policy[key])
            if not set(previous[key]).issubset(current):
                raise MigrationRefused("root recovery overlay missing known-good units: " + key)
            if current.intersection(STAGED_DELTA[key] | APPROVED_DELTA[key]):
                raise MigrationRefused("candidate-specific root unit already present without ledger")

    staged = _overlay_policy(root_policy, STAGED_DELTA)
    final = _overlay_policy(root_policy, APPROVED_DELTA)
    receipt = {
        "schema_version": "1.0", "candidate_sha": candidate_sha,
        "rollback_sha": rollback_sha, "phase": "prepared",
        "original_sha256": digest(original), "staged_sha256": digest(staged),
        "applied_sha256": digest(final),
        "original_policy_base64": base64.b64encode(original).decode("ascii"),
        "authorized_by": "exact_owner_approval_and_ccc_material_review",
        "reviewed_delta": {key: sorted(v) for key, v in APPROVED_DELTA.items()},
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    # Durable undo receipt precedes any protected policy replacement.
    _atomic(ACTIVE, (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode())
    _atomic(POLICY, staged)
    receipt["phase"] = "staged"
    _atomic(ACTIVE, (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode())
    return "STAGED_ALLOWED_ONLY"


def apply_for_candidate(candidate_sha: str, rollback_sha: str) -> str:
    """Commit required timer only AFTER the candidate's full systemd check."""
    _require_root()
    candidate_sha, rollback_sha = _sha(candidate_sha), _sha(rollback_sha)
    _approval(candidate_sha, rollback_sha)
    previous = _source_policy(rollback_sha)
    candidate = _source_policy(candidate_sha)
    _planned_delta(previous, candidate)
    _ledger_dir()
    if not ACTIVE.exists():
        raise MigrationRefused("approved root policy stage missing before final commit")

    receipt = _json(_root_only(ACTIVE))
    _receipt_match(receipt, candidate_sha, rollback_sha)
    raw, _ = _current_root_policy()
    if receipt.get("phase") == "applied" and digest(raw) == receipt.get("applied_sha256"):
        return "ALREADY_APPLIED"
    if receipt.get("phase") not in {"staged", "prepared"}:
        raise MigrationRefused("root migration was not staged")
    if digest(raw) != receipt.get("staged_sha256"):
        raise MigrationRefused("root policy diverged from exact approved stage")
    original = base64.b64decode(receipt["original_policy_base64"], validate=True)
    if digest(original) != receipt.get("original_sha256"):
        raise MigrationRefused("root original-byte receipt checksum mismatch")
    baseline = _json(original)
    _safe_units(baseline)
    final = _overlay_policy(baseline, APPROVED_DELTA)
    if digest(final) != receipt.get("applied_sha256"):
        raise MigrationRefused("root exact final policy hash mismatch")
    _atomic(POLICY, final)
    receipt["phase"] = "applied"
    _atomic(ACTIVE, (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode())
    return "APPLIED_REQUIRED_AFTER_HEALTH"


def restore_for_baseline(target_sha: str) -> str:
    """Revert only an audited exact migration before immutable rollback."""
    _require_root()
    target_sha = _sha(target_sha)
    if not ACTIVE.is_file():
        return "NO_MIGRATION_ACTIVE"
    receipt = _json(_root_only(ACTIVE))
    if receipt.get("rollback_sha") != target_sha:
        raise MigrationRefused("rollback target differs from audited previous LKG")
    if receipt.get("reviewed_delta") != {k: sorted(v) for k, v in APPROVED_DELTA.items()}:
        raise MigrationRefused("root migration receipt does not match reviewed delta")
    original = base64.b64decode(receipt["original_policy_base64"], validate=True)
    if digest(original) != receipt.get("original_sha256"):
        raise MigrationRefused("original protected policy checksum mismatch")
    current, _ = _current_root_policy()
    if digest(current) not in {receipt.get("original_sha256"), receipt.get("staged_sha256"), receipt.get("applied_sha256")}:
        raise MigrationRefused("active root policy changed outside migration; refusing restore")
    control = _json(_root_only(ROOT / "production-control-state.json"))
    if (((control.get("last_known_good") or {}).get("manifest") or {}).get("revision")
            != target_sha):
        raise MigrationRefused("root LKG no longer matches exact rollback target")
    _ledger_dir()
    if digest(current) in {receipt.get("staged_sha256"), receipt.get("applied_sha256")}:
        _atomic(POLICY, original)
    receipt["phase"] = "restored"
    receipt["restored_at"] = datetime.now(timezone.utc).isoformat()
    archived = LEDGER_DIR / ("restored-" + _sha(receipt["candidate_sha"]) + ".json")
    if archived.exists():
        raise MigrationRefused("audited migration archive already exists")
    _atomic(archived, (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode())
    ACTIVE.unlink()
    return "RESTORED"


if __name__ == "__main__":
    raise SystemExit("Root policy changes require native host reconcile, not a standalone command")
