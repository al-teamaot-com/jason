"""Small composition helper for Jason's dynamic provider-independent conversation path."""

from __future__ import annotations

from pathlib import Path

from kernel.capabilities import CapabilityRegistryService

from .dynamic_capability_catalog import RegistryBackedDynamicCapabilityCatalog
from .dynamic_conversation_context_store import SQLiteDynamicConversationContextStore
from .dynamic_conversation_intent import GroundedConversationIntentBuilder
from .dynamic_conversation_kernel import DynamicConversationResolver
from .dynamic_teams_conversation import DynamicTeamsConversationCoordinator


def build_dynamic_teams_conversation_coordinator(
    *,
    capabilities: CapabilityRegistryService,
    structured_client,
    context_db: str | Path,
    ttl_seconds: int = 3600,
    continuation_store=None,
) -> DynamicTeamsConversationCoordinator:
    """Compose the dynamic conversation kernel from existing governed runtime resources.

    The structured client is reasoning-only: it has no connector handles, provider
    credentials, authority grants, or direct execution surface.  Capabilities are read
    from current registry truth each turn, and execution remains outside this helper.

    Conversation continuity reuses bounded selector state already persisted by the
    governed Teams flow.  That avoids a post-response model pass whose only job was to
    rediscover structured state Jason already owns.
    """

    return DynamicTeamsConversationCoordinator(
        context_store=SQLiteDynamicConversationContextStore(
            context_db,
            ttl_seconds=ttl_seconds,
        ),
        capability_catalog=RegistryBackedDynamicCapabilityCatalog(
            registry=capabilities,
            include_pilot=True,
        ),
        resolver=DynamicConversationResolver(client=structured_client),
        intent_builder=GroundedConversationIntentBuilder(client=structured_client),
        observer=None,
        continuation_store=continuation_store,
    )
