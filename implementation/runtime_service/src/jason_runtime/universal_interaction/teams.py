"""Microsoft Teams is one adapter for the universal interaction contract.

Uses PR #1549's existing JasonTeamsCommunicationService, which rechecks
workflow authority, recipient binding, persisted approval, and audience.
This module never directly sends HTTP or opens a new approval callback.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from connectors.microsoft_graph.teams_approval_channel import render_approval_card
from .contracts import FieldType, Interaction, InteractionKind, VisualIntent
from .service import AuthorizedRoute, ChannelFeatures, InteractionDelivery, InteractionRejected
from jason_runtime.teams_communication_service import TeamsCommunicationRequest, JasonTeamsCommunicationService

_COLORS: dict[VisualIntent, str] = {
    VisualIntent.INFORMATION: "Accent",
    VisualIntent.ACTION_REQUIRED: "Warning",
    VisualIntent.CAUTION: "Warning",
    VisualIntent.CRITICAL: "Attention",
    VisualIntent.SUCCESS: "Good",
}


def _audience_reviewable_text(spec: Interaction) -> str:
    """Review the full rendered message/facts, not just an innocuous summary."""
    parts = [spec.title, spec.summary]
    parts.extend(f"{f.label}: {f.value}" for f in spec.facts)
    for item in spec.fields:
        parts.append(item.label)
        parts.extend(o.label for o in item.options)
    result = "\n".join(parts)
    if len(result) > 12000:
        raise InteractionRejected("interaction exceeds existing Teams disclosure review bound")
    return result


@dataclass
class ExistingTeamsInteractionAdapter:
    sender: JasonTeamsCommunicationService
    # The key is an already registered workflow route, not arbitrary input.
    questionnaire_renderers: Mapping[str, Callable[[Interaction], Mapping[str, Any]]] = field(default_factory=dict)
    registered_questionnaire_callbacks: frozenset[str] = frozenset()
    # Actual acceptance of approvals is still performed by the signed ADR-009
    # dispatcher + existing ApprovalRequestService. Never reimplement here.
    approval_callbacks_registered: bool = False
    channel_id: str = "teams"

    @property
    def features(self) -> ChannelFeatures:
        return ChannelFeatures(
            notices=True,
            forms=bool(self.registered_questionnaire_callbacks),
            authenticated_responses=True,
            approvals=self.approval_callbacks_registered,
            supported_fields=frozenset(FieldType),
        )

    def supports(self, spec: Interaction) -> bool:
        if not self.features.supports(spec):
            return False
        if spec.kind is InteractionKind.QUESTIONNAIRE:
            return (spec.workflow in self.registered_questionnaire_callbacks
                    and spec.workflow in self.questionnaire_renderers)
        return True

    @staticmethod
    def informational_card(spec: Interaction) -> Mapping[str, Any]:
        if spec.kind not in (
            InteractionKind.NOTICE, InteractionKind.PROGRESS,
            InteractionKind.ACKNOWLEDGEMENT,
        ):
            raise InteractionRejected("informational renderer cannot create actionable card")
        body: list[dict[str, Any]] = [
            {"type": "TextBlock", "text": spec.title, "weight": "Bolder",
             "size": "Medium", "wrap": True, "color": _COLORS[spec.visual_intent]},
            {"type": "TextBlock", "text": spec.summary, "wrap": True},
        ]
        if spec.facts:
            body.append({"type": "FactSet", "facts": [
                {"title": fact.label, "value": fact.value} for fact in spec.facts
            ]})
        return {"type": "AdaptiveCard", "version": "1.5", "body": body}

    def deliver(self, spec: Interaction, route: AuthorizedRoute) -> InteractionDelivery:
        if not self.supports(spec):
            raise InteractionRejected("Teams lacks registered controls for this interaction")
        if spec.kind is InteractionKind.APPROVAL:
            # Existing canonical renderer + persisted request is authoritative.
            persisted = self.sender.approval_requests.get(spec.approval_id)
            if persisted is None:
                raise InteractionRejected("approval request does not exist")
            rendered = render_approval_card(persisted)
            if spec.summary != rendered.summary:
                raise InteractionRejected("approval summary differs from stored request")
            message = spec.summary
            card = None  # existing sender renders and compares exact saved card
            kind = "approval"
        elif spec.kind is InteractionKind.QUESTIONNAIRE:
            message = _audience_reviewable_text(spec)
            card = self.questionnaire_renderers[spec.workflow](spec)
            if (not isinstance(card, Mapping)
                    or card.get("type") != "AdaptiveCard"
                    or not isinstance(card.get("body"), list)
                    or not isinstance(card.get("actions"), list)):
                raise InteractionRejected("registered workflow returned invalid form card")
            # Even registered rendering does not grant write authority.
            kind = "card"
        else:
            message = _audience_reviewable_text(spec)
            card = self.informational_card(spec)
            kind = "card"
        receipt = self.sender.send(TeamsCommunicationRequest(
            workflow=spec.workflow,
            communication_id=spec.interaction_id,
            correlation_id=spec.correlation_id,
            sender_identity_id=spec.requester_identity_id,
            recipient_identity_id=route.recipient_identity_id,
            organization_id=spec.organization_id,
            client_id=spec.client_id,
            audience_type=route.audience_type,
            purpose=route.purpose,
            text=message,
            kind=kind,
            card=card,
            approval_id=spec.approval_id,
        ))
        if not receipt.message_id:
            raise InteractionRejected("Teams transport returned no acceptance reference")
        return InteractionDelivery(
            interaction_id=spec.interaction_id, channel_id=self.channel_id,
            recipient_identity_id=route.recipient_identity_id,
            message_id=receipt.message_id,
        )
