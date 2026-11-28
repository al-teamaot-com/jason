"""Source-only V5 host attestor for the EXISTING Jason ApprovalRequestService.

This is intentionally NOT another host release approval mechanism.
It supplies independent signed evidence validation to the protected
consumer AFTER a separately reviewed V5 root policy is installed.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import hmac
import re
from typing import Any, Mapping

from kernel.entra_release_root_trust import read_root_browser_release_trust
from jason_mcp.entra_release_stepup import ExactRelease, ReleaseIdentityRoute
from jason_mcp.entra_release_browser_decision import verify_browser_decision_envelope

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_APPROVAL = re.compile(r"^relapproval-[0-9a-f]{32}$")


class V5BrowserHostAttestationDenied(PermissionError):
    pass


def verify_pending_v5_admin_browser_decision(
    *, request: Any, envelope: Mapping[str, Any], exact_release: ExactRelease,
    route: ReleaseIdentityRoute, policy_version: str,
    policy_sha256: str, organization_id: str,
    owner_identity_ids: tuple[str, ...],
    root_trust_path: Path, now: datetime,
) -> dict[str, Any]:
    """Attest existing pending request WITHOUT mutating its approval state."""
    # The host cannot accept a V4 Teams grant as a V5 browser decision.
    if policy_version != "5.0":
        raise V5BrowserHostAttestationDenied("V5_EXPLICIT_APPROVAL_POLICY_REQUIRED")
    if (not isinstance(policy_sha256, str) or not _SHA64.fullmatch(policy_sha256)
            or not isinstance(organization_id, str) or not organization_id
            or not isinstance(owner_identity_ids, tuple)
            or len(owner_identity_ids) != 1 or not owner_identity_ids[0]):
        raise V5BrowserHostAttestationDenied("V5_ROOT_POLICY_NOT_REVIEWED")
    route.validate()
    exact_release.validate()
    if (request is None or getattr(request, "status", None) is None
            or str(getattr(request.status, "value", "")) != "pending"
            or getattr(request, "approval_id", None) != exact_release.approval_id
            or getattr(request, "requested_by", None) != "svc-jason-release-manager"
            or getattr(request, "capability", None) != "release.production.approve"
            or getattr(request, "organization_id", None) != organization_id
            or getattr(request, "client_id", None) is not None
            or getattr(request, "authorized_approver_ids", None) != owner_identity_ids):
        raise V5BrowserHostAttestationDenied("V5_EXISTING_APPROVAL_NOT_AUTHORIZED")
    if (getattr(request, "requested_at", None) is None
            or request.requested_at.tzinfo is None
            or getattr(request, "expires_at", None) != exact_release.expires_at
            or now.tzinfo is None
            or not request.requested_at <= now < request.expires_at):
        raise V5BrowserHostAttestationDenied("V5_APPROVAL_TTL_OR_TIMING_INVALID")
    metadata = getattr(request, "metadata", None)
    if not isinstance(metadata, dict):
        raise V5BrowserHostAttestationDenied("V5_APPROVAL_METADATA_MISSING")
    expected = {
        "candidate_sha": exact_release.candidate_sha,
        "rollback_sha": exact_release.rollback_sha,
        "manifest_sha256": exact_release.manifest_sha256,
        "scope_sha256": exact_release.scope_sha256,
        "owner_policy_sha256": policy_sha256,
    }
    for field, value in expected.items():
        if metadata.get(field) != value:
            raise V5BrowserHostAttestationDenied("V5_APPROVAL_EXACT_RELEASE_MISMATCH")
    if (metadata.get("browser_approval_channel") != "entra_browser_admin"
            or not _SHA40.fullmatch(exact_release.candidate_sha)
            or not _SHA40.fullmatch(exact_release.rollback_sha)):
        raise V5BrowserHostAttestationDenied("V5_APPROVAL_CHANNEL_NOT_APPROVED")
    trust = read_root_browser_release_trust(
        root_trust_path, expected_tenant_id=route.tenant_id,
        expected_admin_oid=route.admin_approver_oid,
        expected_organization=organization_id,
        expected_policy_sha256=policy_sha256,
    )
    verified = verify_browser_decision_envelope(
        envelope, approval=exact_release, route=route,
        trusted_public_keys=trust.keys, now=now,
    )
    if verified.get("release_authorized") is not False:
        raise V5BrowserHostAttestationDenied("V5_HOST_VERIFY_CANNOT_GRANT_RELEASE")
    return {
        "status": "cryptographic_evidence_only",
        "approval_id": exact_release.approval_id,
        "channel": "entra_browser_admin",
        "decision": verified["decision"],
        "signed_evidence_sha256": verified["signed_evidence_sha256"],
        "authenticated_admin_oid": route.admin_approver_oid,
        "authorized_owner_id": owner_identity_ids[0],
        "release_authorized": False,
    }
