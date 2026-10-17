"""Universal interaction orchestration, *not* a new approval/identity system.

Injected authority selects recipients and allowed channels. The existing
Jason orchestration event store provides a durable one-attempt send claim.
Neither provider acceptance nor a signed callback is proof of human presence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Mapping, Protocol

from communication.audience.models import AudienceType, MessagePurpose
from connectors.src.jason_connectors.approval_requests import ApprovalRequest
from orchestrator.event_store import OrchestrationEvent, SQLiteOrchestrationEventStore
from .contracts import FieldType, Interaction, InteractionKind


class InteractionRejected(PermissionError):
    """Fail closed rather than silently select an unsafe channel."""


@dataclass(frozen=True)
class ChannelFeatures:
    notices: bool = True
    forms: bool = False
    authenticated_responses: bool = False
    approvals: bool = False
    acknowledgement_controls: bool = False
    supported_fields: frozenset[FieldType] = frozenset()

    def supports(self, spec: Interaction) -> bool:
        if spec.kind is InteractionKind.QUESTIONNAIRE:
            return self.forms and self.authenticated_responses and all(
                f.field_type in self.supported_fields for f in spec.fields
            )
        if spec.kind is InteractionKind.APPROVAL:
            return self.approvals and self.authenticated_responses
        if spec.kind is InteractionKind.ACKNOWLEDGEMENT and spec.actions:
            return self.acknowledgement_controls and self.authenticated_responses
        return self.notices


@dataclass(frozen=True)
class AuthorizedRoute:
    recipient_identity_id: str
    organization_id: str
    client_id: str | None
    audience_type: AudienceType
    purpose: MessagePurpose
    channels: tuple[str, ...]
    authorization_ref: str
    allowed: bool


@dataclass(frozen=True)
class InteractionDelivery:
    interaction_id: str
    channel_id: str
    recipient_identity_id: str
    message_id: str | None
    state: str = "provider_accepted"


class RouteAuthority(Protocol):
    def authorize(self, spec: Interaction) -> AuthorizedRoute: ...


class ChannelAdapter(Protocol):
    channel_id: str
    features: ChannelFeatures

    def deliver(self, spec: Interaction, route: AuthorizedRoute) -> InteractionDelivery: ...


class InteractionAudit(Protocol):
    def claim(self, spec: Interaction, route: AuthorizedRoute) -> None: ...
    def accepted(self, spec: Interaction, receipt: InteractionDelivery) -> None: ...
    def uncertain(self, spec: Interaction) -> None: ...


@dataclass(frozen=True)
class ExistingApprovalGuard:
    """Checks only the existing immutable ApprovalRequest; does not accept votes."""
    requests: Any

    def verify(self, spec: Interaction, route: AuthorizedRoute, now: datetime) -> None:
        request = self.requests.get(spec.approval_id)
        if (not isinstance(request, ApprovalRequest)
                or getattr(getattr(request, "status", None), "value", None) != "pending"
                or request.organization_id != spec.organization_id
                or request.client_id != spec.client_id
                or request.requested_by != spec.requester_identity_id
                or request.correlation_id != spec.correlation_id
                or route.recipient_identity_id not in request.authorized_approver_ids
                or request.expires_at != spec.expires_at
                or now >= request.expires_at):
            raise InteractionRejected("missing, expired or mismatched persisted approval")


@dataclass
class OrchestrationInteractionJournal:
    """Adapter to existing SQLiteOrchestrationEventStore, no parallel table.

    A stable primary key in existing append-only events atomically prevents
    more than one delivery attempt. On ambiguous HTTP outcome the claim
    remains held; a reviewable reconciliation, NOT auto-retry, is required.
    """
    events: SQLiteOrchestrationEventStore

    @staticmethod
    def _id(interaction_id: str, event: str) -> str:
        return "uis:" + event + ":" + sha256(interaction_id.encode()).hexdigest()

    @staticmethod
    def _event(spec: Interaction, *, event: str, stage: str,
               payload: dict[str, Any]) -> OrchestrationEvent:
        return OrchestrationEvent(
            event_type="universal_interaction." + event,
            execution_id=spec.interaction_id,
            correlation_id=spec.correlation_id,
            organization_id=spec.organization_id,
            principal_id=spec.requester_identity_id,
            capability_name="communication.interaction",
            stage=stage, event_id=OrchestrationInteractionJournal._id(spec.interaction_id, event),
            payload=payload,
        )

    def claim(self, spec: Interaction, route: AuthorizedRoute) -> None:
        event = self._event(spec, event="delivery_claim", stage="claimed", payload={
            "recipient_identity_id": route.recipient_identity_id,
            "route_ref": route.authorization_ref,
            "kind": spec.kind.value,
            "contract_version": spec.contract_version,
            # No form answers, card contents, Microsoft tenant IDs or credentials.
        })
        try:
            self.events.append_event(event)
        except ValueError as exc:
            raise InteractionRejected("delivery already claimed; reconciliation required") from exc

    def accepted(self, spec: Interaction, receipt: InteractionDelivery) -> None:
        self.events.append_event(self._event(
            spec, event="provider_accepted", stage="provider_accepted", payload={
                "channel": receipt.channel_id,
                "recipient_identity_id": receipt.recipient_identity_id,
                "message_id": receipt.message_id,
                "state": receipt.state,
            },
        ))

    def uncertain(self, spec: Interaction) -> None:
        self.events.append_event(self._event(
            spec, event="delivery_uncertain", stage="reconciliation_required",
            payload={"reason": "non-idempotent send outcome unconfirmed"},
        ))


@dataclass
class UniversalInteractionService:
    """One universal facade; registration is deliberately absent in production.

    The source branch is inert until a separate rollout/owner approval and
    resolution of disputed Teams approval provenance (#1553/#1554).
    """
    authority: RouteAuthority
    channels: Mapping[str, ChannelAdapter]
    audit: InteractionAudit
    approvals: ExistingApprovalGuard
    approval_dispatch_enabled: bool = False
    clock: Any = lambda: datetime.now(timezone.utc)

    def dispatch(self, spec: Interaction) -> InteractionDelivery:
        current = self.clock()
        if spec.expires_at is not None and current >= spec.expires_at:
            raise InteractionRejected("interaction expired")
        route = self.authority.authorize(spec)
        if (not route.allowed or not route.authorization_ref
                or route.organization_id != spec.organization_id
                or route.client_id != spec.client_id
                or not route.recipient_identity_id
                or not route.channels):
            raise InteractionRejected("no authorized recipient or channel")
        if spec.kind is InteractionKind.APPROVAL:
            if not self.approval_dispatch_enabled:
                raise InteractionRejected("approval issuance suspended pending owner review")
            self.approvals.verify(spec, route, current)
        for channel_id in route.channels:
            adapter = self.channels.get(channel_id)
            if adapter is None or not adapter.features.supports(spec):
                continue
            # Adapter-specific workflow callback registration is checked
            # BEFORE any irreversible durable delivery claim is made.
            supports = getattr(adapter, "supports", None)
            if supports is not None and not supports(spec):
                continue
            # Atomically record one claim *before* any non-idempotent send.
            self.audit.claim(spec, route)
            try:
                receipt = adapter.deliver(spec, route)
                if (receipt.interaction_id != spec.interaction_id
                        or receipt.channel_id != channel_id
                        or receipt.recipient_identity_id != route.recipient_identity_id
                        or receipt.state != "provider_accepted"):
                    raise InteractionRejected("provider receipt mismatches the authorized request")
                self.audit.accepted(spec, receipt)
                return receipt
            except Exception:
                self.audit.uncertain(spec)
                raise
        raise InteractionRejected("no authorized channel supports required controls")
