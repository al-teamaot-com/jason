"""V5 signed admin-browser release decision for the EXISTING approval ledger.

This does not grant standing or production authority. The root host verifier
must independently validate this signature, exact pending request, reviewed
source scope, CA evidence, freeze and rollback before Release Manager action.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import base64
import json
import re
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization

from .release_v5_aot_policy import (
    CHANNEL, AotV5BrowserPolicy,
)
from .mobile_release_approval import MobileReleasePolicy


APPROVAL_RE = re.compile(r"^relapproval-[0-9a-f]{32}$")
HEX_SHA = re.compile(r"^[0-9a-f]{64}$")


def _canonical(data: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(data), sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def public_key_fingerprint(key: Ed25519PublicKey) -> str:
    raw = key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return sha256(raw).hexdigest()


def _read_exact_request(request: Any, policy: MobileReleasePolicy,
                        when: datetime,
                        *, allow_terminal: bool = False) -> tuple[str, str]:
    if (policy.schema_version != "5.0"
            or not isinstance(policy.browser_policy, AotV5BrowserPolicy)
            or policy.admin_approver_binding != (policy.browser_policy.tenant_id, policy.browser_policy.admin_approver_oid)
            or policy.regular_requester_binding != (policy.browser_policy.tenant_id, policy.browser_policy.requester_oid)
            or when.tzinfo is None
            or request.requested_at.tzinfo is None
            or not request.requested_at <= when < request.expires_at
            or str(getattr(request.status,"value",request.status))
               not in ({"pending","approved","denied"} if allow_terminal
                       else {"pending"})
            or request.organization_id != policy.organization_id
            or request.capability != "release.production.approve"
            or request.authorized_approver_ids != policy.owner_identity_ids
            or request.requested_by != "svc-jason-release-manager"
            or not APPROVAL_RE.fullmatch(request.approval_id)
            or request.metadata.get("owner_policy_sha256") != policy.policy_sha256
            or request.metadata.get("approval_channel") != CHANNEL
            or request.metadata.get("admin_approver_entra_oid") != policy.browser_policy.admin_approver_oid
            or request.metadata.get("notice_to_entra_oid") != policy.browser_policy.requester_oid):
        raise PermissionError("V5_BROWSER_RELEASE_REQUEST_NOT_AUTHORIZED")
    scope = request.metadata.get("scope_sha256")
    manifest = request.metadata.get("manifest_sha256")
    if (not isinstance(scope, str) or not HEX_SHA.fullmatch(scope)
            or not isinstance(manifest,str) or not HEX_SHA.fullmatch(manifest)):
        raise PermissionError("V5_BROWSER_RELEASE_IMMUTABLE_SCOPE_MISSING")
    return scope, manifest


def sign_browser_release_decision(
    *, request: Any, policy: MobileReleasePolicy,
    authenticated_admin_proof: Mapping[str, Any],
    ca_policy_receipt_sha256: str, decision: str,
    when: datetime, private_key: Ed25519PrivateKey,
) -> dict[str, Any]:
    """Attest an explicit admin browser action; never sign normal Teams input."""
    scope, manifest = _read_exact_request(request, policy, when)
    if (decision not in ("approve","deny")
            or not isinstance(private_key, Ed25519PrivateKey)
            or ca_policy_receipt_sha256 != policy.browser_policy.ca_enforcement_receipt_sha256
            or authenticated_admin_proof.get("release_authorized") is not False
            or authenticated_admin_proof.get("channel") != CHANNEL
            or authenticated_admin_proof.get("tenant_id") != policy.browser_policy.tenant_id
            or authenticated_admin_proof.get("authenticated_admin_oid") != policy.browser_policy.admin_approver_oid
            or authenticated_admin_proof.get("approval_id") != request.approval_id
            or authenticated_admin_proof.get("candidate_sha") != request.metadata.get("candidate_sha")
            or authenticated_admin_proof.get("rollback_sha") != request.metadata.get("rollback_sha")
            or authenticated_admin_proof.get("scope_sha256") != scope
            or authenticated_admin_proof.get("manifest_sha256") != manifest):
        raise PermissionError("V5_ADMIN_BROWSER_PROOF_NOT_EXACT")
    digest = authenticated_admin_proof.get("evidence_sha256")
    auth_time = authenticated_admin_proof.get("auth_time")
    if (not isinstance(digest,str) or not HEX_SHA.fullmatch(digest)
            or type(auth_time) is not int
            or not 0 <= when.timestamp() - auth_time <= 300):
        raise PermissionError("V5_FRESH_ADMIN_AUTHENTICATION_REQUIRED")
    public_key = private_key.public_key()
    key_fp = public_key_fingerprint(public_key)
    if key_fp != policy.browser_policy.signer_public_key_sha256:
        raise PermissionError("V5_REVIEWED_SIGNING_KEY_MISMATCH")
    payload = {
        "schema_version":"5.0",
        "channel":CHANNEL,
        "approval_id":request.approval_id,
        "decision":decision,
        "organization_id":request.organization_id,
        "owner_identity_id":policy.owner_identity_ids[0],
        "tenant_id":policy.browser_policy.tenant_id,
        "authenticated_admin_oid":policy.browser_policy.admin_approver_oid,
        "notice_recipient_oid":policy.browser_policy.requester_oid,
        "release_id":request.metadata.get("release_id"),
        "candidate_sha":request.metadata.get("candidate_sha"),
        "rollback_sha":request.metadata.get("rollback_sha"),
        "scope_sha256":scope,
        "manifest_sha256":manifest,
        "owner_policy_sha256":policy.policy_sha256,
        "ca_policy_receipt_sha256":ca_policy_receipt_sha256,
        "auth_evidence_sha256":digest,
        "auth_time":auth_time,
        "requested_at":request.requested_at.isoformat(),
        "expires_at":request.expires_at.isoformat(),
        "decided_at":when.isoformat(),
        "public_key_sha256":key_fp,
        "single_transaction":True,
        "standing_authority":False,
    }
    signature = private_key.sign(_canonical(payload))
    return {
        "payload":payload,
        "signature_base64url":base64.urlsafe_b64encode(signature).decode().rstrip("="),
    }


def verify_browser_release_decision(
    *, signed: Mapping[str, Any], request: Any, policy: MobileReleasePolicy,
    public_key: Ed25519PublicKey, now: datetime,
) -> dict[str, Any]:
    """Root-side signature and exact request check, not production approval."""
    if not isinstance(signed, Mapping) or set(signed) != {
        "payload","signature_base64url"
    } or not isinstance(signed.get("payload"),Mapping):
        raise PermissionError("V5_SIGNED_BROWSER_EVIDENCE_FORMAT_INVALID")
    payload = signed["payload"]
    if not isinstance(public_key,Ed25519PublicKey):
        raise PermissionError("V5_SIGNED_BROWSER_PUBLIC_KEY_INVALID")
    try:
        sig = signed["signature_base64url"]
        if not isinstance(sig,str) or re.fullmatch(r"[A-Za-z0-9_-]{86}",sig) is None:
            raise ValueError("invalid signature encoding")
        signature=base64.urlsafe_b64decode(sig + "==")
        public_key.verify(signature,_canonical(payload))
    except (InvalidSignature,ValueError,TypeError) as exc:
        raise PermissionError("V5_SIGNED_BROWSER_SIGNATURE_INVALID") from exc
    decided = payload.get("decided_at")
    if type(decided) is not str:
        raise PermissionError("V5_BROWSER_DECISION_TIMESTAMP_INVALID")
    try:
        moment = datetime.fromisoformat(decided)
    except ValueError as exc:
        raise PermissionError("V5_BROWSER_DECISION_TIMESTAMP_INVALID") from exc
    _read_exact_request(request,policy,moment,allow_terminal=True)
    state=str(getattr(request.status,"value",request.status))
    if state!="pending" and state!=(
        "approved" if payload.get("decision")=="approve" else "denied"
    ):
        raise PermissionError("V5_SIGNED_BROWSER_TERMINAL_STATUS_MISMATCH")
    expected = {
        "schema_version":"5.0",
        "channel":CHANNEL,
        "approval_id":request.approval_id,
        "organization_id":policy.organization_id,
        "owner_identity_id":policy.owner_identity_ids[0],
        "tenant_id":policy.browser_policy.tenant_id,
        "authenticated_admin_oid":policy.browser_policy.admin_approver_oid,
        "notice_recipient_oid":policy.browser_policy.requester_oid,
        "release_id":request.metadata.get("release_id"),
        "candidate_sha":request.metadata.get("candidate_sha"),
        "rollback_sha":request.metadata.get("rollback_sha"),
        "scope_sha256":request.metadata.get("scope_sha256"),
        "manifest_sha256":request.metadata.get("manifest_sha256"),
        "owner_policy_sha256":policy.policy_sha256,
        "ca_policy_receipt_sha256":policy.browser_policy.ca_enforcement_receipt_sha256,
        "requested_at":request.requested_at.isoformat(),
        "expires_at":request.expires_at.isoformat(),
        "public_key_sha256":policy.browser_policy.signer_public_key_sha256,
        "single_transaction":True,
        "standing_authority":False,
    }
    if (set(payload) != set(expected)|{
            "decision","auth_evidence_sha256","auth_time","decided_at"
            }
            or any(payload.get(k)!=v for k,v in expected.items())
            or payload.get("decision") not in {"approve","deny"}
            or not isinstance(payload.get("auth_evidence_sha256"),str)
            or not HEX_SHA.fullmatch(payload["auth_evidence_sha256"])
            or type(payload.get("auth_time")) is not int
            or moment.tzinfo is None or now.tzinfo is None
            or not request.requested_at <= moment <= now < request.expires_at
            or not 0 <= moment.timestamp()-payload["auth_time"] <= 300
            or now-moment > __import__("datetime").timedelta(minutes=15)
            or public_key_fingerprint(public_key)
                != policy.browser_policy.signer_public_key_sha256):
        raise PermissionError("V5_SIGNED_BROWSER_RELEASE_SCOPE_MISMATCH")
    # The host must additionally validate protected CA attestation, native
    # freeze, current production SHA, CCC and any signed owner-unfreeze receipt.
    return dict(payload)
