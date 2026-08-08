from __future__ import annotations

import pytest

from connectors.core.contracts import ConnectorConfigurationError
from connectors.datto_rmm.auth import acquire_access_token, require_durable_credentials


class RecordingTransport:
    def __init__(self, payload=None):
        self.payload = payload or {
            "access_token": "runtime-token",
            "token_type": "Bearer",
            "expires_in": 360000,
        }
        self.calls = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        return self.payload


def credentials():
    return {
        "api_url": "https://example.invalid",
        "api_key": "synthetic-key",
        "api_secret": "synthetic-secret",
    }


def test_durable_contract_rejects_persisted_token_shape():
    with pytest.raises(ConnectorConfigurationError, match="api_url"):
        require_durable_credentials(
            {"base_url": "https://example.invalid", "access_token": "old-token"}
        )


def test_token_is_acquired_at_runtime_from_durable_credentials():
    transport = RecordingTransport()
    token = acquire_access_token(credentials=credentials(), transport=transport)

    assert token.access_token == "runtime-token"
    assert token.token_type == "Bearer"
    assert token.expires_in == 360000
    assert transport.calls == [
        {
            "method": "POST",
            "url": "https://example.invalid/auth/oauth/token",
            "headers": {"Accept": "application/json"},
            "params": None,
            "json": {
                "grant_type": "password",
                "username": "synthetic-key",
                "password": "synthetic-secret",
            },
            "timeout_seconds": 30.0,
        }
    ]


def test_missing_access_token_fails_closed():
    transport = RecordingTransport(payload={"token_type": "Bearer"})
    with pytest.raises(ConnectorConfigurationError, match="access token"):
        acquire_access_token(credentials=credentials(), transport=transport)
