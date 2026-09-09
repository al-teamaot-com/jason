from orchestrator.investigation_turn_router import (
    InvestigationTurnKind,
    InvestigationTurnRouter,
)


class Client:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return dict(self.result)


def route(kind, text):
    client = Client(
        {
            "kind": kind,
        }
    )

    result = InvestigationTurnRouter(
        client=client,
    ).route(
        human_text=text,
    )

    return result, client


def test_generic_information_turn_routes_to_investigation():
    result, client = route(
        "information",
        "Is the endpoint currently healthy?",
    )

    assert result.kind is InvestigationTurnKind.INFORMATION

    system = client.calls[0]["system"]

    assert "Datto" not in system
    assert "hostname" not in system


def test_broad_troubleshooting_is_information():
    result, _ = route(
        "information",
        "Help me figure out what is wrong with this machine.",
    )

    assert result.kind is InvestigationTurnKind.INFORMATION


def test_action_stays_out_of_investigation():
    result, _ = route(
        "action",
        "Restart the affected endpoint.",
    )

    assert result.kind is InvestigationTurnKind.ACTION


def test_conversation_stays_out_of_investigation():
    result, _ = route(
        "conversation",
        "Thanks, that makes sense.",
    )

    assert result.kind is InvestigationTurnKind.CONVERSATION


def test_router_does_not_receive_resource_catalog_or_selector_schema():
    _, client = route(
        "information",
        "Find out whether that system is online.",
    )

    user = client.calls[0]["user"]

    assert "resource_selector" not in user
    assert "operation_ref" not in user
    assert "provider" not in user
    assert "capability" not in user
