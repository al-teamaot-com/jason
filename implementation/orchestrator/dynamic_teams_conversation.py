"""Identity-bound dynamic Teams conversation planning and context continuity.

This coordinator does not invoke providers. It loads provider-independent conversation
state, asks the dynamic planner to select only currently registered capabilities,
grounds the resulting arguments, and persists only bounded context decisions. Normal
Teams request construction, JKD-001 authority, Central Orchestrator execution, provider
selection, evidence verification, and response rendering remain separate concerns.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .dynamic_capability_catalog import RegistryBackedDynamicCapabilityCatalog
from .dynamic_conversation_context_store import SQLiteDynamicConversationContextStore
from .dynamic_conversation_intent import GroundedConversationIntentBuilder
from .dynamic_conversation_kernel import (
    DynamicConversationContext,
    DynamicConversationResolver,
)
from .dynamic_conversation_observer import DynamicConversationEntityObserver
from .teams_conversation_flow import (
    BoundConversationPrincipal,
    ConversationGuidanceRequiredError,
    ConversationIntent,
    ConversationIntentPlan,
    TeamsConversationPrincipalEvidence,
)


class DynamicContextStore(Protocol):
    def get(
        self,
        *,
        organization_id: str,
        principal_id: str,
        conversation_id: str,
    ) -> DynamicConversationContext | None: ...

    def put(self, context: DynamicConversationContext) -> DynamicConversationContext: ...


@dataclass(frozen=True, slots=True)
class DynamicTeamsConversationCoordinator:
    """Resolve one Teams turn without static semantic mappings."""

    context_store: DynamicContextStore
    capability_catalog: RegistryBackedDynamicCapabilityCatalog
    resolver: DynamicConversationResolver
    intent_builder: GroundedConversationIntentBuilder
    observer: DynamicConversationEntityObserver | None = None

    def resolve_turn(
        self,
        *,
        text: str,
        principal: BoundConversationPrincipal,
        identity: TeamsConversationPrincipalEvidence,
    ) -> ConversationIntent | ConversationIntentPlan | None:
        context = self._load_or_create(principal=principal, identity=identity)
        offered = self.capability_catalog.list_offered()
        plan = self.resolver.resolve(
            text=text.strip(),
            context=context,
            capabilities=offered,
        )

        updated = context.with_verified_entities(
            (),
            topic=plan.topic,
            resolutions=plan.resolved_references,
        )
        self.context_store.put(updated)

        if plan.outcome == "clarify":
            raise ConversationGuidanceRequiredError(
                reason_code="dynamic_conversation_clarification",
                guidance_text=plan.clarification_question or "Please clarify the request.",
            )
        if plan.outcome == "conversation":
            return None

        return self.intent_builder.build(
            text=text.strip(),
            context=updated,
            plan=plan,
            capabilities=offered,
        )

    def observe_verified_response(
        self,
        *,
        principal: BoundConversationPrincipal,
        identity: TeamsConversationPrincipalEvidence,
        response_text: str,
    ) -> DynamicConversationContext:
        """Persist only entities grounded in an already verified Jason response."""

        context = self._load_or_create(principal=principal, identity=identity)
        if self.observer is None:
            return context
        observed = self.observer.observe(
            context=context,
            response_text=response_text,
            provenance=f"verified Jason Teams response:{identity.message_id}",
        )
        return self.context_store.put(observed)

    def _load_or_create(
        self,
        *,
        principal: BoundConversationPrincipal,
        identity: TeamsConversationPrincipalEvidence,
    ) -> DynamicConversationContext:
        existing = self.context_store.get(
            organization_id=principal.organization_id,
            principal_id=principal.principal_id,
            conversation_id=identity.conversation_id,
        )
        if existing is not None:
            return existing
        return DynamicConversationContext(
            conversation_id=identity.conversation_id,
            principal_id=principal.principal_id,
            organization_id=principal.organization_id,
        )
