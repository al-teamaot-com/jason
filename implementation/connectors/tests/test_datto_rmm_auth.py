from __future__ import annotations

import json
import urllib.parse

import pytest

from connectors.core.contracts import ConnectorConfigurationError
from connectors.datto_rmm.auth import acquire_access_token, require_durable_credentials


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def credentials() -> dict[str, str]:
    return {
        "api_url": "https://vidal-api.centrastage.net",
        "api_key": "synthetic-key",
        "api_secret": "synthetic-secret",
    }


def test_durable_contract_rejects_persisted_bearer_token() -> None:
    bad = credentials()
    bad["access_token"] = "must-not-persist"
    with pytest.raises(ConnectorConfigurationError, match="runtime-only"):
        require_durable_credentials(bad)


def test_token_exchange_uses_documented_password_grant_and_public_client() -> None:
    calls = []

    def opener(req, timeout):
        calls.append((req, timeout))
        return FakeResponse(
            {
                "access_token": "runtime-token",
                "token_type": "bearer",
                "expires_in": 360000,
            }
        )

    token = acquire_access_token(credentials=credentials(), opener=opener)
    assert token.access_token == "runtime-token"
    assert token.token_type == "bearer"
    assert token.expires_in == 360000
    assert len(calls) == 1
    req, timeout = calls[0]
    assert timeout == 30.0
    assert req.full_url == "https://vidal-api.centrastage.net/auth/oauth/token"
    assert req.get_method() == "POST"
    assert req.headers["Content-type"] == "application/x-www-form-urlencoded"
    assert req.headers["Authorization"].startswith("Basic ")
    form = urllib.parse.parse_qs(req.data.decode("utf-8"))
    assert form == {
        "grant_type": ["password"],
        "username": ["synthetic-key"],
        "password": ["synthetic-secret"],
    }


def test_missing_access_token_fails_closed() -> None:
    def opener(req, timeout):
        return FakeResponse({"token_type": "Bearer"})

    with pytest.raises(ConnectorConfigurationError, match="access token"):
        acquire_access_token(credentials=credentials(), opener=opener)
