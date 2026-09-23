from __future__ import annotations

from orchestrator.conversation_response import GovernedTeamsConversationResponseRenderer
from orchestrator.dynamic_resource_response import (
    DynamicEvidenceReasoner,
    GovernedDynamicTeamsResourceResponseRenderer,
)


def select_conversation_response_renderer(
    *,
    dynamic_enabled: bool,
    legacy_renderer,
    structured_client,
):
    """Replace only observe-mode evidence rendering when dynamic conversation is enabled.

    Action rendering remains the existing governed conversation renderer.  The dynamic
    read renderer receives no semantic mapping registry, canonical fact vocabulary,
    provider-field map, or question-specific routing dependency.
    """

    if not dynamic_enabled:
        return legacy_renderer

    return GovernedTeamsConversationResponseRenderer(
        resource_renderer=GovernedDynamicTeamsResourceResponseRenderer(
            reasoner=DynamicEvidenceReasoner(structured_client)
        )
    )
