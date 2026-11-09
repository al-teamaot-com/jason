"""V5 browser decision bridge into Jason's EXISTING ApprovalRequestService.

Not a second approval engine: uses the same pending request, atomic decision
receipt, immutable signed-evidence store and protected Release Manager gate.
It cannot deploy, grant standing rights, alter freeze or claim human delivery.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from connectors.src.jason_connectors.approval_requests import (
    ApprovalResponse, ApprovalDecision, ApprovalRequestStatus,
)
from .mobile_release_approval import (
    MobileReleaseSignedEvidenceStore, ApprovalRequestService,
    read_mobile_release_policy, read_eligible_release,
    read_release_approval_containment, CAPABILITY,
)
from .release_v5_aot_policy import (
    CHANNEL,
)
from .release_v5_ca_attestation import verify_root_ca_enforcement_receipt
from .release_v5_signed_evidence import (
    sign_browser_release_decision, verify_browser_release_decision,
    _canonical,
)


@dataclass
class GovernedV5BrowserReleaseDecision:
    """Source-only, dormant until reviewed V5 root policy is activated."""
    policy_path: Path
    release_state_root: Path
    ca_attestation_path: Path
    requests: Any
    approvals: ApprovalRequestService
    signed_evidence: MobileReleaseSignedEvidenceStore
    signing_key: Ed25519PrivateKey
    required_policy_version: str = "5.0"

    def handle(
        self, *, approval_id: str, decision: str,
        authenticated_admin_proof: Mapping[str, Any],
        when: datetime,
    ) -> Mapping[str, Any]:
        policy=read_mobile_release_policy(self.policy_path)
        if policy.schema_version != self.required_policy_version:
            raise PermissionError("V5_BROWSER_APPROVAL_POLICY_NOT_ACTIVATED")
        if decision not in {"approve","deny"}:
            raise PermissionError("V5_BROWSER_EXPLICIT_DECISION_REQUIRED")
        read_release_approval_containment(
            self.release_state_root,
        ).require_request_eligible(when)
        request=self.requests.get(approval_id)
        if request is None or request.status is not ApprovalRequestStatus.PENDING:
            raise PermissionError("V5_BROWSER_PENDING_REQUEST_NOT_FOUND")
        release_id=request.metadata.get("release_id")
        if (request.capability != CAPABILITY
                or request.authorized_approver_ids!=policy.owner_identity_ids
                or not isinstance(release_id,str)):
            raise PermissionError("V5_BROWSER_RELEASE_REQUEST_NOT_AUTHORIZED")
        # Every browser decision rechecks the same frozen release, native
        # manifest and scope before accepting a signed record.
        evidence=read_eligible_release(
            self.release_state_root,release_id,policy,
        )
        if (evidence.candidate_sha!=request.metadata.get("candidate_sha")
                or evidence.rollback_sha!=request.metadata.get("rollback_sha")
                or evidence.manifest_sha256!=request.metadata.get("manifest_sha256")
                or evidence.reviewed_scope_sha256!=request.metadata.get("scope_sha256")):
            raise PermissionError("V5_BROWSER_LIVE_RELEASE_SCOPE_CHANGED")
        ca_hash=verify_root_ca_enforcement_receipt(
            self.ca_attestation_path,
            browser_policy=policy.browser_policy,
            now=when,
        )
        signed=sign_browser_release_decision(
            request=request,policy=policy,
            authenticated_admin_proof=authenticated_admin_proof,
            ca_policy_receipt_sha256=ca_hash,
            decision=decision,when=when,
            private_key=self.signing_key,
        )
        receipt=verify_browser_release_decision(
            signed=signed,request=request,policy=policy,
            public_key=self.signing_key.public_key(),now=when,
        )
        authentication_hash=receipt["auth_evidence_sha256"]
        # Only the existing protected, immutable signed-evidence store.
        # Persist before decision commit; a crash cannot create an accepted
        # release without the verifiable original signature.
        self.signed_evidence.save(
            approval_id=approval_id,
            signed_envelope=signed,
            evidence_sha256=authentication_hash,
        )
        channel_response_id=sha256(_canonical(signed)).hexdigest()
        response=ApprovalResponse(
            approval_id=request.approval_id,
            organization_id=request.organization_id,
            approver_identity_id=policy.owner_identity_ids[0],
            decision=(ApprovalDecision.APPROVE if decision=="approve"
                      else ApprovalDecision.DENY),
            decided_at=when,
            channel=CHANNEL,
            channel_response_id=channel_response_id,
            authentication_evidence_hash=authentication_hash,
        )
        accepted=self.approvals.accept_response(response,now=when)
        return {
            "status":"signed_decision_recorded",
            "approval_id":approval_id,
            "decision":decision,
            "channel":CHANNEL,
            "signed_evidence_sha256":sha256(_canonical(signed)).hexdigest(),
            "release_authorized":False,
            "production_deployed":False,
        }
