from __future__ import annotations

from orchestrator.conversation_response import GovernedTeamsConversationResponseRenderer
from orchestrator.teams_conversation_flow import ConversationIntent


class ResourceRenderer:
    def __init__(self, text: str) -> None:
        self.text = text

    def render(self, result, intent):
        return self.text


def intent(*facts: str) -> ConversationIntent:
    return ConversationIntent(
        capability_name="endpoint.device.search",
        arguments={
            "hostname": "AOT-50107",
            "requested_facts": facts,
        },
        execution_mode="deterministic",
        permission_mode="observe",
    )


def test_timestamp_fact_formats_unix_milliseconds_for_human_output():
    renderer = GovernedTeamsConversationResponseRenderer(
        ResourceRenderer(
            "AOT-50107 — endpoint last seen: 1787134597000. Source: datto_rmm."
        )
    )

    text = renderer.render(object(), intent("endpoint last seen"))

    assert text == (
        "AOT-50107 — endpoint last seen: 2026-08-19 10:16:37 UTC. "
        "Source: datto_rmm."
    )


def test_timestamp_fact_formats_unix_seconds_through_same_semantic_contract():
    renderer = GovernedTeamsConversationResponseRenderer(
        ResourceRenderer(
            "Ticket — endpoint last seen: 1787134597. Source: example_provider."
        )
    )

    text = renderer.render(object(), intent("endpoint last seen"))

    assert "endpoint last seen: 2026-08-19 10:16:37 UTC" in text


def test_non_timestamp_fact_is_not_rewritten():
    original = (
        "AOT-50107 — LAN IP address: 192.168.1.155; "
        "WAN IP address: 71.120.253.76. Source: datto_rmm."
    )
    renderer = GovernedTeamsConversationResponseRenderer(ResourceRenderer(original))

    assert renderer.render(object(), intent("ip address")) == original


def test_unknown_numeric_timestamp_width_is_not_guessed():
    original = "AOT-50107 — endpoint last seen: 178713459700. Source: datto_rmm."
    renderer = GovernedTeamsConversationResponseRenderer(ResourceRenderer(original))

    assert renderer.render(object(), intent("endpoint last seen")) == original
