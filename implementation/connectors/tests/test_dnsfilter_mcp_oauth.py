from __future__ import annotations

import os
import time

from connectors.dnsfilter import mcp_oauth
from connectors.dnsfilter.mcp_oauth import (
    DnsFilterMcpOAuthStore,
    access_token,
)


def test_store_construction_is_side_effect_free_until_used(tmp_path):
    path = tmp_path / "dnsfilter-oauth.sqlite3"
    DnsFilterMcpOAuthStore(path)
    assert not path.exists()


def test_oauth_store_is_private_and_status_never_exposes_token(tmp_path):
    store = DnsFilterMcpOAuthStore(tmp_path / "dnsfilter-oauth.sqlite3")
    store.set_registration(
        {
            "client_id": "client-1",
            "redirect_uris": ["https://example.test/callback"],
            "token_endpoint_auth_method": "none",
        }
    )
    store.set_token(
        {
            "access_token": "top-secret-token",
            "refresh_token": "top-secret-refresh",
            "expires_in": 3600,
        }
    )
    mode = os.stat(store.path).st_mode & 0o777
    assert mode == 0o600
    status = store.status()
    assert status.registered is True
    assert status.connected is True
    assert status.has_refresh_token is True
    assert "top-secret" not in repr(status)


def test_access_token_refreshes_and_preserves_rotating_refresh_token(tmp_path, monkeypatch):
    store = DnsFilterMcpOAuthStore(tmp_path / "dnsfilter-oauth.sqlite3")
    store.set_registration(
        {
            "client_id": "client-1",
            "redirect_uris": ["https://example.test/callback"],
            "token_endpoint_auth_method": "none",
        }
    )
    store.set_token(
        {
            "access_token": "expired-token",
            "refresh_token": "refresh-1",
            "expires_in": 1,
        }
    )

    monkeypatch.setattr(
        mcp_oauth,
        "discover_dnsfilter_oauth",
        lambda: {"token_endpoint": "https://mcp.dnsfilter.com/token"},
    )
    monkeypatch.setattr(
        mcp_oauth,
        "_token_request",
        lambda endpoint, registration, form: {
            "access_token": "fresh-token",
            "expires_in": 3600,
        },
    )
    time.sleep(1.05)
    assert access_token(store) == "fresh-token"
    persisted = store.get_token()
    assert persisted["refresh_token"] == "refresh-1"


def test_pending_authorization_is_single_use(tmp_path):
    store = DnsFilterMcpOAuthStore(tmp_path / "dnsfilter-oauth.sqlite3")
    store.create_pending(
        state="state-1",
        code_verifier="verifier",
        redirect_uri="https://example.test/callback",
    )
    pending = store.consume_pending("state-1")
    assert pending["code_verifier"] == "verifier"
    assert store.status().pending_authorization is False
