"""Provider-neutral one-use Owner release decision evidence.

The service issuing this proof MUST already have authenticated the live Entra
bearer token (signature, issuer, audience, expiry), resolved an active Jason
Owner binding and received a fresh affirmative exact-release request. The
root-host verifier independently checks the issuer's pinned Ed25519 public key
and every immutable release/rollback/scope/manifest/freeze field. A mutable
JSON file, an Owner email, a ChatGPT message, or an untrusted TLS header alone
never supplies production authority.
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import re
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization

TID = "f7054323-d52b-4863-8c2f-1898f0b6077c"
OWNER_OID = "bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
OWNER_PRINCIPAL = "person-entra-bee80bdcffb04c50b453c09d4d411f5f"
ADMIN_OWNER_OID = "c848022d-e13b-4457-84b0-e2f5c00dcaf6"
ADMIN_OWNER_PRINCIPAL = "person-entra-c848022de13b445784b0e2f5c00dcaf6"
EXACT_OWNER_OAUTH_SUBJECTS = {
    OWNER_OID: OWNER_PRINCIPAL,
    ADMIN_OWNER_OID: ADMIN_OWNER_PRINCIPAL,
}
ID_RE = re.compile(r"^owner-mcp-[0-9a-f]{32}$")
SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
SIGNATURE = re.compile(r"^[A-Za-z0-9_-]{86}$")
MAX_AGE = timedelta(minutes=15)


class OwnerReleaseProofDenied(PermissionError):
    pass


def canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def public_key_sha256(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return sha256(raw).hexdigest()


def _fields(data: Mapping[str, Any]) -> None:
    required = {
        "schema_version", "authorization", "approval_id", "decision",
        "tenant_id", "owner_oid", "owner_principal", "organization_id",
        "authentication", "release_id", "candidate_sha", "rollback_sha",
        "scope_sha256", "manifest_sha256", "freeze_sha256",
        "issued_at", "expires_at", "signer_public_key_sha256",
        "standing_authority", "one_release_only",
    }
    if not isinstance(data, Mapping) or set(data) != required:
        raise OwnerReleaseProofDenied("OWNER_RELEASE_PROOF_SCHEMA_INVALID")
    if (data["schema_version"] != "1.0"
            or data["authorization"] != "authenticated_entra_owner_exact_release"
            or data["decision"] not in ("approve", "deny")
            or not isinstance(data["approval_id"], str)
            or ID_RE.fullmatch(data["approval_id"]) is None
            or data["tenant_id"] != TID
            or data["owner_oid"] not in EXACT_OWNER_OAUTH_SUBJECTS
            or data["owner_principal"] != EXACT_OWNER_OAUTH_SUBJECTS.get(
                data["owner_oid"])
            or data["organization_id"] != "aot"
            or data["authentication"] != "verified_entra_oauth_bearer"
            or type(data["one_release_only"]) is not bool
            or data["one_release_only"] is not True
            or type(data["standing_authority"]) is not bool
            or data["standing_authority"] is not False
            or not isinstance(data["release_id"], str)
            or not isinstance(data["candidate_sha"], str)
            or not isinstance(data["rollback_sha"], str)
            or not SHA.fullmatch(data["candidate_sha"])
            or not SHA.fullmatch(data["rollback_sha"])
            or data["release_id"] != "release-" + data["candidate_sha"][:16]
            or any(not isinstance(data[k], str) or DIGEST.fullmatch(data[k]) is None
                   for k in ("scope_sha256", "manifest_sha256", "freeze_sha256",
                             "signer_public_key_sha256"))):
        raise OwnerReleaseProofDenied("OWNER_RELEASE_PROOF_FIELDS_INVALID")


def issue_exact_owner_release(
    *, approval_id: str, release_id: str, candidate_sha: str,
    rollback_sha: str, scope_sha256: str, manifest_sha256: str,
    freeze_sha256: str, verified_tenant_id: str, verified_owner_oid: str,
    verified_principal: str, verified_organization_id: str,
    confirmed_decision: str, at: datetime, private_key: Ed25519PrivateKey,
) -> dict[str, Any]:
    if not isinstance(private_key, Ed25519PrivateKey):
        raise OwnerReleaseProofDenied("OWNER_RELEASE_SIGNER_INVALID")
    if at.tzinfo is None or at.utcoffset() is None:
        raise OwnerReleaseProofDenied("OWNER_RELEASE_TIME_NOT_AWARE")
    at = at.astimezone(timezone.utc)
    payload = {
        "schema_version": "1.0",
        "authorization": "authenticated_entra_owner_exact_release",
        "approval_id": approval_id,
        "decision": confirmed_decision,
        "tenant_id": verified_tenant_id,
        "owner_oid": verified_owner_oid,
        "owner_principal": verified_principal,
        "organization_id": verified_organization_id,
        "authentication": "verified_entra_oauth_bearer",
        "release_id": release_id,
        "candidate_sha": candidate_sha,
        "rollback_sha": rollback_sha,
        "scope_sha256": scope_sha256,
        "manifest_sha256": manifest_sha256,
        "freeze_sha256": freeze_sha256,
        "issued_at": at.isoformat(),
        "expires_at": (at + MAX_AGE).isoformat(),
        "signer_public_key_sha256": public_key_sha256(private_key.public_key()),
        "standing_authority": False,
        "one_release_only": True,
    }
    _fields(payload)
    signature = private_key.sign(canonical(payload))
    return {
        "payload": payload,
        "signature_base64url": base64.urlsafe_b64encode(signature).decode().rstrip("="),
    }


def verify_exact_owner_release(
    signed: Mapping[str, Any], *, public_key: Ed25519PublicKey,
    expected_candidate_sha: str, expected_rollback_sha: str,
    expected_release_id: str, expected_scope_sha256: str,
    expected_manifest_sha256: str, expected_freeze_sha256: str,
    at: datetime, consumed_ids: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    if not isinstance(public_key, Ed25519PublicKey):
        raise OwnerReleaseProofDenied("OWNER_RELEASE_ROOT_TRUST_KEY_UNAVAILABLE")
    if (not isinstance(signed, Mapping)
            or set(signed) != {"payload", "signature_base64url"}
            or not isinstance(signed.get("payload"), Mapping)):
        raise OwnerReleaseProofDenied("OWNER_RELEASE_ENVELOPE_INVALID")
    payload = signed["payload"]
    _fields(payload)
    encoded = signed["signature_base64url"]
    if not isinstance(encoded, str) or SIGNATURE.fullmatch(encoded) is None:
        raise OwnerReleaseProofDenied("OWNER_RELEASE_SIGNATURE_MALFORMED")
    try:
        signature = base64.urlsafe_b64decode(encoded + "==")
        if len(signature) != 64:
            raise ValueError("signature length")
        public_key.verify(signature, canonical(payload))
    except (InvalidSignature, TypeError, ValueError) as exc:
        raise OwnerReleaseProofDenied("OWNER_RELEASE_SIGNATURE_INVALID") from exc
    if public_key_sha256(public_key) != payload["signer_public_key_sha256"]:
        raise OwnerReleaseProofDenied("OWNER_RELEASE_PUBLIC_KEY_DRIFT")
    try:
        issued = datetime.fromisoformat(payload["issued_at"])
        expires = datetime.fromisoformat(payload["expires_at"])
    except (TypeError, ValueError) as exc:
        raise OwnerReleaseProofDenied("OWNER_RELEASE_TIMES_INVALID") from exc
    if (at.tzinfo is None or issued.tzinfo is None or expires.tzinfo is None
            or not issued <= at < expires
            or expires - issued != MAX_AGE):
        raise OwnerReleaseProofDenied("OWNER_RELEASE_EXPIRED_OR_FUTURE")
    if any(payload[k] != expected for k, expected in (
        ("candidate_sha", expected_candidate_sha),
        ("rollback_sha", expected_rollback_sha),
        ("release_id", expected_release_id),
        ("scope_sha256", expected_scope_sha256),
        ("manifest_sha256", expected_manifest_sha256),
        ("freeze_sha256", expected_freeze_sha256),
    )):
        raise OwnerReleaseProofDenied("OWNER_RELEASE_TRANSACTION_BINDING_MISMATCH")
    if payload["approval_id"] in consumed_ids:
        raise OwnerReleaseProofDenied("OWNER_RELEASE_ONE_USE_REPLAY")
    if payload["decision"] != "approve":
        raise OwnerReleaseProofDenied("OWNER_RELEASE_DENIED")
    return dict(payload)


def read_pinned_root_owner_public_key(
    path: "Path", *, require_root_owned: bool = True,
) -> Ed25519PublicKey:
    """Read public-key policy; NEVER accept the signing key from a request.

    In production the host OS must provision the policy under a root-owned
    non-writable directory. Private signing material remains a separate
    service secret. The independently pinned public key is intentionally
    readable: it authenticates an Owner OAuth decision without a Teams card.
    """
    from pathlib import Path
    import stat
    p = Path(path)
    try:
        meta = p.lstat()
        raw = p.read_bytes()
        parent = p.parent.lstat()
    except OSError as exc:
        raise OwnerReleaseProofDenied("OWNER_RELEASE_ROOT_TRUST_UNAVAILABLE") from exc
    if (p.is_symlink() or not stat.S_ISREG(meta.st_mode)
            or p.parent.is_symlink() or not stat.S_ISDIR(parent.st_mode)
            or meta.st_mode & 0o022 or parent.st_mode & 0o022
            or (require_root_owned and (meta.st_uid != 0 or parent.st_uid != 0))
            or len(raw) > 4096):
        raise OwnerReleaseProofDenied("OWNER_RELEASE_ROOT_TRUST_UNSAFE")
    try:
        doc = json.loads(raw)
        expected = {
            "schema_version", "authorization", "organization_id",
            "tenant_id", "authorized_owner_subjects",
            "public_key_base64", "public_key_sha256",
            "standing_authority",
        }
        if not isinstance(doc, dict) or set(doc) != expected:
            raise ValueError("schema")
        if (doc["schema_version"] != "1.0"
                or doc["authorization"] != "authenticated_entra_owner_exact_release"
                or doc["organization_id"] != "aot"
                or doc["tenant_id"] != TID
                or doc["authorized_owner_subjects"] != [
                    {"owner_oid": oid, "owner_principal": principal}
                    for oid, principal in sorted(EXACT_OWNER_OAUTH_SUBJECTS.items())
                ]
                or doc["standing_authority"] is not False
                or not isinstance(doc["public_key_base64"], str)
                or not isinstance(doc["public_key_sha256"], str)
                or DIGEST.fullmatch(doc["public_key_sha256"]) is None):
            raise ValueError("identity")
        key_bytes = base64.b64decode(doc["public_key_base64"], validate=True)
        if len(key_bytes) != 32:
            raise ValueError("public key length")
        key = Ed25519PublicKey.from_public_bytes(key_bytes)
        if public_key_sha256(key) != doc["public_key_sha256"]:
            raise ValueError("trust digest")
        return key
    except (ValueError, TypeError, KeyError) as exc:
        raise OwnerReleaseProofDenied("OWNER_RELEASE_ROOT_TRUST_INVALID") from exc


def read_service_owner_signing_key(path: "Path") -> Ed25519PrivateKey:
    """Fetch a separately provisioned, private, non-symlink service key.

    Nothing in source generation creates, enables, or rotates a live key;
    provisioning requires an independently authorized root operation.
    """
    from pathlib import Path
    import os
    import stat
    p = Path(path)
    try:
        meta = p.lstat()
        raw = p.read_bytes()
    except OSError as exc:
        raise OwnerReleaseProofDenied("OWNER_RELEASE_SERVICE_SIGNER_UNAVAILABLE") from exc
    if (p.is_symlink() or not stat.S_ISREG(meta.st_mode)
            or stat.S_IMODE(meta.st_mode) != 0o400
            or meta.st_uid != os.geteuid() or len(raw) != 32):
        raise OwnerReleaseProofDenied("OWNER_RELEASE_SERVICE_SIGNER_UNSAFE")
    try:
        return Ed25519PrivateKey.from_private_bytes(raw)
    except (ValueError, TypeError) as exc:
        raise OwnerReleaseProofDenied("OWNER_RELEASE_SERVICE_SIGNER_INVALID") from exc
