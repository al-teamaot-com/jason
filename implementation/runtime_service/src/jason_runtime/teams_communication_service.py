"""Shared, constitutionally reused Jason Teams communications boundary.

Architecture: Canonical workflow -> existing AudiencePolicyEngine & authority ->
active Jason Microsoft identity binding -> existing direct Teams gateway ->
provider receipt. Approval issuance requires an already persisted and scoped
ApprovalRequest; the existing ApprovalInteractionDispatcher handles human votes.
This class is NOT a parallel Teams bot, identity provider or approval engine.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from .teams_message_send import post_existing_teams_gateway
from uuid import UUID

from communication.audience.engine import AudiencePolicyEngine
from connectors.src.jason_connectors.approval_requests import ApprovalRequest
from communication.audience.models import (
    AudienceType, CommunicationDraft, MessagePurpose, Recipient, ReviewDecision,
)

_ALLOWED_KINDS = frozenset(("notification", "status", "card", "approval"))
_WORD = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")


def _uuid(value: Any) -> str:
    if not isinstance(value, str):
        raise PermissionError("Teams target requires verified Microsoft identity")
    try:
        result = UUID(value)
    except (ValueError, AttributeError) as exc:
        raise PermissionError("Teams target has invalid Microsoft identity") from exc
    return str(result)


@dataclass(frozen=True)
class TeamsDeliveryReceipt:
    """Provider acceptance is NOT proof of human delivery or approval."""
    message_id: str
    conversation_id: str | None
    recipient_identity_id: str
    delivery_state: str = "provider_accepted"


@dataclass
class ExistingTeamsGatewayTransport:
    """One existing Teams gateway transport reused by all Jason workflows."""
    gateway_url: str
    token_file: str | Path
    timeout_seconds: int = 20

    def send(self, *, binding: Any, text: str,
             card: Mapping[str, Any] | None = None) -> TeamsDeliveryReceipt:
        if getattr(binding, "status", None) != "active":
            raise PermissionError("Teams recipient binding is not active")
        tenant = _uuid(getattr(binding, "microsoft_tenant_id", None))
        actor = _uuid(getattr(binding, "microsoft_object_id", None))
        if not isinstance(text, str) or not text.strip() or len(text) > 12000:
            raise ValueError("Teams message text is invalid or exceeds size bound")
        payload: dict[str, Any] = {
            "aadObjectId": actor, "tenantId": tenant, "text": text,
        }
        if card is not None:
            if (not isinstance(card, Mapping)
                    or card.get("type") != "AdaptiveCard"
                    or not isinstance(card.get("body"), list)
                    or not isinstance(card.get("version"), str)):
                raise ValueError("Teams card must be a bounded AdaptiveCard")
            payload["card"] = dict(card)
        credential = Path(self.token_file).read_text(encoding="utf-8").strip()
        if not credential:
            raise PermissionError("existing Teams proactive token unavailable")
        result = post_existing_teams_gateway(
            gateway_url=self.gateway_url,
            token=credential,
            payload=payload,
            timeout_seconds=self.timeout_seconds,
        )
        message_id = result["message_id"]
        conversation_id = result.get("conversation_id")
        return TeamsDeliveryReceipt(
            message_id=message_id.strip(),
            conversation_id=conversation_id if isinstance(conversation_id, str) else None,
            recipient_identity_id=str(getattr(binding, "jason_identity_id", "")),
        )


@dataclass(frozen=True)
class TeamsCommunicationRequest:
    """Request is from a governed workflow, never from an untrusted Teams card."""
    workflow: str
    communication_id: str
    correlation_id: str
    sender_identity_id: str
    recipient_identity_id: str
    organization_id: str
    client_id: str | None
    audience_type: AudienceType
    purpose: MessagePurpose
    text: str
    kind: str = "notification"
    card: Mapping[str, Any] | None = None
    approval_id: str | None = None


@dataclass
class JasonTeamsCommunicationService:
    """Reusable workflow adapter, not a second authorization engine.

    The orchestrator supplies governed workflow authority. Existing Audience
    PolicyEngine controls disclosure, live bindings resolve the recipient,
    and existing ApprovalRequest records authorize actionable cards.
    """
    transport: ExistingTeamsGatewayTransport
    bindings: Any
    identities: Any
    workflow_authority: Any
    approval_requests: Any
    audience: AudiencePolicyEngine

    def send(self, request: TeamsCommunicationRequest) -> TeamsDeliveryReceipt:
        if (not isinstance(request, TeamsCommunicationRequest)
                or request.kind not in _ALLOWED_KINDS
                or not all(_WORD.fullmatch(x) for x in (
                    request.workflow, request.communication_id,
                    request.correlation_id, request.sender_identity_id,
                    request.recipient_identity_id, request.organization_id))
                or (request.client_id is not None
                    and not _WORD.fullmatch(request.client_id))):
            raise PermissionError("invalid governed Teams communication scope")
        if not self.workflow_authority.can_communicate(
                workflow=request.workflow, sender_identity_id=request.sender_identity_id,
                recipient_identity_id=request.recipient_identity_id,
                organization_id=request.organization_id, client_id=request.client_id,
                kind=request.kind, purpose=request.purpose):
            raise PermissionError("workflow is not authorized for Teams communication")

        identity = self.identities.get(request.recipient_identity_id)
        if (identity is None or getattr(identity, "status", None) != "active"
                or identity.organization_id != request.organization_id):
            raise PermissionError("Teams recipient lacks matching active Jason identity")
        # Internal staff only until external audience/organization routing has
        # a separately approved communication policy and authorized provider.
        if request.audience_type not in (
                AudienceType.INTERNAL_TECHNICIAN,
                AudienceType.SERVICE_MANAGER,
                AudienceType.EXECUTIVE):
            raise PermissionError("Teams internal transport has no external recipient grant")
        binding = self.bindings.find_active_by_jason_identity(
            jason_identity_id=request.recipient_identity_id)
        if (binding is None or getattr(binding, "status", None) != "active"):
            raise PermissionError("Teams recipient has no active Microsoft binding")
        actual_card = request.card
        if request.kind == "approval":
            if not request.approval_id:
                raise PermissionError("approval card requires persisted immutable approval")
            persisted = self.approval_requests.get(request.approval_id)
            if (persisted is None or not isinstance(persisted, ApprovalRequest)
                    or getattr(getattr(persisted, "status", None), "value", None) != "pending"
                    or persisted.organization_id != request.organization_id
                    or persisted.client_id != request.client_id
                    or persisted.requested_by != request.sender_identity_id
                    or persisted.correlation_id != request.correlation_id
                    or request.purpose is not MessagePurpose.APPROVAL_REQUEST
                    or request.recipient_identity_id not in persisted.authorized_approver_ids):
                raise PermissionError("Teams approval is not pending or recipient unauthorized")
            # Canonical shared renderer (already used by invoice/PO, playbook
            # and release approval), not caller-generated approval details.
            from datetime import datetime, timezone
            from connectors.microsoft_graph.teams_approval_channel import render_approval_card
            from .playbook_autonomy_review import TeamsGatewayPlaybookApprovalSender
            if datetime.now(timezone.utc) >= persisted.expires_at:
                raise PermissionError("Teams approval request has expired")
            rendered = render_approval_card(persisted)
            canonical_card = TeamsGatewayPlaybookApprovalSender._adaptive_card(rendered)
            if (request.text != rendered.summary
                    or (request.card is not None and dict(request.card) != canonical_card)):
                raise PermissionError("Teams approval card differs from stored server-approved material")
            actual_card = canonical_card
        elif request.approval_id is not None:
            raise PermissionError("nonapproval message cannot carry approval authority")
        if request.card is not None and request.kind not in ("card", "approval"):
            raise ValueError("actionable card cannot be sent as a status message")

        review = self.audience.review(CommunicationDraft(
            communication_id=request.communication_id,
            correlation_id=request.correlation_id,
            organization_id=request.organization_id,
            client_id=request.client_id,
            sender_identity=request.sender_identity_id,
            channel="teams",
            purpose=request.purpose,
            subject=None,
            body=request.text,
            recipients=(Recipient(
                recipient_id=request.recipient_identity_id,
                organization_id=identity.organization_id,
                client_id=request.client_id,
                audience_type=request.audience_type,
                channel_address=str(binding.microsoft_object_id),
            ),),
        ))
        if review.decision is not ReviewDecision.ALLOW:
            raise PermissionError(
                "Teams content review requires separate revision/approval: "
                + review.decision.value)
        # The gateway returns provider-accepted only, not a false delivery
        # or approval success assertion. Never auto-retry a non-idempotent send.
        return self.transport.send(binding=binding, text=request.text, card=actual_card)


@dataclass
class ExistingTeamsApprovalReceiptHandler:
    """Shared inbound vote adapter; uses EXISTING ApprovalRequestService.

    The SDK-authenticated, replay-protected, Ed25519-signed ingress already
    owns the Microsoft actor evidence. This adapter rebinds the actor and
    consumes the persisted approval exactly once. Execution is deliberately
    NOT part of accepting a card response.
    """
    bindings: Any
    identities: Any
    approval_service: Any
    allowed_capabilities: frozenset[str]
    approval_prefix: str

    def handle(self, *, approval_id: str, decision: str,
               microsoft_tenant_id: str, microsoft_object_id: str,
               conversation_id: str, channel_response_id: str,
               decided_at: Any, selections: Mapping[str, str] | None = None):
        from connectors.src.jason_connectors.approval_requests import (
            ApprovalDecision, ApprovalResponse,
        )
        if (not self.approval_prefix or not approval_id.startswith(self.approval_prefix)
                or not self.allowed_capabilities):
            raise PermissionError("approval route or workflow capability not authorized")
        if selections:
            raise PermissionError("approval selections cannot change stored request")
        if not all(isinstance(v, str) and v.strip() for v in (
                microsoft_tenant_id, microsoft_object_id, conversation_id,
                channel_response_id)):
            raise PermissionError("authenticated Teams response identity missing")
        request = self.approval_service.repository.get(approval_id)
        if request is None or request.capability not in self.allowed_capabilities:
            raise PermissionError("approval is not a registered workflow request")
        binding = self.bindings.find(
            microsoft_tenant_id=microsoft_tenant_id,
            microsoft_object_id=microsoft_object_id,
        )
        if binding is None or getattr(binding, "status", None) != "active":
            raise PermissionError("Teams approver Microsoft identity is not bound")
        identity = self.identities.get(binding.jason_identity_id)
        if (identity is None or getattr(identity, "status", None) != "active"
                or identity.organization_id != request.organization_id):
            raise PermissionError("Teams approver has no matching active Jason identity")
        try:
            resolved_decision = ApprovalDecision(decision)
        except ValueError as exc:
            raise PermissionError("Teams decision is not permitted") from exc
        receipt = self.approval_service.accept_response(
            ApprovalResponse(
                approval_id=approval_id,
                organization_id=request.organization_id,
                approver_identity_id=identity.identity_id,
                decision=resolved_decision,
                decided_at=decided_at,
                channel="microsoft_teams",
                channel_response_id=channel_response_id,
            ),
            now=decided_at,
        )
        return {
            "status": "completed", "approval_id":approval_id,
            "approval_status":receipt.status,
            "executed":False,
            "reply":{"text":(
                "Approval decision recorded. The governed workflow will "
                "separately verify its own execution authority."
                if receipt.status=="approved" else
                "Denied or changes requested. No workflow action was executed."
            )},
        }
