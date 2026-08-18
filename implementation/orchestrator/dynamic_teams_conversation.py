"""Identity-bound dynamic Teams conversation planning and context continuity.

This coordinator does not invoke providers. It loads provider-independent conversation
state, asks the dynamic planner to select only currently registered capabilities,
grounds the resulting arguments, and persists only bounded context decisions. Normal
Teams request construction, JKD-001 authority, Central Orchestrator execution, provider
selection, evidence verification, and response rendering remain separate concerns.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Protocol

from .dynamic_capability_catalog import RegistryBackedDynamicCapabilityCatalog
from .dynamic_conversation_context_store import SQLiteDynamicConversationContextStore
from .dynamic_conversation_intent import GroundedConversationIntentBuilder
from .dynamic_conversation_kernel import (
    ConversationEntity,
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


class GovernedContinuationStore(Protocol):
    def get(
        self,
        *,
        organization_id: str,
        principal_id: str,
        conversation_id: str,
    ): ...


@dataclass(frozen=True, slots=True)
class DynamicTeamsConversationCoordinator:
    """Resolve one Teams turn without static semantic mappings."""

    context_store: DynamicContextStore
    capability_catalog: RegistryBackedDynamicCapabilityCatalog
    resolver: DynamicConversationResolver
    intent_builder: GroundedConversationIntentBuilder
    observer: DynamicConversationEntityObserver | None = None
    continuation_store: GovernedContinuationStore | None = None

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
        """Optional compatibility path for model-assisted response observation.

        Normal dynamic Teams continuity no longer requires this call: successful
        governed resource selectors are already persisted by TeamsConversationFlow and
        are rehydrated deterministically on the following turn.  Keeping this method
        preserves an explicit opt-in path for future richer entity observation without
        making it part of the critical conversational latency path.
        """

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
        context = existing or DynamicConversationContext(
            conversation_id=identity.conversation_id,
            principal_id=principal.principal_id,
            organization_id=principal.organization_id,
        )
        hydrated = self._hydrate_governed_continuation(
            context=context,
            principal=principal,
            identity=identity,
        )
        if hydrated is not context:
            self.context_store.put(hydrated)
        return hydrated

    def _hydrate_governed_continuation(
        self,
        *,
        context: DynamicConversationContext,
        principal: BoundConversationPrincipal,
        identity: TeamsConversationPrincipalEvidence,
    ) -> DynamicConversationContext:
        """Reuse already-governed selector state without another semantic model pass.

        TeamsConversationFlow records only bounded selector strings from a successful
        governed result.  Reusing those exact strings is deterministic state transfer,
        not semantic mapping: selector names remain whatever the runtime capability
        contract supplied and no provider, question, synonym, or field rule is added.
        """

        if self.continuation_store is None:
            return context
        state = self.continuation_store.get(
            organization_id=principal.organization_id,
            principal_id=principal.principal_id,
            conversation_id=identity.conversation_id,
        )
        if state is None or state.response_kind != "result" or not state.resource_selector:
            return context

        entities: list[ConversationEntity] = []
        active: dict[str, str] = {}
        provenance = (
            "governed Teams continuation selector:"
            f"{state.last_message_id}"
        )
        for raw_key, raw_value in state.resource_selector.items():
            key = str(raw_key).strip()
            value = str(raw_value).strip()
            if not key or not value:
                continue
            kind = _selector_kind(key)
            ref = _continuation_entity_ref(key=key, value=value)
            entities.append(
                ConversationEntity(
                    ref=ref,
                    kind=kind,
                    canonical_id=value,
                    display_name=value,
                    provenance=provenance,
                )
            )
            active[kind] = ref

        if not entities:
            return context
        return context.with_verified_entities(
            entities,
            active_kinds=active,
        )


def _selector_kind(key: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", key.strip()).strip("_.-")
    if not normalized:
        normalized = "value"
    return f"selector.{normalized}"[:64]


def _continuation_entity_ref(*, key: str, value: str) -> str:
    digest = hashlib.sha256(
        f"{key.casefold()}\0{value.casefold()}".encode("utf-8")
    ).hexdigest()[:20]
    return f"entity-{digest}"
