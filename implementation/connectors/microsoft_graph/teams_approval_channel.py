"""Microsoft Teams binding for Jason's provider-neutral approval protocol.

This module translates between Jason approval objects and Teams channel payloads.
It deliberately performs no authority decision: Teams is transport/UI only.
"""

from __future__ import annotations

import hashlib

from dataclasses import dataclass
import re
from datetime import datetime
from typing import Mapping

from connectors.src.jason_connectors.approval_requests import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalResponse,
)


@dataclass(frozen=True, slots=True)
class TeamsApprovalCard:
    approval_id: str
    organization_id: str
    title: str
    summary: str
    capability: str
    requested_mode: str
    expires_at: str
    evidence_artifact_ids: tuple[str, ...]
    facts: tuple[tuple[str, str], ...] = ()
    card_instance_challenge: str | None = None


def render_approval_card(request: ApprovalRequest) -> TeamsApprovalCard:
    """Render only non-secret approval metadata for delivery to Teams."""
    request.validate()
    presentation = request.presentation
    challenge = request.metadata.get("card_instance_challenge")
    is_reviewed_release = (
        request.capability == "release.production.approve"
        and request.approval_id.startswith("relapproval-"))
    is_universal_plan = request.approval_id.startswith("planapproval-")
    is_procurement_purchase = (
        request.capability == 'procurement.submission.execute'
        and request.requested_mode == 'purchase'
        and request.approval_id.startswith('procapproval-')
    )
    if (is_universal_plan or is_procurement_purchase) and challenge is None:
        raise PermissionError("reviewed plan or purchase card requires an issued card-instance proof")
    if challenge is not None:
        if (not (is_reviewed_release or is_universal_plan or is_procurement_purchase)
                or type(challenge) is not str
                or re.fullmatch(r"[0-9a-f]{48}", challenge) is None
                or hashlib.sha256(challenge.encode("ascii")).hexdigest()
                    != request.metadata.get("card_instance_challenge_sha256")):
            raise PermissionError("card-instance proof must match its reviewed request")
    return TeamsApprovalCard(
        approval_id=request.approval_id,
        organization_id=request.organization_id,
        title=(presentation.title if presentation is not None else "Jason approval required"),
        summary=(
            presentation.summary
            if presentation is not None
            else f"{request.requested_by} requests {request.requested_mode} for {request.capability}"
        ),
        capability=request.capability,
        requested_mode=request.requested_mode,
        expires_at=request.expires_at.isoformat(),
        evidence_artifact_ids=tuple(ref.artifact_id for ref in request.evidence_references),
        facts=(presentation.facts if presentation is not None else ()),
        card_instance_challenge=request.metadata.get("card_instance_challenge"),
    )


def parse_teams_response(
    payload: Mapping[str, str],
    *,
    authenticated_identity_id: str,
    decided_at: datetime,
) -> ApprovalResponse:
    """Translate an authenticated Teams interaction into a provider-neutral response.

    The authenticated identity must come from the governed Microsoft/Entra ingress
    boundary, never from a user-editable card field.
    """
    raw_decision = payload.get("decision", "").strip().lower()
    if raw_decision not in {
        ApprovalDecision.APPROVE.value,
        ApprovalDecision.DENY.value,
        ApprovalDecision.REQUEST_CHANGES.value,
    }:
        raise ValueError("Teams approval decision must be approve, deny, or request_changes")
    return ApprovalResponse(
        approval_id=payload.get("approval_id", ""),
        organization_id=payload.get("organization_id", ""),
        approver_identity_id=authenticated_identity_id,
        decision=ApprovalDecision(raw_decision),
        decided_at=decided_at,
        channel="microsoft_teams",
        channel_response_id=payload.get("channel_response_id", ""),
    )
