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
import json
import re
from typing import Any, Callable, Mapping

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


# This extends the existing Owner Ed25519 signer with one authenticated PARENT
# objective receipt. It is not an alternate signer or production release policy.
_ENTRA_ISSUER = "https://login.microsoftonline.com/" + TID + "/v2.0"
_ENTRA_AUDIENCE = "9b9996e9-5c34-48b7-948c-f44f89352f89"
_MAX_PARENT_LIFETIME = timedelta(hours=24)
_PARENT_FIELDS = frozenset({
    "schema_version", "authorization", "authentication", "decision",
    "tenant_id", "owner_oid", "owner_principal", "organization_id",
    "parent_plan_id", "parent_approval_id", "parent_plan_fingerprint",
    "reviewed_objective", "policy_digest", "issued_at", "expires_at",
    "identity_evidence_sha256", "signer_public_key_sha256",
    "standing_authority", "one_plan_only",
})


def _parent_validation(
    payload: Mapping[str, Any], *, at: datetime,
) -> None:
    """Recompute the reviewed full manifest digest; deny partial signatures."""
    if (not isinstance(payload, Mapping) or set(payload) != _PARENT_FIELDS
            or payload["schema_version"] != "2.0"
            or payload["authorization"] != "verified_entra_owner_bounded_plan"
            or payload["authentication"] != "verified_entra_oauth_bearer"
            or payload["decision"] != "approve"
            or payload["tenant_id"] != TID or payload["organization_id"] != "aot"
            or not isinstance(payload["owner_oid"], str)
            or payload["owner_oid"] not in EXACT_OWNER_OAUTH_SUBJECTS
            or payload["owner_principal"] != EXACT_OWNER_OAUTH_SUBJECTS.get(
                payload["owner_oid"])
            or type(payload["standing_authority"]) is not bool
            or payload["standing_authority"] is not False
            or type(payload["one_plan_only"]) is not bool
            or payload["one_plan_only"] is not True
            or not isinstance(payload["parent_plan_id"], str)
            or _NAME.fullmatch(payload["parent_plan_id"]) is None
            or not isinstance(payload["parent_approval_id"], str)
            or _PARENT.fullmatch(payload["parent_approval_id"]) is None
            or any(not isinstance(payload[k], str)
                   or _HEX64.fullmatch(payload[k]) is None for k in (
                       "policy_digest", "parent_plan_fingerprint",
                       "identity_evidence_sha256", "signer_public_key_sha256",
                   ))
            or not isinstance(payload["reviewed_objective"], dict)):
        raise BoundedStepProofDenied("OWNER_PLAN_RECEIPT_FIELDS_INVALID")
    material = payload["reviewed_objective"]
    if (material.get("schema_version") != "1.0"
            or material.get("organization_id") != "aot"
            or material.get("plan_id") != payload["parent_plan_id"]
            or material.get("policy_digest") != payload["policy_digest"]
            or not isinstance(material.get("actions"), list)
            or not 1 <= len(material["actions"]) <= 12):
        raise BoundedStepProofDenied("OWNER_PLAN_REVIEWED_MANIFEST_INVALID")
    original = sha256(json.dumps(
        material, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")).hexdigest()
    if original != payload["parent_plan_fingerprint"]:
        raise BoundedStepProofDenied("OWNER_PLAN_MANIFEST_DIGEST_DRIFT")
    try:
        issued = datetime.fromisoformat(payload["issued_at"])
        expires = datetime.fromisoformat(payload["expires_at"])
        manifest_expires = datetime.fromisoformat(material["expires_at"])
    except (TypeError, ValueError, KeyError) as exc:
        raise BoundedStepProofDenied("OWNER_PLAN_TIME_INVALID") from exc
    if (any(x.tzinfo is None or x.utcoffset() is None
            for x in (at, issued, expires, manifest_expires))
            or not issued <= at < expires
            or expires != manifest_expires
            or not timedelta(0) < expires - issued <= _MAX_PARENT_LIFETIME):
        raise BoundedStepProofDenied("OWNER_PLAN_EXPIRED_OR_INVALID_LIFETIME")


def issue_authenticated_owner_objective(
    *, objective: Any, ledger: Any, approval_id: str,
    bearer_token: str,
    verify_entra_bearer: Callable[[str], Mapping[str, Any] | None],
    exact_owner_consent: Callable[[Mapping[str, Any]], bool],
    protected_main_check: Callable[[str], bool],
    signer_private_key: Ed25519PrivateKey, at: datetime,
) -> dict[str, Any]:
    """ONE actual Owner decision to approve a full bounded, immutable plan.

    The signed OAuth bearer must already be independently verified by the
    trusted caller callback (e.g. the existing MCP Entra verifier). The callback
    only returns verified claims, not user-supplied JSON. The Owner sees and
    approves exactly the full immutable review manifest once. Store human grant
    and signed parent proof in the EXISTING PlanGrantLedger atomically.

    Source-only interface. Not reachable from production and cannot bypass the
    current exact-revision release rule or mint root-action authority.
    """
    from orchestrator.approval_plan_scope import ApprovedPlanScope
    from orchestrator.approval_plan_grants import VerifiedPlanDecision
    from orchestrator.pmv4_objective_scope import BoundedObjective

    if (not isinstance(objective, BoundedObjective)
            or objective.organization_id != "aot"
            or not isinstance(approval_id, str)
            or _PARENT.fullmatch(approval_id) is None
            or not isinstance(signer_private_key, Ed25519PrivateKey)
            or not isinstance(bearer_token, str)
            or len(bearer_token) < 16
            or not isinstance(at, datetime) or at.tzinfo is None
            or any(not callable(v) for v in (
                verify_entra_bearer, exact_owner_consent, protected_main_check,
            ))):
        raise BoundedStepProofDenied("OWNER_PLAN_EXACT_PRINCIPAL_OR_SCOPE_REQUIRED")
    if protected_main_check(objective.candidate_sha) is not True:
        raise BoundedStepProofDenied("OWNER_PLAN_PROTECTED_MAIN_UNVERIFIED")
    try:
        claims = verify_entra_bearer(bearer_token)
    except (ValueError, TypeError, RuntimeError, OSError, PermissionError) as exc:
        raise BoundedStepProofDenied("OWNER_PLAN_ENTRA_VERIFIER_FAILURE") from exc
    seconds = int(at.timestamp())
    if (not isinstance(claims, Mapping)
            or claims.get("tid") != TID
            or claims.get("iss") != _ENTRA_ISSUER
            or claims.get("aud") != _ENTRA_AUDIENCE
            or not isinstance(claims.get("oid"), str)
            or claims["oid"] not in EXACT_OWNER_OAUTH_SUBJECTS
            or any(type(claims.get(field)) is not int for field in (
                "iat", "nbf", "exp"))
            or not claims["iat"] <= seconds < claims["exp"]
            or not claims["nbf"] <= seconds
            or seconds - claims["iat"] > 900):
        raise BoundedStepProofDenied("OWNER_PLAN_ENTRA_OWNER_CLAIMS_DENIED")
    # Recover the identical, still-valid verified decision without presenting
    # a second human approval. Re-authenticate the caller first, then check
    # immutable signed evidence, Owner OID and current grant/revocation.
    prior = ledger.authenticated_owner_objective_receipt(
        plan_id=objective.plan_id, approval_id=approval_id,
    )
    if prior is not None:
        already = verify_authenticated_owner_objective(
            prior, objective=objective,
            pinned_public_key=signer_private_key.public_key(),
            at=at, ledger=ledger,
        )
        if already["owner_oid"] != claims["oid"]:
            raise BoundedStepProofDenied("OWNER_PLAN_RECOVERY_OWNER_IDENTITY_CHANGED")
        return prior
    scope = ApprovedPlanScope(
        objective.plan_id, objective.organization_id,
        objective.policy_digest,
        frozenset(a.capability for a in objective.actions),
        frozenset(), max(a.risk for a in objective.actions),
        True, objective.expires_at,
    )
    review = objective.review_material()
    presented = {
        "service": "pmv4-bounded-owner-objective",
        "approval_id": approval_id,
        "owner_principal": EXACT_OWNER_OAUTH_SUBJECTS[claims["oid"]],
        "plan_fingerprint": objective.fingerprint,
        "full_reviewed_objective": review,
    }
    if exact_owner_consent(presented) is not True:
        raise BoundedStepProofDenied("OWNER_PLAN_EXACT_CONSENT_DENIED")
    claims_digest = sha256(canonical({
        k: claims[k] for k in ("tid", "iss", "aud", "oid", "iat", "nbf", "exp")
    })).hexdigest()
    payload = {
        "schema_version": "2.0",
        "authorization": "verified_entra_owner_bounded_plan",
        "authentication": "verified_entra_oauth_bearer",
        "decision": "approve",
        "tenant_id": TID, "owner_oid": claims["oid"],
        "owner_principal": EXACT_OWNER_OAUTH_SUBJECTS[claims["oid"]],
        "organization_id": "aot",
        "parent_plan_id": objective.plan_id,
        "parent_approval_id": approval_id,
        "parent_plan_fingerprint": objective.fingerprint,
        "reviewed_objective": review,
        "policy_digest": objective.policy_digest,
        "issued_at": at.isoformat(),
        "expires_at": objective.expires_at.isoformat(),
        "identity_evidence_sha256": claims_digest,
        "signer_public_key_sha256": public_key_sha256(
            signer_private_key.public_key()),
        "standing_authority": False,
        "one_plan_only": True,
    }
    _parent_validation(payload, at=at)
    signed = {
        "payload": payload,
        "signature_base64url": base64.urlsafe_b64encode(
            signer_private_key.sign(canonical(payload))
        ).decode("ascii").rstrip("="),
    }
    decision = VerifiedPlanDecision(
        approval_id=approval_id,
        approver_identity_id=payload["owner_principal"],
        authenticated=True, authorized=True, approved=True,
        plan_fingerprint=objective.fingerprint, decided_at=at,
    )
    ledger.record_authenticated_owner_objective(scope, decision, signed)
    return signed


def verify_authenticated_owner_objective(
    signed: Mapping[str, Any], *, objective: Any,
    pinned_public_key: Ed25519PublicKey, at: datetime,
    ledger: Any,
) -> dict[str, Any]:
    """Independent signature + exact manifest + mandatory current grant readback.

    In production the root caller must ALSO enforce its independently trusted
    root health/readback, current Owner binding, policy and revocation evidence.
    """
    from orchestrator.pmv4_objective_scope import BoundedObjective
    from orchestrator.approval_plan_scope import ProposedPlanStep

    if (not isinstance(objective, BoundedObjective)
            or not isinstance(pinned_public_key, Ed25519PublicKey)
            or not isinstance(signed, Mapping)
            or set(signed) != {"payload", "signature_base64url"}
            or not isinstance(signed.get("payload"), Mapping)):
        raise BoundedStepProofDenied("OWNER_PLAN_SIGNED_ENVELOPE_INVALID")
    payload = signed["payload"]
    _parent_validation(payload, at=at)
    if (payload["reviewed_objective"] != objective.review_material()
            or payload["parent_plan_fingerprint"] != objective.fingerprint
            or public_key_sha256(pinned_public_key) != payload["signer_public_key_sha256"]):
        raise BoundedStepProofDenied("OWNER_PLAN_REVIEWED_MATERIAL_CHANGED")
    signature = signed.get("signature_base64url")
    if not isinstance(signature, str) or re.fullmatch(
        r"[A-Za-z0-9_-]{86}", signature,
    ) is None:
        raise BoundedStepProofDenied("OWNER_PLAN_SIGNATURE_MALFORMED")
    try:
        decoded = base64.urlsafe_b64decode(signature + "==")
        if len(decoded) != 64:
            raise ValueError("invalid Ed25519 signature length")
        pinned_public_key.verify(decoded, canonical(payload))
    except (InvalidSignature, TypeError, ValueError) as exc:
        raise BoundedStepProofDenied("OWNER_PLAN_SIGNATURE_INVALID") from exc
    if ledger is None:
        raise BoundedStepProofDenied("OWNER_PLAN_CURRENT_GRANT_REQUIRED")
    if ledger is not None:
        record = ledger.authenticated_owner_objective_receipt(
            plan_id=objective.plan_id,
            approval_id=payload["parent_approval_id"],
        )
        if record != signed:
            raise BoundedStepProofDenied("OWNER_PLAN_DURABLE_RECEIPT_MISSING_OR_CHANGED")
        first = objective.actions[0]
        ledger.require_grant(
            ProposedPlanStep(
                objective.plan_id, objective.organization_id,
                objective.policy_digest, first.capability, None,
                first.risk, True,
            ), plan_fingerprint=objective.fingerprint, now=at,
        )
        stored = ledger.decision_receipt(payload["parent_approval_id"])
        if (stored is None
                or stored["approver_identity_id"] != payload["owner_principal"]
                or stored["plan_fingerprint"] != objective.fingerprint
                or stored["revoked_at"] is not None):
            raise BoundedStepProofDenied("OWNER_PLAN_DURABLE_ACTOR_MISMATCH")
    return dict(payload)
