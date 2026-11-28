"""Protected host V5 verification within the EXISTING release decision consumer.

A V5 decision cannot be projected as a V4 Teams decision. This verifies the
native read-only approval request, signed receipt, evidence digest, root trust,
tenant and signer. Promotion remains bound to an approved, installed V5 policy
and the existing protected release manager's CCC/freeze/rollback transaction.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from connectors.src.jason_connectors.approval_requests import (
    ApprovalRequestStatus, SQLiteApprovalRequestRepository,
)
from jason_mcp.entra_release_stepup import ExactRelease, ReleaseIdentityRoute
from tools.verify_browser_release_evidence import verify_pending_v5_admin_browser_decision


def verify_v5_browser_release_receipt(
    *, request: Any, response: dict[str, Any],
    envelope: dict[str, Any], evidence_sha256: str,
    exact_release: ExactRelease, route: ReleaseIdentityRoute,
    policy_version: str, policy_sha256: str,
    organization_id: str, owner_identity_ids: tuple[str, ...],
    root_trust_path: Path, now: datetime,
) -> dict[str, Any]:
    """Verify a native accepted decision; never grant release authority."""
    if policy_version != "5.0":
        raise PermissionError("root V5 browser release policy not approved")
    if (not isinstance(response, dict) or not isinstance(envelope, dict)
            or not isinstance(evidence_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", evidence_sha256) is None):
        raise PermissionError("V5 native receipt or evidence malformed")
    # Canonical signed bytes and digest are independently verified from
    # durable evidence, not recomputed from a caller's asserted hash alone.
    from jason_mcp.entra_release_browser_decision import _canonical
    actual_sha = sha256(_canonical(envelope)).hexdigest()
    if actual_sha != evidence_sha256:
        raise PermissionError("V5 signed evidence digest mismatch")
    if (getattr(request, "status", None) is not ApprovalRequestStatus.APPROVED
            or response.get("approval_id") != exact_release.approval_id
            or response.get("decision") != "approve"
            or response.get("channel") != "entra_browser_admin"
            or response.get("organization_id") != organization_id
            or response.get("approver_identity_id") not in owner_identity_ids
            or response.get("authentication_evidence_hash") != evidence_sha256
            or response.get("channel_response_id") != evidence_sha256):
        raise PermissionError("V5 signed release receipt is not exact native owner approval")
    try:
        timestamp = datetime.fromisoformat(response["decided_at"])
    except (ValueError, TypeError, KeyError) as exc:
        raise PermissionError("V5 native signed decision timestamp absent") from exc
    if (timestamp.tzinfo is None or
            timestamp != getattr(request, "decided_at", None) and
            getattr(request, "decided_at", None) is not None
            or not request.requested_at <= timestamp < request.expires_at
            or timestamp > now):
        raise PermissionError("V5 signed decision timestamp outside request TTL")
    # Attestor expects PENDING before ledger consumption. Reconstruct a
    # read-only snapshot with its original immutable fields, never mutate the
    # live approved request or its status/decision.
    from dataclasses import replace
    pending_snapshot = replace(request, status=ApprovalRequestStatus.PENDING)
    verified = verify_pending_v5_admin_browser_decision(
        request=pending_snapshot, envelope=envelope,
        exact_release=exact_release, route=route,
        policy_version=policy_version, policy_sha256=policy_sha256,
        organization_id=organization_id, owner_identity_ids=owner_identity_ids,
        root_trust_path=root_trust_path, now=timestamp,
    )
    if (verified.get("release_authorized") is not False
            or verified["signed_evidence_sha256"] != evidence_sha256
            or verified["decision"] != "approve"):
        raise PermissionError("V5 host evidence is not an independently signed approval")
    return {
        "status": "host_signed_browser_receipt_verified",
        "approval_id":exact_release.approval_id,
        "owner_identity_id":response["approver_identity_id"],
        "authenticated_admin_oid":verified["authenticated_admin_oid"],
        "signed_evidence_sha256":evidence_sha256,
        "candidate_sha":exact_release.candidate_sha,
        "rollback_sha":exact_release.rollback_sha,
        "manifest_sha256":exact_release.manifest_sha256,
        "scope_sha256":exact_release.scope_sha256,
        "decision_time":timestamp.isoformat(),
        "release_authorized":False,
        "ccc_attested":False,
        "production_changed":False,
    }
