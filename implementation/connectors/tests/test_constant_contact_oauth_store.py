import os
import sqlite3

import pytest

from connectors.constant_contact.oauth_store import EncryptedOAuthStore, OAuthStorageError


def make_store(tmp_path):
    return EncryptedOAuthStore(tmp_path / "oauth" / "state.sqlite3", b"x" * 32)


def test_encrypted_token_storage_and_private_permissions(tmp_path):
    store = make_store(tmp_path)
    tokens = {"access_token": "sensitive-access", "refresh_token": "sensitive-refresh"}
    store.save_tokens(tokens)
    assert store.load_tokens() == tokens
    assert os.stat(store.path).st_mode & 0o077 == 0
    assert b"sensitive-access" not in store.path.read_bytes()
    store.disconnect_local()
    assert store.load_tokens() is None


def test_oauth_state_is_one_use(tmp_path):
    store = make_store(tmp_path)
    state = store.issue_state()
    store.consume_state(state)
    with pytest.raises(OAuthStorageError, match="already used"):
        store.consume_state(state)


def test_wrong_encryption_key_fails_closed(tmp_path):
    store = make_store(tmp_path)
    store.save_tokens({"access_token": "secret", "refresh_token": "refresh"})
    wrong = EncryptedOAuthStore(store.path, b"y" * 32)
    with pytest.raises(OAuthStorageError, match="decrypt"):
        wrong.load_tokens()


def test_unsafe_file_permissions_rejected(tmp_path):
    store = make_store(tmp_path)
    store.issue_state()
    os.chmod(store.path, 0o644)
    with pytest.raises(OAuthStorageError, match="permissions"):
        store.load_tokens()


def test_invalid_token_payload_and_key_rejected(tmp_path):
    with pytest.raises(OAuthStorageError):
        EncryptedOAuthStore(tmp_path / "a.db", b"weak")
    store = make_store(tmp_path)
    with pytest.raises(OAuthStorageError, match="missing"):
        store.save_tokens({"access_token": "only-one"})
