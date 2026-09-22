from __future__ import annotations

from dataclasses import dataclass

import pytest

from connectors.core.contracts import ConnectorContext, ConnectorRequest
from connectors.microsoft_graph.sharepoint_read import MicrosoftSharePointReadConnector


@dataclass
class FakeToken:
    access_token: str = "secret-token"


class FakeTokens:
    def __init__(self):
        self.calls = []

    def acquire_for_client(self, *, client_id: str, correlation_id: str):
        self.calls.append((client_id, correlation_id))
        return FakeToken()


class FakeTransport:
    def __init__(self):
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        return {"value": [{"id": "result-1"}]}


class FakeAudit:
    def __init__(self):
        self.events = []

    def record(self, event_type, context, details):
        self.events.append((event_type, context.capability, dict(details)))


def request(capability: str, arguments: dict, *, organization_id: str = "aot", mode: str = "observe"):
    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr-1",
            principal_id="person-al",
            organization_id=organization_id,
            client_id=None,
            capability=capability,
            mode=mode,
        ),
        arguments=arguments,
    )


def connector():
    tokens, transport, audit = FakeTokens(), FakeTransport(), FakeAudit()
    return MicrosoftSharePointReadConnector(tokens=tokens, transport=transport, audit=audit), tokens, transport, audit


def test_site_search_is_read_only_and_audited():
    c, tokens, transport, audit = connector()
    result = c.execute(request("microsoft_sharepoint.site.search", {"query": "AOT"}))
    assert result.provider == "microsoft_sharepoint"
    assert tokens.calls == [("client-aot-internal", "corr-1")]
    call = transport.calls[0]
    assert call["method"] == "GET"
    assert call["url"] == "https://graph.microsoft.com/v1.0/sites"
    assert call["params"]["search"] == "AOT"
    assert "secret-token" not in str(audit.events)
    assert [e[0] for e in audit.events] == ["connector.requested", "connector.completed"]


def test_document_search_uses_graph_search_without_write_authority():
    c, _, transport, _ = connector()
    c.execute(request("microsoft_sharepoint.document.search", {"query": "patch policy", "page_size": 500}))
    call = transport.calls[0]
    assert call["method"] == "POST"
    assert call["url"].endswith("/search/query")
    body = call["json"]["requests"][0]
    assert body["entityTypes"] == ["driveItem"]
    assert body["query"]["queryString"] == "patch policy"
    assert body["size"] == 100


def test_non_aot_organization_fails_closed():
    c, _, transport, _ = connector()
    with pytest.raises(Exception, match="AOT organization boundary"):
        c.execute(request("microsoft_sharepoint.site.search", {"query": "AOT"}, organization_id="other"))
    assert transport.calls == []


def test_execute_mode_is_rejected():
    c, _, transport, _ = connector()
    with pytest.raises(Exception, match="read-only"):
        c.execute(request("microsoft_sharepoint.site.search", {"query": "AOT"}, mode="execute"))
    assert transport.calls == []
