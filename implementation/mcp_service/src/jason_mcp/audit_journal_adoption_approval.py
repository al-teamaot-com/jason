"""Exact one-use Entra Owner-signed audit-journal adoption decision.

Source-only until the separately authorized, pinned native Root consumer and
root-produced offer are installed. This is NOT a generic release approval and
cannot start production or modify the archive.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from kernel.signed_owner_release import (
    EXACT_OWNER_OAUTH_SUBJECTS, issue_exact_owner_release,
    verify_exact_owner_release,
)

ACTION = "ADOPT-EXACT-DAILY-AUDIT-JOURNAL"
APPROVAL_WORDS = "APPROVE_EXACT_DAILY_AUDIT_JOURNAL_ARCHIVE"
ROLLBACK = "d1b8c196dadd4b672ec8ba47075f27bb61c98d63"
TENANT = "f7054323-d52b-4863-8c2f-1898f0b6077c"
LICENSED_OWNER = "bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
ARCHIVE = "/srv/jason/archive/governed-audit/orchestration"
SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
RELEASE = re.compile(r"release-[0-9a-f]{16}\Z")
MAX_BYTES = 16384


class AuditJournalApprovalDenied(PermissionError):
    pass


def deny(code: str) -> None:
    raise AuditJournalApprovalDenied("AUDIT_JOURNAL_OWNER_APPROVAL_" + code)


def canonical(data: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(data), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def validate_offer(offer: Mapping[str, Any]) -> dict[str, Any]:
    keys = {
        "schema_version", "action", "release_id", "candidate_sha",
        "rollback_sha", "scope_sha256", "manifest_sha256", "freeze_sha256",
        "archive_root", "owner_oid", "production_breaker_verified",
        "production_drift_verified", "protected_peers_verified",
        "separate_archive_mount_verified", "journal_only",
        "availability_interruption_authorized", "one_use",
        "standing_authority", "production_mutations",
        "root_stage_receipt_sha256", "prepared_at",
    }
    if not isinstance(offer, Mapping) or set(offer) != keys:
        deny("ROOT_OFFER_SCHEMA")
    s = dict(offer)
    if (s["schema_version"] != "1.0"
            or s["action"] != ACTION
            or not isinstance(s["candidate_sha"], str)
            or SHA.fullmatch(s["candidate_sha"]) is None
            or s["rollback_sha"] != ROLLBACK
            or s["candidate_sha"] == ROLLBACK
            or s["release_id"] != "release-" + s["candidate_sha"][:16]
            or s["archive_root"] != ARCHIVE
            or s["owner_oid"] != LICENSED_OWNER
            or any(not isinstance(s[k], str) or DIGEST.fullmatch(s[k]) is None
                   for k in ("scope_sha256", "manifest_sha256",
                             "freeze_sha256", "root_stage_receipt_sha256"))
            or not all(s[k] is True for k in (
                "production_breaker_verified", "production_drift_verified",
                "protected_peers_verified", "separate_archive_mount_verified",
                "journal_only", "availability_interruption_authorized",
                "one_use"))
            or s["standing_authority"] is not False
            or s["production_mutations"] is not False
            or not isinstance(s["prepared_at"], str)):
        deny("ROOT_OFFER_UNTRUSTED")
    try:
        observed = datetime.fromisoformat(s["prepared_at"].replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - observed).total_seconds()
    except (ValueError, TypeError, OverflowError) as exc:
        raise AuditJournalApprovalDenied("AUDIT_JOURNAL_OWNER_APPROVAL_ROOT_OFFER_TIME") from exc
    if observed.tzinfo is None or not -10 <= age <= 600:
        deny("ROOT_OFFER_STALE")
    return s


def read_offer(state_root: Path, release_id: str) -> dict[str, Any]:
    if not isinstance(release_id, str) or RELEASE.fullmatch(release_id) is None:
        deny("RELEASE_ID_INVALID")
    p = state_root / "offers" / (release_id + ".json")
    try:
        st = p.lstat()
        if (p.is_symlink() or not stat.S_ISREG(st.st_mode)
                or st.st_uid != os.geteuid()
                or stat.S_IMODE(st.st_mode) != 0o600
                or st.st_nlink != 1
                or not 1 <= st.st_size <= MAX_BYTES):
            deny("ROOT_OFFER_CUSTODY")
        raw = p.read_bytes()
        if len(raw) != st.st_size:
            deny("ROOT_OFFER_CHANGED")
        offer = validate_offer(json.loads(raw))
    except (OSError, ValueError, TypeError) as exc:
        raise AuditJournalApprovalDenied("AUDIT_JOURNAL_OWNER_APPROVAL_ROOT_OFFER_MISSING") from exc
    if offer["release_id"] != release_id:
        deny("ROOT_OFFER_WRONG_RELEASE")
    return offer


def queue_exact_archive_owner_approval(
    *, state_root: Path, release_id: str, candidate_sha: str,
    scope_sha256: str, manifest_sha256: str,
    approved_by: str, organization_id: str,
    verified_token_claims: Mapping[str, Any],
    service_signer: Ed25519PrivateKey,
    affirmative_decision: str,
) -> dict[str, Any]:
    """Bind an independently verified Owner decision to one prepared Root offer."""
    if affirmative_decision != APPROVAL_WORDS:
        deny("EXACT_AFFIRMATIVE_DECISION_REQUIRED")
    if (not isinstance(service_signer, Ed25519PrivateKey)
            or not isinstance(verified_token_claims, Mapping)
            or verified_token_claims.get("tid") != TENANT
            or verified_token_claims.get("oid") != LICENSED_OWNER
            or approved_by != EXACT_OWNER_OAUTH_SUBJECTS[LICENSED_OWNER]
            or organization_id != "aot"):
        deny("LICENSED_ENTRA_OWNER_REQUIRED")
    offer = read_offer(state_root, release_id)
    if (candidate_sha != offer["candidate_sha"]
            or scope_sha256 != offer["scope_sha256"]
            or manifest_sha256 != offer["manifest_sha256"]):
        deny("EXACT_CANDIDATE_SCOPE_MANIFEST_MISMATCH")
    stamp = datetime.now(timezone.utc)
    signed = issue_exact_owner_release(
        approval_id="owner-mcp-" + uuid4().hex,
        release_id=release_id, candidate_sha=candidate_sha,
        rollback_sha=ROLLBACK, scope_sha256=scope_sha256,
        manifest_sha256=manifest_sha256,
        freeze_sha256=offer["freeze_sha256"],
        verified_tenant_id=TENANT, verified_owner_oid=LICENSED_OWNER,
        verified_principal=approved_by, verified_organization_id="aot",
        confirmed_decision="approve", at=stamp, private_key=service_signer,
    )
    verify_exact_owner_release(
        signed, public_key=service_signer.public_key(),
        expected_candidate_sha=candidate_sha, expected_rollback_sha=ROLLBACK,
        expected_release_id=release_id, expected_scope_sha256=scope_sha256,
        expected_manifest_sha256=manifest_sha256,
        expected_freeze_sha256=offer["freeze_sha256"], at=stamp,
    )
    receipt = {
        "schema_version": "1.0",
        "action": ACTION,
        "release_id": release_id,
        "candidate_sha": candidate_sha,
        "scope_sha256": scope_sha256,
        "manifest_sha256": manifest_sha256,
        "root_stage_receipt_sha256": offer["root_stage_receipt_sha256"],
        "signed_owner_proof": signed,
        "standing_authority": False,
        "owner_approval_is_one_use": True,
        "production_mutations": False,
    }
    folder = state_root / "owner-approvals"
    fm = folder.lstat()
    if (folder.is_symlink() or not stat.S_ISDIR(fm.st_mode)
            or fm.st_uid != os.geteuid()
            or stat.S_IMODE(fm.st_mode) != 0o700):
        deny("APPROVAL_SPOOL_UNTRUSTED")
    target = folder / (release_id + ".json")
    if target.exists() or target.is_symlink():
        deny("ONE_USE_APPROVAL_REPLAY")
    raw = canonical(receipt) + b"\n"
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        pass
    return {
        "status": "signed_exact_owner_approval_queued_not_deployed",
        "release_id": release_id, "candidate_sha": candidate_sha,
        "scope_sha256": scope_sha256,
        "manifest_sha256": manifest_sha256,
        "approval_id": signed["payload"]["approval_id"],
        "root_stage_receipt_sha256": offer["root_stage_receipt_sha256"],
        "owner_approval_is_one_use": True,
        "production_mutations": False,
    }
