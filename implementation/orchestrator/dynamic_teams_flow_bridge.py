"""Cutover bridge from dynamic conversation planning into the existing governed Teams flow.

The bridge deliberately reuses TeamsConversationFlow for authority-bound request creation,
Central Orchestrator execution, response rendering, continuation handling, and transport.
It changes only how conversational intent is resolved.  The dynamic coordinator sees the
bound Teams identity, provider-independent conversation context, and the runtime capability
catalog; it does not invoke providers or grant authority.
"""

from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(frozen=True, slots=True)
class DynamicTeamsFlowBridge:
    """Use dynamic context/capability reasoning while preserving Jason governance.

    Successful TeamsConversationFlow execution already persists bounded continuation
    state after the governed result is rendered.  Dynamic context consumes that state
    on the next turn, so the bridge intentionally does not perform an additional
    model-based response observation after transport delivery.
    """

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

        governed_flow = TeamsConversationFlow(
            identity_binder=_BoundIdentityBinder(principal),
            intent_resolver=_ResolvedIntentResolver(resolved),
            request_factory=self.request_factory,
            orchestrator=self.orchestrator,
            response_renderer=self.response_renderer,
            transport=self.transport,
            continuation_store=self.continuation_store,
        )
        return governed_flow.handle(request)
