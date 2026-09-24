from __future__ import annotations

import json
from urllib.error import HTTPError

import pytest

from connectors.core.contracts import ConnectorConfigurationError, ConnectorTransportError
from connectors.dnsfilter.client import DNSFILTER_API_URL, DnsFilterClient


class FakeResponse:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode("utf-8")
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return self._raw


class FakeOpener:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []
        self.timeouts = []
    def open(self, request, timeout):
        self.requests.append(request)
        self.timeouts.append(timeout)
        return FakeResponse(self.payload)


def test_client_uses_documented_api_key_header_and_scoped_get():
    opener = FakeOpener({"data": []})
    client = DnsFilterClient({"api_key": "secret-key"}, opener=opener)
    result = client.get(
        "/v1/user_agents",
        {"organization_ids": [123], "agent_state": "protected"},
    )
    request = opener.requests[0]
    assert request.get_method() == "GET"
    assert request.full_url.startswith(DNSFILTER_API_URL + "/v1/user_agents?")
    assert "organization_ids=123" in request.full_url
    assert request.get_header("Authorization") == "secret-key"
    assert result == {"data": []}


def test_client_rejects_unregistered_provider_paths_before_request():
    opener = FakeOpener({})
    client = DnsFilterClient({"api_key": "secret-key"}, opener=opener)
    with pytest.raises(ConnectorConfigurationError, match="allowlisted"):
        client.get("/v1/user_agents/00000000-0000-0000-0000-000000000001")
    assert opener.requests == []


class FailingOpener:
    def open(self, request, timeout):
        raise HTTPError(request.full_url, 401, "provider-secret-body", None, None)


def test_http_error_is_redacted():
    client = DnsFilterClient({"api_key": "very-secret"}, opener=FailingOpener())
    with pytest.raises(ConnectorTransportError) as captured:
        client.get("/v1/policies", {"organization_id": 123})
    message = str(captured.value)
    assert "401" in message
    assert "very-secret" not in message
    assert "provider-secret-body" not in message
