"""Microsoft Teams binding for Jason's provider-neutral approval protocol.

This module translates between Jason approval objects and Teams channel payloads.
It deliberately performs no authority decision: Teams is transport/UI only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from implementation.connectors.src.jason_connectors.approval_requests import (
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


def render_approval_card(request: ApprovalRequest) -> TeamsApprovalCard:
    """Render only non-secret approval metadata for delivery to Teams."""
    request.validate()
    return TeamsApprovalCard(
        approval_id=request.approval_id,
        organization_id=request.organization_id,
        title="Jason approval required",
        summary=f"{request.requested_by} requests {request.requested_mode} for {request.capability}",
        capability=request.capability,
        requested_mode=request.requested_mode,
        expires_at=request.expires_at.isoformat(),
        evidence_artifact_ids=tuple(ref.artifact_id for ref in request.evidence_references),
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
    if raw_decision not in {ApprovalDecision.APPROVE.value, ApprovalDecision.DENY.value}:
        raise ValueError("Teams approval decision must be approve or deny")
    return ApprovalResponse(
        approval_id=payload.get("approval_id", ""),
        organization_id=payload.get("organization_id", ""),
        approver_identity_id=authenticated_identity_id,
        decision=ApprovalDecision(raw_decision),
        decided_at=decided_at,
        channel="microsoft_teams",
        channel_response_id=payload.get("channel_response_id", ""),
    )
