from __future__ import annotations

from pathlib import Path

from jason_runtime.dynamic_conversation_cutover import (
    DynamicConversationCutoverSettings,
    select_teams_conversation_flow,
)
from orchestrator.dynamic_teams_flow_bridge import DynamicTeamsFlowBridge


class CapabilityRegistry:
    pass


class StructuredClient:
    pass


class Marker:
    pass


def dependencies(tmp_path: Path):
    return {
        "capabilities": CapabilityRegistry(),
        "structured_client": StructuredClient(),
        "identity_binder": Marker(),
        "request_factory": Marker(),
        "orchestrator": Marker(),
        "response_renderer": Marker(),
        "transport": Marker(),
        "continuation_store": Marker(),
        "context_db": tmp_path / "dynamic-context.sqlite3",
    }


def test_disabled_cutover_returns_exact_legacy_flow(tmp_path):
    legacy = Marker()
    deps = dependencies(tmp_path)

    selected = select_teams_conversation_flow(
        settings=DynamicConversationCutoverSettings(
            enabled=False,
            context_db=deps.pop("context_db"),
        ),
        legacy_flow=legacy,
        **deps,
    )

    assert selected is legacy


def test_enabled_cutover_builds_dynamic_bridge_and_reuses_governed_dependencies(
    tmp_path, monkeypatch
):
    legacy = Marker()
    deps = dependencies(tmp_path)
    context_db = deps.pop("context_db")
    coordinator = Marker()
    observed = {}

    def build_coordinator(*, capabilities, structured_client, context_db, ttl_seconds):
        observed.update(
            {
                "capabilities": capabilities,
                "structured_client": structured_client,
                "context_db": context_db,
                "ttl_seconds": ttl_seconds,
            }
        )
        return coordinator

    monkeypatch.setattr(
        "jason_runtime.dynamic_conversation_cutover.build_dynamic_teams_conversation_coordinator",
        build_coordinator,
    )

    selected = select_teams_conversation_flow(
        settings=DynamicConversationCutoverSettings(
            enabled=True,
            context_db=context_db,
            context_ttl_seconds=2700,
        ),
        legacy_flow=legacy,
        **deps,
    )

    assert isinstance(selected, DynamicTeamsFlowBridge)
    assert selected.coordinator is coordinator
    assert selected.identity_binder is deps["identity_binder"]
    assert selected.request_factory is deps["request_factory"]
    assert selected.orchestrator is deps["orchestrator"]
    assert selected.response_renderer is deps["response_renderer"]
    assert selected.transport is deps["transport"]
    assert selected.continuation_store is deps["continuation_store"]
    assert observed == {
        "capabilities": deps["capabilities"],
        "structured_client": deps["structured_client"],
        "context_db": context_db,
        "ttl_seconds": 2700,
    }


def test_cutover_does_not_accept_provider_or_semantic_mapping_dependencies(tmp_path):
    import inspect

    parameters = set(inspect.signature(select_teams_conversation_flow).parameters)

    assert "providers" not in parameters
    assert "semantic_mapping_registry" not in parameters
    assert "fact_vocabulary" not in parameters
    assert "fact_resolver" not in parameters
    assert "provider_capability_map" not in parameters


def test_cutover_ttl_is_bounded():
    for ttl in (0, 59, 86401):
        try:
            DynamicConversationCutoverSettings(context_ttl_seconds=ttl)
        except ValueError as error:
            assert "ttl" in str(error)
        else:
            raise AssertionError("unbounded dynamic context ttl was accepted")
