from __future__ import annotations

import json
from urllib.error import HTTPError

import pytest

from connectors.core.contracts import ConnectorTransportError
from connectors.dnsfilter.mcp_client import DnsFilterMcpClient
from connectors.dnsfilter.mcp_oauth import (
    DnsFilterMcpOAuthError,
    DnsFilterMcpOAuthStore,
)


class FakeResponse:
    def __init__(self, body, content_type="text/event-stream"):
        self._body = body.encode("utf-8")
        self.headers = {"Content-Type": content_type}
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return self._body


class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.requests = []
    def __call__(self, request, timeout):
        self.requests.append(request)
        return self.response


def store(tmp_path):
    value = DnsFilterMcpOAuthStore(tmp_path / "oauth.sqlite3")
    value.set_token({"access_token": "opaque-token", "expires_in": 3600})
    return value


def test_client_calls_exact_mcp_tool_with_bearer_and_parses_sse(tmp_path):
    body = "event: message\ndata: " + json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {"organization_id": 9001, "count": 3}
                        ),
                    }
                ]
            },
        }
    ) + "\n\n"
    opener = FakeOpener(FakeResponse(body))
    client = DnsFilterMcpClient(store(tmp_path), opener=opener)
    result = client.call_tool(
        "pending_unblock_requests_count",
        {"organization_id": 9001},
    )
    request = opener.requests[0]
    payload = json.loads(request.data.decode("utf-8"))
    assert payload["params"]["name"] == "pending_unblock_requests_count"
    assert payload["params"]["arguments"] == {"organization_id": 9001}
    assert request.get_header("Authorization") == "Bearer opaque-token"
    assert result == {"organization_id": 9001, "count": 3}


class UnauthorizedOpener:
    def __call__(self, request, timeout):
        raise HTTPError(request.full_url, 401, "bad token", None, None)


def test_client_converts_401_to_reauthentication_required(tmp_path):
    client = DnsFilterMcpClient(store(tmp_path), opener=UnauthorizedOpener())
    with pytest.raises(DnsFilterMcpOAuthError, match="re-authentication"):
        client.call_tool("get_current_user", {})


def test_provider_tool_error_does_not_echo_tokens(tmp_path):
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32000, "message": "provider denied"},
        }
    )
    opener = FakeOpener(FakeResponse(body, "application/json"))
    client = DnsFilterMcpClient(store(tmp_path), opener=opener)
    with pytest.raises(ConnectorTransportError) as captured:
        client.call_tool("get_current_user", {})
    assert "opaque-token" not in str(captured.value)
