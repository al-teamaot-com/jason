"""Normalized response handoff behind Jason's EXISTING authenticated ingress.

This module provides no public endpoint, credential verifier, new
ApprovalRequestService or workflow executor. Production registration remains
OFF while the owner approval provenance incident is unresolved.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Mapping, Protocol

from orchestrator.event_store import OrchestrationEvent, SQLiteOrchestrationEventStore
from .contracts import ActionType, Interaction, InteractionKind, validate_answers
from .service import InteractionRejected


@dataclass(frozen=True)
class VerifiedReply:
    interaction_id: str
    response_id: str
    actor_identity_id: str
    organization_id: str
    client_id: str | None
    action_key: str
    answers: Mapping[str, Any]
    evidence_ref: str
    received_at: datetime


@dataclass(frozen=True)
class ResponseReceipt:
    interaction_id: str
    response_id: str
    actor_identity_id: str
    status: str
    existing_approval_result: str | None
    evidence_ref: str


class TrustedIngress(Protocol):
    """Must be ADR-009 signed SDK ingress + active tenant/Jason actor binding."""
    def verify(self, *, signed_event: Any, interaction_id: str) -> VerifiedReply: ...


class ResponderAuthority(Protocol):
    def may_respond(self, spec: Interaction, reply: VerifiedReply) -> bool: ...


class ExistingApprovalCallback(Protocol):
    def accept_from_existing_signed_ingress(
        self, *, spec: Interaction, signed_event: Any, verified: VerifiedReply
    ) -> str: ...


class WorkflowAnswerSink(Protocol):
    def accept_validated_answers(
        self, *, spec: Interaction, verified: VerifiedReply, answers: Mapping[str, Any]
    ) -> None: ...


class ResponseAudit(Protocol):
    def claim_once(self, spec: Interaction, reply: VerifiedReply) -> None: ...
    def accepted(self, spec: Interaction, receipt: ResponseReceipt) -> None: ...
    def uncertain(self, spec: Interaction) -> None: ...


@dataclass
class OrchestrationResponseJournal:
    """One-use response claim in the EXISTING orchestration event journal."""
    events: SQLiteOrchestrationEventStore

    @staticmethod
    def _id(spec: Interaction, stage: str) -> str:
        return "uis:" + stage + ":" + sha256(spec.interaction_id.encode()).hexdigest()

    def _event(self, spec: Interaction, stage: str, payload: dict) -> OrchestrationEvent:
        return OrchestrationEvent(
            event_type="universal_interaction." + stage,
            execution_id=spec.interaction_id, correlation_id=spec.correlation_id,
            organization_id=spec.organization_id, principal_id=spec.requester_identity_id,
            capability_name="communication.interaction",
            stage=stage, event_id=self._id(spec, stage), payload=payload,
        )

    def claim_once(self, spec: Interaction, reply: VerifiedReply) -> None:
        try:
            self.events.append_event(self._event(spec, "response_claim", {
                "response_id": reply.response_id,
                "actor_identity_id": reply.actor_identity_id,
                "action_key": reply.action_key,
                # No answers or signed event stored in audit.
            }))
        except ValueError as exc:
            raise InteractionRejected("response already claimed") from exc

    def accepted(self, spec: Interaction, receipt: ResponseReceipt) -> None:
        self.events.append_event(self._event(spec, "response_recorded", {
            "response_id": receipt.response_id,
            "actor_identity_id": receipt.actor_identity_id,
            "result": receipt.existing_approval_result or "form_recorded",
            "status": receipt.status,
            "evidence_ref": receipt.evidence_ref,
        }))

    def uncertain(self, spec: Interaction) -> None:
        self.events.append_event(self._event(
            spec, "response_uncertain", {"reason": "callback state requires reconciliation"}
        ))


@dataclass
class UniversalResponseHandoff:
    """Only accepts verified events from an existing, registered callback.

    No new callback route is exposed by importing this module. Existing
    ApprovalRequestService and procurement worker remain authoritative.
    """
    trusted_ingress: TrustedIngress
    responder_authority: ResponderAuthority
    existing_approvals: ExistingApprovalCallback
    workflow_answers: WorkflowAnswerSink
    journal: ResponseAudit
    callback_enabled: bool = False
    clock: Any = lambda: datetime.now(timezone.utc)

    def accept(self, spec: Interaction, signed_event: Any) -> ResponseReceipt:
        if not self.callback_enabled:
            raise InteractionRejected("universal callback not activated")
        verified = self.trusted_ingress.verify(
            signed_event=signed_event, interaction_id=spec.interaction_id)
        if (not isinstance(verified, VerifiedReply)
                or verified.interaction_id != spec.interaction_id
                or verified.organization_id != spec.organization_id
                or verified.client_id != spec.client_id
                or not verified.response_id or not verified.evidence_ref
                or verified.received_at.tzinfo is None):
            raise InteractionRejected("signed interaction identity/scope invalid")
        now = self.clock()
        if spec.expires_at is not None and now >= spec.expires_at:
            raise InteractionRejected("interaction expired")
        if not self.responder_authority.may_respond(spec, verified):
            raise InteractionRejected("actor not authorized to respond")
        action = next((a for a in spec.actions if a.key == verified.action_key), None)
        if action is None:
            raise InteractionRejected("unregistered action")
        if spec.kind is InteractionKind.APPROVAL:
            if action.intent not in (ActionType.APPROVE, ActionType.DENY):
                raise InteractionRejected("approval action invalid")
            if verified.answers:
                raise InteractionRejected("approval cannot alter stored material")
            values: Mapping[str, Any] = {}
        elif spec.kind is InteractionKind.QUESTIONNAIRE:
            if action.intent is not ActionType.SUBMIT:
                raise InteractionRejected("questionnaire only supports Submit")
            values = validate_answers(spec, verified.answers)
        else:
            if action.intent is not ActionType.ACKNOWLEDGE or verified.answers:
                raise InteractionRejected("only a bounded acknowledgment allowed")
            values = {}
        self.journal.claim_once(spec, verified)
        try:
            outcome = None
            if spec.kind is InteractionKind.APPROVAL:
                # MUST retain signed tenant/actor verification and the
                # existing atomic pending -> approved/denied transition.
                outcome = self.existing_approvals.accept_from_existing_signed_ingress(
                    spec=spec, signed_event=signed_event, verified=verified)
                if outcome not in ("approved", "denied"):
                    raise InteractionRejected("existing approval callback produced invalid result")
            elif spec.kind is InteractionKind.QUESTIONNAIRE:
                # Business policy/PO execution belongs exclusively to caller.
                self.workflow_answers.accept_validated_answers(
                    spec=spec, verified=verified, answers=values)
            receipt = ResponseReceipt(
                interaction_id=spec.interaction_id,
                response_id=verified.response_id,
                actor_identity_id=verified.actor_identity_id,
                status="recorded", existing_approval_result=outcome,
                evidence_ref=verified.evidence_ref,
            )
            self.journal.accepted(spec, receipt)
            return receipt
        except Exception:
            # A disconnected workflow may already have acted. Never auto-retry
            # a callback, consume an approval twice, or invent receipt state.
            self.journal.uncertain(spec)
            raise
