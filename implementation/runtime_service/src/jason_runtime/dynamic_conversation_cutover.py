from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from orchestrator.dynamic_conversation_composition import (
    build_dynamic_teams_conversation_coordinator,
)
from orchestrator.dynamic_teams_flow_bridge import DynamicTeamsFlowBridge

from .dynamic_response_cutover import select_conversation_response_renderer


@dataclass(frozen=True, slots=True)
class DynamicConversationCutoverSettings:
    """Runtime-owned rollout controls for the dynamic conversation path.

    The flag changes only conversational interpretation and read-response evidence
    interpretation. Identity binding, JKD-001 authority, request construction,
    Central Orchestrator execution, provider resolution, transport, and governed
    action rendering remain the existing runtime components.
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
    legacy flow is returned unchanged. When enabled, conversational planning and
    observe-mode evidence rendering use the provider-independent dynamic path; the
    same governed identity, authority, orchestrator, action renderer, continuation,
    and transport objects remain in force.
    """

    if not settings.enabled:
        return legacy_flow

    coordinator = build_dynamic_teams_conversation_coordinator(
        capabilities=capabilities,
        structured_client=structured_client,
        context_db=settings.context_db,
        ttl_seconds=settings.context_ttl_seconds,
    )
    dynamic_response_renderer = select_conversation_response_renderer(
        dynamic_enabled=True,
        legacy_renderer=response_renderer,
        structured_client=structured_client,
    )
    return DynamicTeamsFlowBridge(
        identity_binder=identity_binder,
        coordinator=coordinator,
        request_factory=request_factory,
        orchestrator=orchestrator,
        response_renderer=dynamic_response_renderer,
        transport=transport,
        continuation_store=continuation_store,
    )
