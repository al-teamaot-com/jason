"""30-second signed current Owner-plan grant attestation (source only).

The universal-approval SQLite grant is UID1000-owned. A future root consumer
must never treat its raw unsigned grant or revoked=false value as authority.
A separately trusted, pinned signer must attest the CURRENT grant/revocation
record for each exact machine step. Root rechecks an independently root-owned
claim/revocation journal and native safety before any protected mutation.
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

from kernel.pmv4_plan_child_proof import (
    _parent_validation, verify_authenticated_owner_objective,
)
from kernel.signed_owner_release import canonical, public_key_sha256
from orchestrator.pmv4_objective_scope import (
    BoundedObjective, require_objective_step_conformance,
)


class PlanGrantAttestationDenied(PermissionError):
    pass


_ALLOWED = frozenset({
    "schema_version", "kind", "parent_signed_sha256", "parent_plan_id",
    "parent_approval_id", "parent_plan_fingerprint", "owner_oid",
    "policy_digest", "action_index", "action", "candidate_sha",
    "rollback_sha", "scope_sha256", "artifact_sha256",
    "freeze_sha256", "hold_sha256", "current_grant_status",
    "observed_at", "expires_at", "signer_public_key_sha256",
    "standing_authority", "one_plan_only",
})
_MAX_AGE = timedelta(seconds=30)
_SIGNATURE = re.compile(r"[A-Za-z0-9_-]{86}\Z")


def _valid_signature(signed: Mapping[str, Any], *, key: Ed25519PublicKey) -> None:
    if (not isinstance(signed, Mapping)
            or set(signed) != {"payload", "signature_base64url"}
            or not isinstance(signed["payload"], Mapping)
            or not isinstance(signed["signature_base64url"], str)
            or not _SIGNATURE.fullmatch(signed["signature_base64url"])):
        raise PlanGrantAttestationDenied("OWNER_PLAN_ATTESTATION_ENVELOPE_UNTRUSTED")
    try:
        signature = base64.urlsafe_b64decode(signed["signature_base64url"] + "==")
        if len(signature) != 64:
            raise ValueError("signature length")
        key.verify(signature, canonical(signed["payload"]))
    except (InvalidSignature, ValueError, TypeError) as exc:
        raise PlanGrantAttestationDenied("OWNER_PLAN_ATTESTATION_SIGNATURE_INVALID") from exc


def issue_current_grant_attestation(
    *, objective: BoundedObjective, signed_parent: Mapping[str, Any],
    ledger: Any, signer_private_key: Ed25519PrivateKey,
    pinned_public_key: Ed25519PublicKey, action_index: int,
    at: datetime, production: bool = False,
) -> dict[str, Any]:
    """Source-only issuer: NO human interaction and NO production permissions."""
    if production:
        raise PlanGrantAttestationDenied("OWNER_PLAN_ROOT_ATTESTOR_NOT_DEPLOYED")
    if (not isinstance(objective, BoundedObjective)
            or not isinstance(signer_private_key, Ed25519PrivateKey)
            or not isinstance(pinned_public_key, Ed25519PublicKey)
            or public_key_sha256(signer_private_key.public_key())
               != public_key_sha256(pinned_public_key)
            or type(action_index) is not int
            or not 0 <= action_index < len(objective.actions)
            or not isinstance(at, datetime) or at.tzinfo is None):
        raise PlanGrantAttestationDenied("OWNER_PLAN_ATTESTOR_TRUST_REQUIRED")
    parent = verify_authenticated_owner_objective(
        signed_parent, objective=objective, pinned_public_key=pinned_public_key,
        ledger=ledger, at=at,
    )
    action = objective.actions[action_index]
    require_objective_step_conformance(
        ledger=ledger, objective=objective,
        approved_fingerprint=objective.fingerprint,
        action_index=action_index, observed_candidate_sha=objective.candidate_sha,
        observed_rollback_sha=objective.rollback_sha,
        observed_freeze_sha256=objective.freeze_sha256,
        observed_hold_sha256=objective.hold_sha256,
        observed_scope_sha256=action.scope_sha256,
        observed_artifact_sha256=action.artifact_sha256,
        now=at,
    )
    observed = at.astimezone(timezone.utc)
    expires = min(observed + _MAX_AGE, objective.expires_at)
    if expires <= observed:
        raise PlanGrantAttestationDenied("OWNER_PLAN_ATTESTOR_OBJECTIVE_EXPIRED")
    payload = {
        "schema_version": "1.0", "kind": "current-enrolled-unrevoked-owner-plan",
        "parent_signed_sha256": sha256(canonical(signed_parent)).hexdigest(),
        "parent_plan_id": objective.plan_id,
        "parent_approval_id": parent["parent_approval_id"],
        "parent_plan_fingerprint": objective.fingerprint,
        "owner_oid": parent["owner_oid"],
        "policy_digest": objective.policy_digest,
        "action_index": action_index, "action": action.capability,
        "candidate_sha": objective.candidate_sha,
        "rollback_sha": objective.rollback_sha,
        "scope_sha256": action.scope_sha256,
        "artifact_sha256": action.artifact_sha256,
        "freeze_sha256": objective.freeze_sha256,
        "hold_sha256": objective.hold_sha256,
        "current_grant_status": "confirmed_active_and_not_revoked",
        "observed_at": observed.isoformat(), "expires_at": expires.isoformat(),
        "signer_public_key_sha256": public_key_sha256(pinned_public_key),
        "standing_authority": False, "one_plan_only": True,
    }
    return {
        "payload": payload,
        "signature_base64url": base64.urlsafe_b64encode(
            signer_private_key.sign(canonical(payload))
        ).decode("ascii").rstrip("="),
    }


def verify_current_grant_attestation(
    *, objective: BoundedObjective, signed_parent: Mapping[str, Any],
    signed_attestation: Mapping[str, Any],
    pinned_public_key: Ed25519PublicKey,
    expected_action_index: int, at: datetime,
    production: bool = False,
) -> dict[str, Any]:
    """Cryptographic read-only verifier, NEVER an executable root approval."""
    if production:
        raise PlanGrantAttestationDenied("OWNER_PLAN_ROOT_CONSUMER_NOT_DEPLOYED")
    if (not isinstance(objective, BoundedObjective)
            or not isinstance(pinned_public_key, Ed25519PublicKey)
            or not isinstance(signed_parent, Mapping)
            or not isinstance(signed_attestation, Mapping)
            or type(expected_action_index) is not int
            or not 0 <= expected_action_index < len(objective.actions)
            or not isinstance(at, datetime) or at.tzinfo is None):
        raise PlanGrantAttestationDenied("OWNER_PLAN_ATTESTATION_INVALID_ARGUMENTS")
    # Do not trust raw operator DB: verify actual parent and current-status
    # signatures using the independently pinned root Owner public key.
    _valid_signature(signed_parent, key=pinned_public_key)
    parent = signed_parent["payload"]
    _parent_validation(parent, at=at)
    if (parent.get("reviewed_objective") != objective.review_material()
            or parent.get("parent_plan_fingerprint") != objective.fingerprint
            or parent.get("signer_public_key_sha256")
               != public_key_sha256(pinned_public_key)):
        raise PlanGrantAttestationDenied("OWNER_PLAN_ATTESTATION_PARENT_CHANGED")
    _valid_signature(signed_attestation, key=pinned_public_key)
    payload = signed_attestation["payload"]
    action = objective.actions[expected_action_index]
    expected = {
        "schema_version": "1.0", "kind": "current-enrolled-unrevoked-owner-plan",
        "parent_signed_sha256": sha256(canonical(signed_parent)).hexdigest(),
        "parent_plan_id": objective.plan_id,
        "parent_approval_id": parent["parent_approval_id"],
        "parent_plan_fingerprint": objective.fingerprint,
        "owner_oid": parent["owner_oid"],
        "policy_digest": objective.policy_digest,
        "action_index": expected_action_index, "action": action.capability,
        "candidate_sha": objective.candidate_sha,
        "rollback_sha": objective.rollback_sha,
        "scope_sha256": action.scope_sha256,
        "artifact_sha256": action.artifact_sha256,
        "freeze_sha256": objective.freeze_sha256,
        "hold_sha256": objective.hold_sha256,
        "current_grant_status": "confirmed_active_and_not_revoked",
        "signer_public_key_sha256": public_key_sha256(pinned_public_key),
        "standing_authority": False, "one_plan_only": True,
    }
    if (set(payload) != _ALLOWED
            or any(payload.get(k) != v for k, v in expected.items())):
        raise PlanGrantAttestationDenied("OWNER_PLAN_ATTESTATION_SCOPE_CHANGED")
    try:
        observed = datetime.fromisoformat(payload["observed_at"])
        expires = datetime.fromisoformat(payload["expires_at"])
    except (TypeError, KeyError, ValueError) as exc:
        raise PlanGrantAttestationDenied("OWNER_PLAN_ATTESTATION_TIME_INVALID") from exc
    if (observed.tzinfo is None or expires.tzinfo is None
            or not observed <= at < expires
            or not timedelta(0) < expires - observed <= _MAX_AGE
            or expires > objective.expires_at):
        raise PlanGrantAttestationDenied("OWNER_PLAN_ATTESTATION_STALE_OR_EXPIRED")
    return {
        "status": "cryptographically_verified_current_plan_no_root_authority",
        "parent_approval_id": parent["parent_approval_id"],
        "plan_fingerprint": objective.fingerprint,
        "step_index": expected_action_index,
        "assertion_sha256": sha256(canonical(signed_attestation)).hexdigest(),
        "no_root_mutation": True,
    }
