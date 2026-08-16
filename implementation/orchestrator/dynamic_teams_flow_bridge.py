"""Cutover bridge from dynamic conversation planning into the existing governed Teams flow.

The bridge deliberately reuses TeamsConversationFlow for authority-bound request creation,
Central Orchestrator execution, response rendering, continuation handling, and transport.
It changes only how conversational intent is resolved.  The dynamic coordinator sees the
bound Teams identity, provider-independent conversation context, and the runtime capability
catalog; it does not invoke providers or grant authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .dynamic_teams_conversation import DynamicTeamsConversationCoordinator
from .teams_conversation_flow import (
    BoundConversationPrincipal,
    ConversationIntent,
    ConversationIntentPlan,
    TeamsConversationFlow,
    TeamsConversationFlowResult,
    TeamsConversationRequest,
)


class _BoundIdentityBinder:
    def __init__(self, principal: BoundConversationPrincipal) -> None:
        self._principal = principal

    def bind(self, evidence):
        return self._principal


class _ResolvedIntentResolver:
    def __init__(self, resolved: ConversationIntent | ConversationIntentPlan) -> None:
        self._resolved = resolved

    def resolve(self, *, text, principal):
        return self._resolved


class _CapturingTransport:
    def __init__(self, delegate) -> None:
        self._delegate = delegate
        self.last_text: str | None = None

    def send(self, *, conversation_id: str, text: str, correlation_id: str) -> str:
        self.last_text = text
        return self._delegate.send(
            conversation_id=conversation_id,
            text=text,
            correlation_id=correlation_id,
        )


@dataclass(frozen=True, slots=True)
class DynamicTeamsFlowBridge:
    """Use dynamic context/capability reasoning while preserving Jason governance."""

    identity_binder: object
    coordinator: DynamicTeamsConversationCoordinator
    request_factory: object
    orchestrator: object
    response_renderer: object
    transport: object
    continuation_store: object | None = None

    def handle(self, request: TeamsConversationRequest) -> TeamsConversationFlowResult:
        principal = self.identity_binder.bind(request.identity)
        if principal is None:
            raise PermissionError("Teams identity is not bound to a governed Jason principal")

        resolved = self.coordinator.resolve_turn(
            text=request.text.strip(),
            principal=principal,
            identity=request.identity,
        )
        if resolved is None:
            # Conversation-only responses need a dedicated governed response path rather
            # than pretending a provider capability was requested.  Until that response
            # path is wired, fail closed without provider execution.
            raise LookupError("dynamic conversation turn did not require a governed capability")

        capture = _CapturingTransport(self.transport)
        governed_flow = TeamsConversationFlow(
            identity_binder=_BoundIdentityBinder(principal),
            intent_resolver=_ResolvedIntentResolver(resolved),
            request_factory=self.request_factory,
            orchestrator=self.orchestrator,
            response_renderer=self.response_renderer,
            transport=capture,
            continuation_store=self.continuation_store,
        )
        result = governed_flow.handle(request)

        if capture.last_text:
            self.coordinator.observe_verified_response(
                principal=principal,
                identity=request.identity,
                response_text=capture.last_text,
            )
        return result
