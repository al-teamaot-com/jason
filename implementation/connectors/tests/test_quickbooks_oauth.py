from __future__ import annotations

import time
from io import BytesIO
from urllib.error import HTTPError

import pytest

from connectors.quickbooks import oauth
from connectors.quickbooks.oauth import (
    QUICKBOOKS_PRODUCTION_REDIRECT_URI_DEFAULT,
    QUICKBOOKS_SCOPE,
    QuickBooksOAuthError,
    QuickBooksOAuthStore,
    QuickBooksReconnectRequiredError,
    begin_quickbooks_oauth,
    complete_quickbooks_oauth,
    disconnect_quickbooks_oauth,
    quickbooks_access_context,
    refresh_quickbooks_oauth,
)


_REAL_LOAD_OAUTH_ENDPOINTS = oauth._load_oauth_endpoints


@pytest.fixture(autouse=True)
def _stable_intuit_discovery(monkeypatch):
    monkeypatch.setattr(
        oauth,
        "_load_oauth_endpoints",
        lambda environment: oauth.QuickBooksOAuthEndpoints(
            authorization_endpoint="https://appcenter.intuit.com/connect/oauth2",
            token_endpoint="https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
            revocation_endpoint="https://developer.api.intuit.com/v2/oauth2/tokens/revoke",
        ),
    )


def test_begin_oauth_persists_bounded_state_and_accounting_scope(tmp_path):
    store = QuickBooksOAuthStore(tmp_path / "oauth.sqlite3")

    url = begin_quickbooks_oauth(
        store,
        client_id="public-client-id",
        environment="sandbox",
        redirect_uri="https://mcp-jason.teamaot.com/oauth/quickbooks/callback",
    )

    assert "client_id=public-client-id" in url
    assert "client_secret" not in url
    assert "com.intuit.quickbooks.accounting" in url
    assert "payment" not in url.casefold()
    assert store.status().pending_authorization is True


def test_begin_production_oauth_is_accounting_only_and_uses_production_callback(tmp_path):
    store = QuickBooksOAuthStore(tmp_path / "production-oauth.sqlite3")
    url = begin_quickbooks_oauth(
        store,
        client_id="production-public-client-id",
        environment="production",
        redirect_uri=QUICKBOOKS_PRODUCTION_REDIRECT_URI_DEFAULT,
    )
    assert "client_id=production-public-client-id" in url
    assert "quickbooks%2Fproduction%2Fcallback" in url
    assert "com.intuit.quickbooks.accounting" in url
    assert "payment" not in url.casefold()
    assert store.status().pending_authorization is True


def test_callback_state_is_single_use_and_realm_is_server_derived(tmp_path, monkeypatch):
    store = QuickBooksOAuthStore(tmp_path / "oauth.sqlite3")
    url = begin_quickbooks_oauth(
        store,
        client_id="public-client-id",
        environment="sandbox",
    )
    state = url.split("state=", 1)[1].split("&", 1)[0]

    monkeypatch.setattr(
        oauth,
        "_token_request",
        lambda **kwargs: {
            "access_token": "short-lived-access",
            "refresh_token": "rotating-refresh",
            "expires_in": 3600,
        },
    )

    status = complete_quickbooks_oauth(
        store,
        credentials={
            "client_id": "public-client-id",
            "client_secret": "private-secret",
        },
        code="one-time-code",
        state=state,
        realm_id="1234567890123456",
    )

    assert status.connected is True
    assert status.environment == "sandbox"
    assert status.realm_id == "1234567890123456"
    assert status.has_refresh_token is True
    assert status.pending_authorization is False

    with pytest.raises(QuickBooksOAuthError, match="missing or expired"):
        complete_quickbooks_oauth(
            store,
            credentials={
                "client_id": "public-client-id",
                "client_secret": "private-secret",
            },
            code="replayed-code",
            state=state,
            realm_id="1234567890123456",
        )


def test_access_context_refreshes_and_persists_newest_refresh_token(tmp_path, monkeypatch):
    store = QuickBooksOAuthStore(tmp_path / "oauth.sqlite3")
    store.set_token(
        {
            "access_token": "old-access",
            "refresh_token": "old-refresh",
            "expires_in": 1,
        },
        realm_id="1234567890123456",
        environment="sandbox",
    )

    monkeypatch.setattr(
        oauth,
        "_token_request",
        lambda **kwargs: {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
        },
    )

    access, realm, environment = quickbooks_access_context(
        store,
        credentials={
            "client_id": "public-client-id",
            "client_secret": "private-secret",
        },
        refresh_window_seconds=120,
    )

    assert access == "new-access"
    assert realm == "1234567890123456"
    assert environment == "sandbox"
    assert store.get_token()["refresh_token"] == "new-refresh"


def test_invalid_realm_id_fails_closed(tmp_path, monkeypatch):
    store = QuickBooksOAuthStore(tmp_path / "oauth.sqlite3")
    url = begin_quickbooks_oauth(store, client_id="public-client-id")
    state = url.split("state=", 1)[1].split("&", 1)[0]
    monkeypatch.setattr(
        oauth,
        "_token_request",
        lambda **kwargs: {
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_in": 3600,
        },
    )

    with pytest.raises(QuickBooksOAuthError, match="Realm ID"):
        complete_quickbooks_oauth(
            store,
            credentials={
                "client_id": "public-client-id",
                "client_secret": "private-secret",
            },
            code="code",
            state=state,
            realm_id="../../other-company",
        )


class _DiscoveryResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._payload


def test_discovery_document_supplies_current_oauth_endpoints(monkeypatch):
    payload = (
        b'{"authorization_endpoint":"https://appcenter.intuit.com/connect/oauth2",'
        b'"token_endpoint":"https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",'
        b'"revocation_endpoint":"https://developer.api.intuit.com/v2/oauth2/tokens/revoke"}'
    )
    monkeypatch.setattr(
        oauth,
        "urlopen",
        lambda request, timeout: _DiscoveryResponse(payload),
    )

    endpoints = _REAL_LOAD_OAUTH_ENDPOINTS("sandbox")

    assert endpoints.authorization_endpoint == "https://appcenter.intuit.com/connect/oauth2"
    assert endpoints.token_endpoint == "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
    assert endpoints.revocation_endpoint == "https://developer.api.intuit.com/v2/oauth2/tokens/revoke"


def test_discovery_document_rejects_untrusted_endpoint(monkeypatch):
    payload = (
        b'{"authorization_endpoint":"https://evil.example/connect/oauth2",'
        b'"token_endpoint":"https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",'
        b'"revocation_endpoint":"https://developer.api.intuit.com/v2/oauth2/tokens/revoke"}'
    )
    monkeypatch.setattr(
        oauth,
        "urlopen",
        lambda request, timeout: _DiscoveryResponse(payload),
    )

    with pytest.raises(QuickBooksOAuthError, match="untrusted endpoint"):
        _REAL_LOAD_OAUTH_ENDPOINTS("sandbox")


def test_invalid_grant_requires_reconnect_without_echoing_provider_detail(monkeypatch):
    error = HTTPError(
        url="https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
        code=400,
        msg="Bad Request",
        hdrs=None,
        fp=BytesIO(b'{"error":"invalid_grant","error_description":"sensitive detail"}'),
    )
    monkeypatch.setattr(oauth, "urlopen", lambda request, timeout: (_ for _ in ()).throw(error))

    with pytest.raises(QuickBooksReconnectRequiredError, match="reconnect is required") as excinfo:
        oauth._token_request(
            client_id="public-client-id",
            client_secret="private-secret",
            environment="sandbox",
            form={"grant_type": "refresh_token", "refresh_token": "expired-refresh"},
        )

    assert "sensitive detail" not in str(excinfo.value)


def test_invalid_refresh_grant_clears_oauth_state_and_requires_reconnect(tmp_path, monkeypatch):
    store = QuickBooksOAuthStore(tmp_path / "oauth.sqlite3")
    store.set_token(
        {
            "access_token": "old-access",
            "refresh_token": "expired-refresh",
            "expires_in": 1,
        },
        realm_id="1234567890123456",
        environment="sandbox",
    )
    monkeypatch.setattr(
        oauth,
        "_token_request",
        lambda **kwargs: (_ for _ in ()).throw(
            QuickBooksReconnectRequiredError("reconnect is required")
        ),
    )

    with pytest.raises(QuickBooksReconnectRequiredError):
        refresh_quickbooks_oauth(
            store,
            credentials={
                "client_id": "public-client-id",
                "client_secret": "private-secret",
            },
        )

    status = store.status()
    assert status.connected is False
    assert status.has_refresh_token is False


def test_disconnect_then_reconnect_establishes_fresh_sandbox_authorization(tmp_path, monkeypatch):
    store = QuickBooksOAuthStore(tmp_path / "oauth.sqlite3")
    store.set_token(
        {
            "access_token": "old-access",
            "refresh_token": "old-refresh",
            "expires_in": 3600,
        },
        realm_id="1234567890123456",
        environment="sandbox",
    )
    assert store.status().connected is True

    store.clear()
    assert store.status().connected is False

    url = begin_quickbooks_oauth(store, client_id="public-client-id")
    state = url.split("state=", 1)[1].split("&", 1)[0]
    monkeypatch.setattr(
        oauth,
        "_token_request",
        lambda **kwargs: {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
        },
    )

    status = complete_quickbooks_oauth(
        store,
        credentials={
            "client_id": "public-client-id",
            "client_secret": "private-secret",
        },
        code="fresh-code",
        state=state,
        realm_id="1234567890123456",
    )

    assert status.connected is True
    assert status.environment == "sandbox"
    assert store.get_token()["refresh_token"] == "new-refresh"


def test_disconnect_revokes_refresh_token_then_clears_local_state(tmp_path, monkeypatch):
    store = QuickBooksOAuthStore(tmp_path / "oauth.sqlite3")
    store.set_token(
        {
            "access_token": "sandbox-access",
            "refresh_token": "sandbox-refresh",
            "expires_in": 3600,
        },
        realm_id="1234567890123456",
        environment="sandbox",
    )
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = request.data
        captured["content_type"] = request.headers.get("Content-type")
        captured["authorization"] = request.headers.get("Authorization")
        return _DiscoveryResponse(b'{}')

    monkeypatch.setattr(oauth, "urlopen", fake_urlopen)

    status = disconnect_quickbooks_oauth(
        store,
        credentials={
            "client_id": "public-client-id",
            "client_secret": "private-secret",
        },
    )

    assert captured["url"] == "https://developer.api.intuit.com/v2/oauth2/tokens/revoke"
    assert captured["body"] == b'{"token": "sandbox-refresh"}'
    assert captured["content_type"] == "application/json"
    assert captured["authorization"].startswith("Basic ")
    assert status.connected is False
    assert status.has_refresh_token is False
    assert store.get_token() is None
