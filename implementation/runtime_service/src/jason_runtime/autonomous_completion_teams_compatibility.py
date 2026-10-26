"""First migration seam: existing autonomous status notice -> canonical Interaction.

This adapter is intentionally NOT wired into live composition or a new sender.
It uses the existing domain renderer as the source of truth, preserves its
complete text and facts, and prepares a no-send preview of the canonical Teams
template for parity review. The existing governed notification invoker, plan,
recipient, delivery journal and provider transport remain authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from communication.audience.models import AudienceType, MessagePurpose

from .autonomous_completion_notification import _render
from .universal_interaction.contracts import Fact, Interaction, InteractionKind, VisualIntent
from .universal_interaction.service import (
    AuthorizedRoute, InteractionDelivery, InteractionRejected, RouteAuthority,
    UniversalInteractionService,
)
from .universal_interaction.teams import ExistingTeamsInteractionAdapter


WORKFLOW = "autonomy_completion_status"
REQUESTER = "jason-autonomy-worker"
RECIPIENT = "person-al"
ORGANIZATION = "aot"

# Phase-one nonapproval status ONLY. Never convert release authorization,
# owner action required, work blocked, or escalation messages to a notice.
_ALLOWED_STATUS = {
    "work_started": (InteractionKind.PROGRESS, VisualIntent.INFORMATION, "Accent"),
    "ticket_status_updated": (InteractionKind.PROGRESS, VisualIntent.INFORMATION, "Accent"),
    "work_completed": (InteractionKind.NOTICE, VisualIntent.SUCCESS, "Good"),
}


@dataclass(frozen=True, slots=True)
class StatusNoticePreview:
    """No sender attached. A preview does NOT imply Teams delivery."""
    event_type: str
    recipient_identity_id: str
    interaction: Interaction
    legacy_text: str
    legacy_card: Mapping[str, Any]
    canonical_card: Mapping[str, Any]


def prepare_status_notice_preview(
    *, arguments: Mapping[str, Any], execution_id: str, correlation_id: str,
    principal_id: str, organization_id: str, client_id: str | None,
) -> StatusNoticePreview:
    """Normalize existing validated status material into Interaction v1.

    Strict identities and existing event renderer are reused; future dispatch
    must resolve the *same* person-al from the active AOT binding and re-check
    separate workflow authority through UniversalInteractionService.
    """
    if (organization_id != ORGANIZATION or principal_id != REQUESTER
            or client_id is not None):
        raise PermissionError("autonomous status preview cannot broaden audience or client")
    if not isinstance(arguments, Mapping):
        raise TypeError("autonomous status arguments must be a mapping")

    # Calls the EXISTING bounded domain renderer rather than copying/revising
    # work and ticket facts in a Teams-specific function.
    event, legacy_text, legacy_card = _render(arguments)
    presentation = _ALLOWED_STATUS.get(event)
    if presentation is None:
        raise PermissionError("this event needs a separately reviewed Teams migration")
    kind, visual_intent, expected_color = presentation
    if (not isinstance(legacy_card, Mapping)
            or legacy_card.get("type") != "AdaptiveCard"
            or legacy_card.get("version") != "1.4"
            or "actions" in legacy_card):
        raise ValueError("legacy status card was not a nonactionable Adaptive Card")
    body = legacy_card.get("body")
    if (not isinstance(body, list) or len(body) not in (2, 3)
            or body[0].get("type") != "TextBlock"
            or body[0].get("color") != expected_color
            or body[1].get("type") != "TextBlock"
            or not isinstance(body[0].get("text"), str)
            or not isinstance(body[1].get("text"), str)):
        raise ValueError("legacy status card content or semantic color changed")
    if len(body) == 3:
        if body[2].get("type") != "FactSet" or not isinstance(body[2].get("facts"), list):
            raise ValueError("legacy status card facts changed")
        raw_facts = body[2]["facts"]
    else:
        raw_facts = []

    facts = tuple(Fact(label=x["title"], value=x["value"]) for x in raw_facts)
    spec = Interaction(
        # Reuse the already stable single-work execution ID. Never fabricate
        # a fresh per-attempt identifier that would defeat deduplication.
        interaction_id=execution_id,
        workflow=WORKFLOW,
        correlation_id=correlation_id,
        organization_id=organization_id,
        client_id=client_id,
        requester_identity_id=principal_id,
        kind=kind,
        title=body[0]["text"],
        # Full original provider text retained to avoid any lost work/ticket
        # detail; facts remain structured and subject to audience review.
        summary=legacy_text,
        facts=facts,
        visual_intent=visual_intent,
    )
    card = ExistingTeamsInteractionAdapter.informational_card(spec)
    if (card["body"][0]["color"] != expected_color
            or card["body"][0]["text"] != body[0]["text"]
            or card["body"][1]["text"] != legacy_text
            or ("actions" in card)):
        raise RuntimeError("canonical status template failed the original message parity guard")
    if raw_facts and card["body"][2]["facts"] != raw_facts:
        raise RuntimeError("canonical status facts differ from legacy work evidence")
    return StatusNoticePreview(
        event_type=event,
        recipient_identity_id=RECIPIENT,
        interaction=spec,
        legacy_text=legacy_text,
        legacy_card=legacy_card,
        canonical_card=card,
    )


@dataclass(frozen=True)
class ExistingOwnerStatusRouteGuard:
    """Pin the current AOT owner route; delegate determines actual authority.

    Never change the recipient just because a new renderer handles a message.
    This is called *once* inside UniversalInteractionService dispatch.
    """
    delegate: RouteAuthority
    event_type: str

    def authorize(self, spec: Interaction) -> AuthorizedRoute:
        if (spec.workflow != WORKFLOW
                or spec.requester_identity_id != REQUESTER
                or spec.organization_id != ORGANIZATION
                or spec.client_id is not None
                or spec.approval_id is not None
                or spec.actions
                or spec.kind not in (InteractionKind.NOTICE, InteractionKind.PROGRESS)):
            raise InteractionRejected("status request is not approved for this migration")
        route = self.delegate.authorize(spec)
        expected_purpose = (
            MessagePurpose.TICKET_UPDATE
            if self.event_type == "ticket_status_updated" else MessagePurpose.OPERATIONAL
        )
        if (not isinstance(route, AuthorizedRoute)
                or not route.allowed
                or route.recipient_identity_id != RECIPIENT
                or route.organization_id != ORGANIZATION
                or route.client_id is not None
                or route.audience_type is not AudienceType.EXECUTIVE
                or route.purpose is not expected_purpose
                or route.channels != ("teams",)
                or not route.authorization_ref):
            raise InteractionRejected("existing AOT owner Teams route was changed")
        return route


@dataclass(frozen=True)
class GovernedAutonomyStatusInteractionPort:
    """Future single-sender integration seam; NEVER called by production yet.

    The injected existing UniversalInteractionService enforces audience,
    exact recipient/tenant, authorized route, immutable one-attempt claim,
    provider binding and no blind retry. No extra Teams transport exists here.
    """
    interactions: UniversalInteractionService

    def dispatch_prepared(self, preview: StatusNoticePreview) -> InteractionDelivery:
        if (not isinstance(preview, StatusNoticePreview)
                or preview.event_type not in _ALLOWED_STATUS
                or preview.recipient_identity_id != RECIPIENT
                or preview.interaction.workflow != WORKFLOW
                or preview.interaction.organization_id != ORGANIZATION
                or preview.interaction.requester_identity_id != REQUESTER
                or preview.interaction.client_id is not None
                or preview.interaction.approval_id is not None
                or preview.interaction.actions
                or preview.interaction.kind not in (InteractionKind.NOTICE, InteractionKind.PROGRESS)):
            raise PermissionError("canonical status route cannot broaden notification scope")
        # No transport is invoked outside this already-governed facade.
        expected_kind, expected_visual, expected_color = _ALLOWED_STATUS[preview.event_type]
        old_body = preview.legacy_card.get("body")
        if (preview.interaction.kind is not expected_kind
                or preview.interaction.visual_intent is not expected_visual
                or not isinstance(old_body, list) or len(old_body) < 2
                or preview.interaction.title != old_body[0].get("text")
                or preview.interaction.summary != preview.legacy_text
                or old_body[0].get("color") != expected_color
                or preview.canonical_card
                != ExistingTeamsInteractionAdapter.informational_card(preview.interaction)):
            raise PermissionError("canonical status preview differs from reviewed legacy material")
        # One checked authority resolution inside the EXISTING UIS execution,
        # not an authorization preflight plus a potentially changed route.
        protected = replace(
            self.interactions,
            authority=ExistingOwnerStatusRouteGuard(self.interactions.authority, preview.event_type),
        )
        return protected.dispatch(preview.interaction)
