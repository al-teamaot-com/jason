"""Non-active V5 signed browser decision: root independently verifies signature.

No route invokes this module, no signing key is provisioned, and no Release
Manager/ApprovalRequestService mutation occurs. This is a governed source
primitive for the existing approval pipeline, NOT an approval bypass.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import base64
import hmac
import json
import re
import secrets
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .entra_release_stepup import ExactRelease, EntraStepUpDenied, ReleaseIdentityRoute

_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_NONCE = re.compile(r"^[A-Za-z0-9_-]{40,100}$")
_KEY_ID = re.compile(r"^[a-z][a-z0-9_.:-]{3,80}$")
_VERSION = "5.0"
_CHANNEL = "entra_browser_admin"
_MAX_DECISION_SECONDS = 300


def _canonical(data: Mapping[str, Any]) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _strict_keys(data: Mapping[str, Any], allowed: set[str]) -> None:
    if not isinstance(data, dict) or set(data) != allowed:
        raise EntraStepUpDenied("V5_EVIDENCE_SCHEMA_INVALID")


_FIELDS = {
    "schema_version", "channel", "decision", "approval_id", "candidate_sha",
    "rollback_sha", "scope_sha256", "manifest_sha256", "release_fingerprint",
    "tenant_id", "authenticated_admin_oid", "owner_subject_id",
    "auth_time", "decided_at", "expires_at", "nonce", "evidence_sha256",
}


def _validate_proof(
    proof: Mapping[str, Any], *, approval: ExactRelease,
    route: ReleaseIdentityRoute, now: datetime,
) -> None:
    if not isinstance(proof, Mapping) or proof.get("release_authorized") is not False:
        raise EntraStepUpDenied("V5_UNVERIFIED_LOGIN_PROOF")
    exact = {
        "authenticated_admin_oid": route.admin_approver_oid,
        "tenant_id": route.tenant_id,
        "owner_subject_id": route.owner_subject_id,
        "approval_id": approval.approval_id,
        "channel": "microsoft_entra_browser_stepup",
        "candidate_sha": approval.candidate_sha,
        "scope_sha256": approval.scope_sha256,
        "rollback_sha": approval.rollback_sha,
        "manifest_sha256": approval.manifest_sha256,
    }
    for key, value in exact.items():
        if proof.get(key) != value:
            raise EntraStepUpDenied("V5_LOGIN_IDENTITY_OR_RELEASE_MISMATCH")
    digest = proof.get("evidence_sha256")
    auth = proof.get("auth_time")
    if (not isinstance(digest, str) or not _SHA64.fullmatch(digest)
            or type(auth) is not int
            or not 0 <= int(now.timestamp()) - auth <= _MAX_DECISION_SECONDS):
        raise EntraStepUpDenied("V5_LOGIN_FRESHNESS_UNVERIFIED")


def create_browser_decision_envelope(
    *, approval: ExactRelease, route: ReleaseIdentityRoute,
    verified_login_proof: Mapping[str, Any], decision: str,
    signing_key: Ed25519PrivateKey, key_id: str, now: datetime,
) -> dict[str, Any]:
    """Sign one explicit UI choice following verified admin login.

    Caller MUST ensure an authenticated same-origin explicit decision POST.
    This method alone never writes to the approval or release ledger.
    """
    route.validate()
    approval.validate()
    if (decision not in ("approve", "deny") or type(decision) is not str
            or not _KEY_ID.fullmatch(key_id)
            or not isinstance(signing_key, Ed25519PrivateKey)
            or now.tzinfo is None or now >= approval.expires_at):
        raise EntraStepUpDenied("V5_SIGNING_INPUT_INVALID")
    _validate_proof(verified_login_proof, approval=approval, route=route, now=now)
    payload = {
        "schema_version": _VERSION, "channel": _CHANNEL, "decision": decision,
        "approval_id": approval.approval_id, "candidate_sha": approval.candidate_sha,
        "rollback_sha": approval.rollback_sha, "scope_sha256": approval.scope_sha256,
        "manifest_sha256": approval.manifest_sha256,
        "release_fingerprint": approval.fingerprint(),
        "tenant_id": route.tenant_id,
        "authenticated_admin_oid": route.admin_approver_oid,
        "owner_subject_id": route.owner_subject_id,
        "auth_time": verified_login_proof["auth_time"],
        "decided_at": now.astimezone(timezone.utc).isoformat(),
        "expires_at": approval.expires_at.astimezone(timezone.utc).isoformat(),
        "nonce": secrets.token_urlsafe(32),
        "evidence_sha256": verified_login_proof["evidence_sha256"],
    }
    signature = signing_key.sign(_canonical(payload))
    return {
        "payload": payload, "key_id": key_id,
        "signature": base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii"),
    }


def verify_browser_decision_envelope(
    envelope: Mapping[str, Any], *, approval: ExactRelease,
    route: ReleaseIdentityRoute, trusted_public_keys: Mapping[str, Ed25519PublicKey],
    now: datetime,
) -> dict[str, Any]:
    """Host-side independent cryptographic read, no approval mutation.

    Replay prevention is enforced by the existing one-decision-per-request
    approval ledger BEFORE a V5 host consumer applies a verified decision.
    """
    approval.validate()
    route.validate()
    _strict_keys(envelope, {"payload", "key_id", "signature"})
    key_id = envelope["key_id"]
    if not isinstance(key_id, str) or not _KEY_ID.fullmatch(key_id):
        raise EntraStepUpDenied("V5_SIGNING_KEY_NOT_TRUSTED")
    key = trusted_public_keys.get(key_id)
    if not isinstance(key, Ed25519PublicKey):
        raise EntraStepUpDenied("V5_SIGNING_KEY_NOT_TRUSTED")
    payload = envelope["payload"]
    _strict_keys(payload, _FIELDS)
    signature = envelope["signature"]
    if not isinstance(signature, str) or not re.fullmatch(r"[A-Za-z0-9_-]{86}", signature):
        raise EntraStepUpDenied("V5_SIGNATURE_INVALID")
    try:
        raw = base64.urlsafe_b64decode(signature + "==")
        key.verify(raw, _canonical(payload))
    except (InvalidSignature, ValueError, TypeError) as exc:
        raise EntraStepUpDenied("V5_SIGNATURE_INVALID") from exc
    exact = {
        "schema_version": _VERSION, "channel": _CHANNEL,
        "approval_id": approval.approval_id, "candidate_sha": approval.candidate_sha,
        "rollback_sha": approval.rollback_sha, "scope_sha256": approval.scope_sha256,
        "manifest_sha256": approval.manifest_sha256,
        "release_fingerprint": approval.fingerprint(),
        "tenant_id": route.tenant_id,
        "authenticated_admin_oid": route.admin_approver_oid,
        "owner_subject_id": route.owner_subject_id,
        "expires_at": approval.expires_at.astimezone(timezone.utc).isoformat(),
    }
    for field, value in exact.items():
        if payload[field] != value:
            raise EntraStepUpDenied("V5_SIGNED_SCOPE_OR_IDENTITY_MISMATCH")
    if payload["decision"] not in ("approve", "deny"):
        raise EntraStepUpDenied("V5_SIGNED_DECISION_INVALID")
    if not isinstance(payload["nonce"], str) or not _NONCE.fullmatch(payload["nonce"]):
        raise EntraStepUpDenied("V5_NONCE_INVALID")
    if not isinstance(payload["evidence_sha256"], str) or not _SHA64.fullmatch(payload["evidence_sha256"]):
        raise EntraStepUpDenied("V5_SOURCE_EVIDENCE_INVALID")
    try:
        decided = datetime.fromisoformat(payload["decided_at"])
    except (TypeError, ValueError) as exc:
        raise EntraStepUpDenied("V5_DECISION_TIME_INVALID") from exc
    auth = payload["auth_time"]
    if (now.tzinfo is None or decided.tzinfo is None or
            decided > now or now >= approval.expires_at or
            not 0 <= (now - decided).total_seconds() <= _MAX_DECISION_SECONDS or
            type(auth) is not int or
            not 0 <= int(decided.timestamp()) - auth <= _MAX_DECISION_SECONDS):
        raise EntraStepUpDenied("V5_DECISION_NOT_FRESH")
    return {
        "verification": "signature_and_exact_subject_verified",
        "channel": _CHANNEL,
        "approval_id": approval.approval_id,
        "decision": payload["decision"],
        "authenticated_admin_oid": route.admin_approver_oid,
        "tenant_id": route.tenant_id,
        "signed_evidence_sha256": sha256(_canonical(envelope)).hexdigest(),
        "release_fingerprint": approval.fingerprint(),
        # Verifier cannot apply release authority; independent policy consumer
        # must still validate root policy, CCC, nonreplay and release lock.
        "release_authorized": False,
    }
