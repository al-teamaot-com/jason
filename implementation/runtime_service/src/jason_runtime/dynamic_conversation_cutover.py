from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from orchestrator.dynamic_conversation_composition import (
    build_dynamic_teams_conversation_coordinator,
)
from orchestrator.dynamic_teams_flow_bridge import DynamicTeamsFlowBridge


@dataclass(frozen=True, slots=True)
class DynamicConversationCutoverSettings:
    """Runtime-owned rollout controls for the dynamic conversation path.

    The flag changes only conversational interpretation. Identity binding, JKD-001
    authority, request construction, Central Orchestrator execution, provider
    resolution, evidence handling, response rendering, and transport remain the
    existing governed runtime components.
    """

    enabled: bool = False
    context_db: Path = Path(
        "/var/lib/jason/openclaw/dynamic-conversation-context.sqlite3"
    )
    context_ttl_seconds: int = 3600

    def __post_init__(self) -> None:
        if self.context_ttl_seconds < 60 or self.context_ttl_seconds > 86400:
            raise ValueError(
                "dynamic conversation context ttl must be between 60 and 86400 seconds"
            )


def select_teams_conversation_flow(
    *,
    settings: DynamicConversationCutoverSettings,
    legacy_flow,
    capabilities,
    structured_client,
    identity_binder,
    request_factory,
    orchestrator,
    response_renderer,
    transport,
    continuation_store=None,
):
    """Return legacy or dynamic Teams flow without changing governance boundaries.

    Rollback is a single configuration decision. When disabled, the exact supplied
    legacy flow is returned unchanged. When enabled, only the conversational resolver
    is replaced by the dynamic provider-independent coordinator; the same governed
    identity, authority, orchestrator, renderer, continuation, and transport objects
    are reused.
    """

    if not settings.enabled:
        return legacy_flow

    coordinator = build_dynamic_teams_conversation_coordinator(
        capabilities=capabilities,
        structured_client=structured_client,
        context_db=settings.context_db,
        ttl_seconds=settings.context_ttl_seconds,
    )
    return DynamicTeamsFlowBridge(
        identity_binder=identity_binder,
        coordinator=coordinator,
        request_factory=request_factory,
        orchestrator=orchestrator,
        response_renderer=response_renderer,
        transport=transport,
        continuation_store=continuation_store,
    )
