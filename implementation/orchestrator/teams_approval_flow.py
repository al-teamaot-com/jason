"""End-to-end governed Teams approval response flow.

This composition layer wires existing trust boundaries without collapsing them:
Microsoft token verification -> Teams ingress identity binding -> provider-neutral
approval validation -> JKD-001 durable approval/re-authorization -> resumed
orchestration request carrying a fresh execution context.

Teams and Microsoft authentication remain inputs to Jason authority, never the
authority themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Protocol

from connectors.microsoft_graph.teams_approval_ingress import (
    TeamsApprovalIngress,
    VerifiedMicrosoftPrincipal,
)
from connectors.src.jason_connectors.approval_requests import (
    AcceptedApproval,
    ApprovalRequestService,
)

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

        Denials are valid approval outcomes but never resume execution. Any failed
        authentication, tenant binding, identity binding, approval authorization,
        expiration, scope, or JKD-001 re-authorization check raises and leaves the
        caller without a resumed execution request.
        """

        principal = self.token_verifier.verify(token)
        response = self.ingress.accept_verified_interaction(
            principal=principal,
            payload=payload,
            decided_at=decided_at,
        )
        accepted = self.approval_service.accept_response(response, now=now)

        if accepted.status != "approved":
            return TeamsApprovalFlowResult(
                accepted_approval=accepted,
                resumed_request=None,
            )

        resumed = self.resume_bridge.resume(
            original_request=original_request,
            accepted=accepted,
            authentication_assurance=principal.authentication_assurance,
        )
        return TeamsApprovalFlowResult(
            accepted_approval=accepted,
            resumed_request=resumed,
        )
