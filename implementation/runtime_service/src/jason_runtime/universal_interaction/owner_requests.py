"""Build one common Teams-capable interaction from EXISTING owner approval.

This is presentation construction, not authorization or execution. The caller
must first persist its approval with ApprovalRequestService and obtain a
governed recipient route. No SSH, host shell, new login, or approval datastore
is part of this interface. Every decision remains with signed ADR-009 ingress.
"""
from __future__ import annotations

from connectors.src.jason_connectors.approval_requests import (
    ApprovalRequest, ApprovalRequestStatus,
)

from .contracts import (
    Action, ActionType, Fact, Interaction, InteractionKind, VisualIntent,
)


def interaction_from_owner_approval(
    request: ApprovalRequest, *, interaction_id: str, workflow: str,
    visual_intent: VisualIntent = VisualIntent.ACTION_REQUIRED,
) -> Interaction:
    """Universal owner interaction from a preexisting immutable request.

    Release, expense, high-impact configuration and playbook workflows may
    call this only after their own authority has created the persisted
    ApprovalRequest. It does NOT activate approval issuance by itself.

    All material details come from the already approved canonical
    ApprovalPresentation, never from an editable Teams client.
    """
    if not isinstance(request, ApprovalRequest):
        raise TypeError("a persisted ApprovalRequest is required")
    request.validate()
    if request.status is not ApprovalRequestStatus.PENDING:
        raise PermissionError("owner interaction requires a pending approval")
    if request.presentation is None:
        raise PermissionError("owner action requires exact reviewable presentation")
    return Interaction(
        interaction_id=interaction_id, workflow=workflow,
        correlation_id=request.correlation_id,
        organization_id=request.organization_id,
        client_id=request.client_id,
        requester_identity_id=request.requested_by,
        kind=InteractionKind.APPROVAL,
        title=request.presentation.title,
        summary=request.presentation.summary,
        visual_intent=visual_intent,
        facts=tuple(Fact(label, value) for label, value in request.presentation.facts),
        actions=(
            Action("approve", "Approve", ActionType.APPROVE),
            Action("deny", "Deny", ActionType.DENY),
        ),
        approval_id=request.approval_id,
        expires_at=request.expires_at,
    )
