from __future__ import annotations

import inspect

from jason_runtime.dynamic_response_cutover import select_conversation_response_renderer
from orchestrator.conversation_response import GovernedTeamsConversationResponseRenderer
from orchestrator.dynamic_resource_response import GovernedDynamicTeamsResourceResponseRenderer


class FakeClient:
    def complete(self, **kwargs):
        raise AssertionError("not called during composition")


def test_disabled_returns_exact_legacy_renderer() -> None:
    legacy = object()
    selected = select_conversation_response_renderer(
        dynamic_enabled=False,
        legacy_renderer=legacy,
        structured_client=FakeClient(),
    )
    assert selected is legacy


def test_enabled_uses_mapping_free_dynamic_read_renderer() -> None:
    selected = select_conversation_response_renderer(
        dynamic_enabled=True,
        legacy_renderer=object(),
        structured_client=FakeClient(),
    )
    assert isinstance(selected, GovernedTeamsConversationResponseRenderer)
    assert isinstance(selected.resource_renderer, GovernedDynamicTeamsResourceResponseRenderer)


def test_selector_has_no_static_semantic_dependencies() -> None:
    params = set(inspect.signature(select_conversation_response_renderer).parameters)
    forbidden = {
        "semantic_mapping_registry",
        "fact_vocabulary",
        "fact_resolver",
        "provider_capability_map",
        "canonical_facts",
    }
    assert params.isdisjoint(forbidden)
