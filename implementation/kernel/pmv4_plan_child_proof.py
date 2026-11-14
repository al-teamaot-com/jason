"""Proof type for a *derived* PMv4 bounded Owner plan step (source only).

Does not authorize execution or replace current root exact-Owner schema. This
distinct signature type intentionally cannot be mistaken for a freshly
authenticated Entra bearer or a current PMv3 production release approval.
The existing authenticated plan ledger/actor/step gates MUST run before issue;
the future root gate MUST independently verify the signed parent plan receipt,
policy, protected source, root breaker, freeze, health and one-use claim before
execution. No live issuer or root consumer calls these functions yet.
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import re
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)

from .signed_owner_release import (
    EXACT_OWNER_OAUTH_SUBJECTS, TID, canonical, public_key_sha256,
)

MAX_STEP_AGE = timedelta(minutes=15)
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_NAME = re.compile(r"[a-z][a-z0-9._:-]{2,119}\Z")
_PARENT = re.compile(r"planapproval-[0-9a-f-]{12,100}\Z")
_FIELDS = frozenset({
    "schema_version", "authorization", "authentication", "tenant_id",
    "owner_oid", "owner_principal", "organization_id", "parent_plan_id",
    "parent_approval_id", "parent_plan_fingerprint",
    "parent_authenticated_decision_sha256", "parent_plan_expires_at",
    "policy_digest", "step_index", "step_claim_id", "action",
    "candidate_sha", "rollback_sha", "scope_sha256", "artifact_sha256",
    "freeze_sha256", "hold_sha256", "issued_at", "expires_at",
    "one_step_only", "standing_authority", "signer_public_key_sha256",
})


class BoundedStepProofDenied(PermissionError):
    pass


def _validate(payload: Mapping[str, Any], *, at: datetime | None = None) -> None:
    if not isinstance(payload, Mapping) or frozenset(payload) != _FIELDS:
        raise BoundedStepProofDenied("PLAN_STEP_PROOF_SCHEMA_INVALID")
    if (payload["schema_version"] != "2.0"
            or payload["authorization"] != "verified_owner_bounded_plan_derived_step"
            or payload["authentication"] != "prior_authenticated_owner_plan"
            or payload["tenant_id"] != TID
            or payload["organization_id"] != "aot"
            or not isinstance(payload["owner_oid"], str)
            or payload["owner_oid"] not in EXACT_OWNER_OAUTH_SUBJECTS
            or payload["owner_principal"] != EXACT_OWNER_OAUTH_SUBJECTS.get(
                payload["owner_oid"]
            )
            or type(payload["step_index"]) is not int
            or not 0 <= payload["step_index"] <= 11
            or not isinstance(payload["parent_plan_id"], str)
            or _NAME.fullmatch(payload["parent_plan_id"]) is None
            or not isinstance(payload["parent_approval_id"], str)
            or _PARENT.fullmatch(payload["parent_approval_id"]) is None
            or not isinstance(payload["action"], str)
            or _NAME.fullmatch(payload["action"]) is None
            or payload["one_step_only"] is not True
            or type(payload["one_step_only"]) is not bool
            or payload["standing_authority"] is not False
            or type(payload["standing_authority"]) is not bool
            or any(not isinstance(payload[k], str)
                   or _HEX64.fullmatch(payload[k]) is None for k in (
                       "parent_plan_fingerprint", "parent_authenticated_decision_sha256",
                       "policy_digest", "scope_sha256", "artifact_sha256",
                       "freeze_sha256", "hold_sha256", "signer_public_key_sha256",
                       "step_claim_id",
                   ))
            or any(not isinstance(payload[k], str)
                   or _SHA40.fullmatch(payload[k]) is None
                   for k in ("candidate_sha", "rollback_sha"))):
        raise BoundedStepProofDenied("PLAN_STEP_PROOF_FIELDS_INVALID")
    claim = sha256(canonical({
        "parent_approval_id": payload["parent_approval_id"],
        "parent_plan_fingerprint": payload["parent_plan_fingerprint"],
        "step_index": payload["step_index"],
        "action": payload["action"],
    })).hexdigest()
    if payload["step_claim_id"] != claim:
        raise BoundedStepProofDenied("PLAN_STEP_PROOF_CLAIM_DRIFT")
    try:
        issued = datetime.fromisoformat(payload["issued_at"])
        expires = datetime.fromisoformat(payload["expires_at"])
        parent_expires = datetime.fromisoformat(payload["parent_plan_expires_at"])
    except (ValueError, TypeError) as exc:
        raise BoundedStepProofDenied("PLAN_STEP_PROOF_TIME_INVALID") from exc
    if (any(t.tzinfo is None or t.utcoffset() is None
            for t in (issued, expires, parent_expires))
            or expires - issued != MAX_STEP_AGE
            or not issued < parent_expires):
        raise BoundedStepProofDenied("PLAN_STEP_PROOF_LIFETIME_INVALID")
    if at is not None:
        if (at.tzinfo is None or at.utcoffset() is None
                or not issued <= at < expires
                or at >= parent_expires):
            raise BoundedStepProofDenied("PLAN_STEP_PROOF_EXPIRED_OR_FUTURE")


def issue_derived_step_proof(
    *, private_key: Ed25519PrivateKey, verified_owner_oid: str,
    parent_plan_id: str, parent_approval_id: str,
    parent_plan_fingerprint: str, parent_authenticated_decision_sha256: str,
    parent_plan_expires_at: datetime, policy_digest: str, step_index: int,
    action: str, candidate_sha: str, rollback_sha: str,
    scope_sha256: str, artifact_sha256: str,
    freeze_sha256: str, hold_sha256: str, at: datetime,
) -> dict[str, Any]:
    """Sign only *after* existing plan/identity/step reauthorization passes.

    No implicit grant is created here; the live caller is responsible for the
    original authenticated ledger receipt and independently verified values.
    """
    if (not isinstance(private_key, Ed25519PrivateKey)
            or not isinstance(at, datetime) or at.tzinfo is None
            or not isinstance(parent_plan_expires_at, datetime)
            or parent_plan_expires_at.tzinfo is None):
        raise BoundedStepProofDenied("PLAN_STEP_SIGNER_OR_CLOCK_INVALID")
    issued = at.astimezone(timezone.utc)
    payload = {
        "schema_version": "2.0",
        "authorization": "verified_owner_bounded_plan_derived_step",
        "authentication": "prior_authenticated_owner_plan",
        "tenant_id": TID,
        "owner_oid": verified_owner_oid,
        "owner_principal": EXACT_OWNER_OAUTH_SUBJECTS.get(verified_owner_oid),
        "organization_id": "aot",
        "parent_plan_id": parent_plan_id,
        "parent_approval_id": parent_approval_id,
        "parent_plan_fingerprint": parent_plan_fingerprint,
        "parent_authenticated_decision_sha256": parent_authenticated_decision_sha256,
        "parent_plan_expires_at": parent_plan_expires_at.isoformat(),
        "policy_digest": policy_digest,
        "step_index": step_index,
        "step_claim_id": sha256(canonical({
            "parent_approval_id": parent_approval_id,
            "parent_plan_fingerprint": parent_plan_fingerprint,
            "step_index": step_index,
            "action": action,
        })).hexdigest(),
        "action": action,
        "candidate_sha": candidate_sha,
        "rollback_sha": rollback_sha,
        "scope_sha256": scope_sha256,
        "artifact_sha256": artifact_sha256,
        "freeze_sha256": freeze_sha256,
        "hold_sha256": hold_sha256,
        "issued_at": issued.isoformat(),
        "expires_at": (issued + MAX_STEP_AGE).isoformat(),
        "one_step_only": True,
        "standing_authority": False,
        "signer_public_key_sha256": public_key_sha256(private_key.public_key()),
    }
    _validate(payload, at=issued)
    signature = private_key.sign(canonical(payload))
    return {
        "payload": payload,
        "signature_base64url": base64.urlsafe_b64encode(signature).decode().rstrip("="),
    }


def verify_derived_step_proof(
    signed: Mapping[str, Any], *, pinned_public_key: Ed25519PublicKey,
    expected: Mapping[str, Any], at: datetime,
    consumed_step_claims: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Cryptographic binding only; returns facts, NEVER root execution authority.

    The future root consumer MUST independently verify parent grant evidence
    from its protected source and the normal root release/health/rollback gates.
    """
    if (not isinstance(pinned_public_key, Ed25519PublicKey)
            or not isinstance(signed, Mapping)
            or frozenset(signed) != {"payload", "signature_base64url"}
            or not isinstance(signed.get("payload"), Mapping)):
        raise BoundedStepProofDenied("PLAN_STEP_PROOF_ENVELOPE_INVALID")
    payload = signed["payload"]
    _validate(payload, at=at)
    if (frozenset(expected) != frozenset(payload) - {
        "schema_version", "authorization", "authentication",
        "issued_at", "expires_at", "step_claim_id",
        "one_step_only", "standing_authority", "signer_public_key_sha256",
    } or any(payload[k] != v for k, v in expected.items())):
        raise BoundedStepProofDenied("PLAN_STEP_PROOF_EXACT_BINDING_CHANGED")
    if (public_key_sha256(pinned_public_key)
            != payload["signer_public_key_sha256"]):
        raise BoundedStepProofDenied("PLAN_STEP_PROOF_WRONG_ROOT_SIGNER")
    value = signed.get("signature_base64url")
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_-]{86}", value) is None:
        raise BoundedStepProofDenied("PLAN_STEP_PROOF_SIGNATURE_MALFORMED")
    try:
        signature = base64.urlsafe_b64decode(value + "==")
        if len(signature) != 64:
            raise ValueError("invalid Ed25519 signature length")
        pinned_public_key.verify(signature, canonical(payload))
    except (InvalidSignature, TypeError, ValueError) as exc:
        raise BoundedStepProofDenied("PLAN_STEP_PROOF_SIGNATURE_INVALID") from exc
    if payload["step_claim_id"] in consumed_step_claims:
        raise BoundedStepProofDenied("PLAN_STEP_PROOF_REPLAY")
    return dict(payload)
