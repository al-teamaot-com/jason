from urllib.parse import urlencode

import pytest

from connectors.constant_contact.callback import complete_authorization
from connectors.constant_contact.oauth import ConstantContactOAuthError
from connectors.constant_contact.oauth_store import EncryptedOAuthStore, OAuthStorageError
from connectors.constant_contact.token_exchange import OAuthTokenError


class FakeResponse:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, n):
        return (b'{"token_type":"Bearer","access_token":"a","refresh_token":"r",'
                b'"scope":"contact_data offline_access","expires_in":3600}')


def test_callback_consumes_state_and_saves_encrypted_tokens(tmp_path):
    store = EncryptedOAuthStore(tmp_path / "oauth.sqlite3", b"a" * 32)
    state = store.issue_state()
    query = urlencode({"code": "private-code", "state": state})
    result = complete_authorization(query_string=query, store=store, credentials={
        "client_id": "id", "client_secret": "secret"}, token_transport=lambda req, timeout: FakeResponse())
    assert result["connected"]
    assert store.load_tokens()["refresh_token"] == "r"
    with pytest.raises(OAuthStorageError, match="already used"):
        complete_authorization(query_string=query, store=store, credentials={
            "client_id": "id", "client_secret": "secret"}, token_transport=lambda req, timeout: FakeResponse())


def test_bad_state_never_exchanges_token(tmp_path):
    store = EncryptedOAuthStore(tmp_path / "oauth.sqlite3", b"a" * 32)
    called = []
    with pytest.raises(OAuthStorageError):
        complete_authorization(query_string=urlencode({"code": "private", "state": "x" * 40}),
            store=store, credentials={"client_id": "id", "client_secret": "secret"},
            token_transport=lambda req, timeout: called.append(True))
    assert called == []


def test_malformed_callback_never_consumes_valid_state(tmp_path):
    store = EncryptedOAuthStore(tmp_path / "oauth.sqlite3", b"a" * 32)
    state = store.issue_state()
    with pytest.raises(ConstantContactOAuthError):
        complete_authorization(query_string=urlencode({"code": ["a", "b"], "state": state}, doseq=True),
            store=store, credentials={"client_id": "id", "client_secret": "secret"},
            token_transport=lambda req, timeout: FakeResponse())
    store.consume_state(state)
