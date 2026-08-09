"""End-to-end governed Teams approval response flow with immutable audit evidence.

This composition layer wires existing trust boundaries without collapsing them:
Microsoft token verification -> Teams ingress identity binding -> provider-neutral
approval validation -> JKD-001 durable approval/re-authorization -> resumed
orchestration request carrying a fresh execution context.

Teams and Microsoft authentication remain inputs to Jason authority, never the
authority themselves. Audit recording is mandatory and fail-closed for this flow;
audit events can never create or expand execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping, Protocol
from uuid import uuid4

from connectors.microsoft_graph.teams_approval_ingress import (
    TeamsApprovalIngress,
    VerifiedMicrosoftPrincipal,
)
from connectors.src.jason_connectors.approval_requests import (
    AcceptedApproval,
    ApprovalRequestService,
)

from .approval_audit import ApprovalAuditEvent, ApprovalAuditEventType, ApprovalAuditRecorder
from .approvals import ApprovalResumeBridge
from .contracts import OrchestrationRequest


class MicrosoftPrincipalVerifier(Protocol):
    def verify(self, token: str) -> VerifiedMicrosoftPrincipal: ...


@dataclass(frozen=True, slots=True)
class TeamsApprovalFlowResult:
    accepted_approval: AcceptedApproval
    resumed_request: OrchestrationRequest | None


@dataclass(frozen=True, slots=True)
class TeamsApprovalFlow:
    token_verifier: MicrosoftPrincipalVerifier
    ingress: TeamsApprovalIngress
    approval_service: ApprovalRequestService
    resume_bridge: ApprovalResumeBridge
    audit: ApprovalAuditRecorder
    event_id_factory: Callable[[], str] = lambda: str(uuid4())

    def handle_response(
        self,
        *,
        token: str,
        payload: Mapping[str, str],
        original_request: OrchestrationRequest,
        decided_at: datetime,
        now: datetime | None = None,
    ) -> TeamsApprovalFlowResult:
        """Process one Teams approval response through every Jason trust gate.

        Denials are valid approval outcomes but never resume execution. Authentication,
        tenant/identity binding, approval authorization, expiration, JKD-001
        re-authorization, and audit persistence all fail closed.
        """

        approval_id = payload.get("approval_id", "").strip()
        if not approval_id:
            raise PermissionError("approval payload approval_id is required")

        stage = "token_verification"
        principal: VerifiedMicrosoftPrincipal | None = None
        try:
            principal = self.token_verifier.verify(token)
            self._record(
                event_type=ApprovalAuditEventType.RESPONSE_AUTHENTICATED,
                approval_id=approval_id,
                original_request=original_request,
                occurred_at=decided_at,
                actor_identity_id=None,
                channel="teams",
                metadata={
                    "microsoft_tenant_id": principal.tenant_id,
                    "authentication_assurance": principal.authentication_assurance,
                },
            )

            stage = "teams_ingress"
            response = self.ingress.accept_verified_interaction(
                principal=principal,
                payload=payload,
                decided_at=decided_at,
            )

            stage = "approval_authority"
            accepted = self.approval_service.accept_response(response, now=now)
            outcome_type = (
                ApprovalAuditEventType.RESPONSE_ACCEPTED
                if accepted.status == "approved"
                else ApprovalAuditEventType.RESPONSE_DENIED
            )
            self._record(
                event_type=outcome_type,
                approval_id=accepted.approval_id,
                original_request=original_request,
                occurred_at=accepted.decided_at,
                actor_identity_id=accepted.decided_by,
                channel=accepted.channel,
                channel_reference_id=accepted.channel_response_id,
                evidence_references=accepted.evidence_references,
                metadata={"approval_status": accepted.status},
            )

            if accepted.status != "approved":
                return TeamsApprovalFlowResult(
                    accepted_approval=accepted,
                    resumed_request=None,
                )

            stage = "jkd_reauthorization"
            resumed = self.resume_bridge.resume(
                original_request=original_request,
                accepted=accepted,
                authentication_assurance=principal.authentication_assurance,
            )
            self._record(
                event_type=ApprovalAuditEventType.JKD_REAUTHORIZED,
                approval_id=accepted.approval_id,
                original_request=original_request,
                occurred_at=self._now(now),
                actor_identity_id=accepted.decided_by,
                channel=accepted.channel,
                channel_reference_id=accepted.channel_response_id,
                authority_context_id=resumed.authority_context_id,
                evidence_references=accepted.evidence_references,
            )
            self._record(
                event_type=ApprovalAuditEventType.ORCHESTRATOR_RESUMED,
                approval_id=accepted.approval_id,
                original_request=original_request,
                occurred_at=self._now(now),
                actor_identity_id=original_request.principal_id,
                channel=accepted.channel,
                channel_reference_id=accepted.channel_response_id,
                authority_context_id=resumed.authority_context_id,
                evidence_references=accepted.evidence_references,
            )
            return TeamsApprovalFlowResult(
                accepted_approval=accepted,
                resumed_request=resumed,
            )
        except Exception as exc:
            event_type = ApprovalAuditEventType.PROCESSING_FAILED
            if stage == "approval_authority" and "expired" in str(exc).lower():
                event_type = ApprovalAuditEventType.REQUEST_EXPIRED
            elif stage in {"teams_ingress", "approval_authority"} and isinstance(exc, PermissionError):
                event_type = ApprovalAuditEventType.AUTHORIZATION_REJECTED

            self._record(
                event_type=event_type,
                approval_id=approval_id,
                original_request=original_request,
                occurred_at=self._now(now),
                actor_identity_id=None,
                channel="teams",
                reason_code=type(exc).__name__,
                metadata={"stage": stage, "error": str(exc)[:240]},
            )
            raise

    def _record(
        self,
        *,
        event_type: ApprovalAuditEventType,
        approval_id: str,
        original_request: OrchestrationRequest,
        occurred_at: datetime,
        actor_identity_id: str | None,
        channel: str | None = None,
        channel_reference_id: str | None = None,
        authority_context_id: str | None = None,
        reason_code: str | None = None,
        evidence_references=(),
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        self.audit.record(
            ApprovalAuditEvent(
                event_id=self.event_id_factory(),
                event_type=event_type,
                occurred_at=occurred_at,
                approval_id=approval_id,
                request_id=original_request.execution_id,
                correlation_id=original_request.correlation_id,
                organization_id=original_request.organization_id,
                client_id=original_request.client_id,
                actor_identity_id=actor_identity_id,
                capability=original_request.capability_name,
                channel=channel,
                channel_reference_id=channel_reference_id,
                authority_context_id=authority_context_id,
                reason_code=reason_code,
                evidence_references=tuple(evidence_references),
                metadata=dict(metadata or {}),
            )
        )

    @staticmethod
    def _now(value: datetime | None) -> datetime:
        current = value or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("approval flow clock must be timezone-aware")
        return current.astimezone(timezone.utc)
