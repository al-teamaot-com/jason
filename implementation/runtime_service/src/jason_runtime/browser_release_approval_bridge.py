"""Dormant V5 browser decision intake using Jason's EXISTING approval ledger.

This adds no approval endpoint and cannot authorize a production release.
It never accepts unverified Entra claims, text Teams notifications or V4
policy as privileged release approval.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from connectors.src.jason_connectors.approval_requests import (
    ApprovalDecision, ApprovalResponse, ApprovalRequestStatus,
)


@dataclass
class V5BrowserApprovalDecisionBridge:
    """Explicitly *unmounted* bridge into the same ApprovalRequestService."""
    approvals: Any
    requests: Any
    signed_evidence: Any
    reviewed_route: Any
    root_trust_path: Path
    reviewed_policy_sha256: str
    organization_id: str
    owner_identity_ids: tuple[str, ...]
    policy_version: str = "not-activated"
    # Explicit host-verified trust port, never a user-provided callback.
    # The standalone runtime service must NOT import MCP/host packages.
    attest_signed_browser_evidence: Callable[..., Mapping[str, Any]] | None = None

    def handle_signed_browser_decision(
        self, *, envelope: Mapping[str, Any],
        exact_release: Any,
        now: datetime,
    ) -> Mapping[str, Any]:
        """Persist signed evidence then consume one native pending decision.

        The bridge itself never creates a pending release approval, changes
        root policy, records CCC, unfreezes or invokes a release runner.
        The protected host consumer must independently re-attest stored
        evidence under a separately reviewed V5 root policy before any release.
        """
        if self.policy_version != "5.0":
            raise PermissionError("V5_BROWSER_POLICY_NOT_INSTALLED")
        if now.tzinfo is None:
            raise PermissionError("V5_BROWSER_CLOCK_INVALID")
        if not callable(self.attest_signed_browser_evidence):
            raise PermissionError("V5_BROWSER_HOST_ATTESTOR_NOT_INSTALLED")
        request = self.requests.get(exact_release.approval_id)
        if request is None:
            raise PermissionError("V5_BROWSER_REQUEST_MISSING")
        # This source is not callable from any live V4 handler. The
        # *protected root policy* and exact reviewed Owner route are inputs.
        attested = self.attest_signed_browser_evidence(
            request=request, envelope=envelope,
            exact_release=exact_release, route=self.reviewed_route,
            policy_version=self.policy_version,
            policy_sha256=self.reviewed_policy_sha256,
            organization_id=self.organization_id,
            owner_identity_ids=self.owner_identity_ids,
            root_trust_path=self.root_trust_path, now=now,
        )
        if attested["release_authorized"] is not False:
            raise PermissionError("V5_BROWSER_ATTESTOR_CANNOT_GRANT_RELEASE")
        sha = attested["signed_evidence_sha256"]
        self.signed_evidence.save(
            approval_id=exact_release.approval_id,
            signed_envelope=envelope, evidence_sha256=sha,
        )
        response = ApprovalResponse(
            approval_id=exact_release.approval_id,
            organization_id=self.organization_id,
            approver_identity_id=self.owner_identity_ids[0],
            decision=(ApprovalDecision.APPROVE if attested["decision"] == "approve"
                      else ApprovalDecision.DENY),
            decided_at=now,
            channel="entra_browser_admin",
            channel_response_id=sha,
            authentication_evidence_hash=sha,
        )
        accepted = self.approvals.accept_response(response, now=now)
        return {
            "status": "existing_approval_ledger_decision",
            "approval_id":exact_release.approval_id,
            "decision_status": accepted.status,
            "source":"versioned_5_browser_evidence",
            "evidence_sha256":sha,
            "release_authorized":False,
            "executed":False,
        }
