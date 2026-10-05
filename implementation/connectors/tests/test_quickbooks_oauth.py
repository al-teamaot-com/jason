from __future__ import annotations

import time

import pytest

from connectors.quickbooks import oauth
from connectors.quickbooks.oauth import (
    QUICKBOOKS_SCOPE,
    QuickBooksOAuthError,
    QuickBooksOAuthStore,
    begin_quickbooks_oauth,
    complete_quickbooks_oauth,
    quickbooks_access_context,
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
        realm_id="9341458418110656",
    )

    assert status.connected is True
    assert status.environment == "sandbox"
    assert status.realm_id == "9341458418110656"
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
            realm_id="9341458418110656",
        )


def test_access_context_refreshes_and_persists_newest_refresh_token(tmp_path, monkeypatch):
    store = QuickBooksOAuthStore(tmp_path / "oauth.sqlite3")
    store.set_token(
        {
            "access_token": "old-access",
            "refresh_token": "old-refresh",
            "expires_in": 1,
        },
        realm_id="9341458418110656",
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
    assert realm == "9341458418110656"
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
