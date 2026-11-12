import json
import time

import pytest

from connectors.constant_contact.oauth_store import EncryptedOAuthStore, OAuthStorageError
from connectors.constant_contact.session import current_access_token


class Response:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, size):
        return json.dumps({"access_token": "rotated-access", "refresh_token": "rotated-refresh",
                           "expires_in": 3600, "scope": "account_read contact_data offline_access",
                           "token_type": "Bearer"}).encode()


def make_store(tmp_path):
    return EncryptedOAuthStore(tmp_path / "oauth.sqlite3", b"x" * 32)


def test_valid_token_does_not_refresh(tmp_path):
    store = make_store(tmp_path)
    store.save_tokens({"access_token": "valid", "refresh_token": "r", "expires_at": int(time.time()) + 5000})
    assert current_access_token(store, {}, token_transport=lambda req, timeout: pytest.fail("unexpected refresh")) == "valid"


def test_expired_token_rotates_and_persists(tmp_path):
    store = make_store(tmp_path)
    store.save_tokens({"access_token": "old", "refresh_token": "old-refresh", "expires_at": 1})
    calls = []
    def transport(req, timeout):
        calls.append(1)
        return Response()
    assert current_access_token(store, {"client_id": "id", "client_secret": "secret"},
                                token_transport=transport) == "rotated-access"
    assert store.load_tokens()["refresh_token"] == "rotated-refresh"
    assert current_access_token(store, {}, token_transport=transport) == "rotated-access"
    assert calls == [1]


def test_not_connected_fails_closed(tmp_path):
    with pytest.raises(OAuthStorageError, match="requires authorization"):
        current_access_token(make_store(tmp_path), {})
