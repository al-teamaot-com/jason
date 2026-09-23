from __future__ import annotations

import json
from urllib.error import HTTPError

import pytest

from connectors.backup_net.client import (
    BACKUP_NET_API_URL,
    BACKUP_NET_AUTH_URL,
    BackupNetClient,
)
from connectors.core.contracts import (
    ConnectorTransportError,
    connector_execution_deadline,
)


CUSTOMER_ID = "d28a556c-d8de-48f9-8a64-90fdf03ec4d0"


class FakeResponse:
    def __init__(self, value):
        self.raw = json.dumps(value).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.raw

class FakeOpener:
    def __init__(self):
        self.requests = []
        self.timeouts = []

    def open(self, request, timeout):
        self.requests.append(request)
        self.timeouts.append(timeout)
        if len(self.requests) == 1:
            return FakeResponse(
                {
                    "access_token": "opaque-access-token",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                }
            )
        return FakeResponse(
            [
                {
                    "id": "asset-1",
                    "name": "DGV-50859",
                    "customerId": CUSTOMER_ID,
                }
            ]
        )


def test_client_uses_documented_oauth_flow_and_bearer_api_request():
    opener = FakeOpener()
    client = BackupNetClient(
        {"client_id": "client-id", "client_secret": "client-secret"},
        opener=opener,
    )
    result = client.get(
        "/api/epb/v1/assets",
        {"customer_id": CUSTOMER_ID, "name": "DGV-50859"},
    )

    token_request, api_request = opener.requests
    assert token_request.full_url == BACKUP_NET_AUTH_URL
    assert token_request.get_method() == "POST"
    token_body = token_request.data.decode("utf-8")
    assert token_body == "grant_type=client_credentials"
    assert "client-id" not in token_body
    assert "client-secret" not in token_body
    assert token_request.get_header("Authorization") == (
        "Basic Y2xpZW50LWlkOmNsaWVudC1zZWNyZXQ="
    )

    assert api_request.full_url.startswith(
        BACKUP_NET_API_URL + "/api/epb/v1/assets?"
    )
    assert "customer_id=" in api_request.full_url
    assert "client-secret" not in api_request.full_url
    assert api_request.get_header("Authorization") == "Bearer opaque-access-token"
    assert result["items"][0]["name"] == "DGV-50859"


class FailingOpener:
    def open(self, request, timeout):
        raise HTTPError(
            request.full_url,
            401,
            "secret-response-body",
            hdrs=None,
            fp=None,
        )


def test_http_failure_is_redacted_and_does_not_echo_credentials():
    client = BackupNetClient(
        {"client_id": "client-id", "client_secret": "very-secret-value"},
        opener=FailingOpener(),
    )
    with pytest.raises(ConnectorTransportError) as captured:
        client.get("/api/epb/v1/assets", {"customer_id": CUSTOMER_ID})
    message = str(captured.value)
    assert "401" in message
    assert "very-secret-value" not in message
    assert "secret-response-body" not in message


def test_client_honors_shared_governed_execution_deadline():
    opener = FakeOpener()
    client = BackupNetClient(
        {"client_id": "client-id", "client_secret": "client-secret"},
        opener=opener,
    )

    with connector_execution_deadline(0.5):
        client.get(
            "/api/epb/v1/assets",
            {"customer_id": CUSTOMER_ID, "name": "DGV-50859"},
        )

    assert len(opener.timeouts) == 2
    assert all(0 < value <= 0.5 for value in opener.timeouts)
