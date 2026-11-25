"""Encrypted, single-account Constant Contact OAuth state.

Client credentials and encryption key are supplied by the approved secret
resolver, not persisted here. No secret values should enter logs.
"""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import stat
import time
from pathlib import Path
from typing import Mapping

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

AAD = b"project-jason:constant-contact:oauth:v1"


class OAuthStorageError(RuntimeError):
    """Safe error; do not log original sqlite/crypto exceptions or secrets."""


class EncryptedOAuthStore:
    def __init__(self, path: Path, encryption_key: bytes):
        if len(encryption_key) != 32:
            raise OAuthStorageError("AES-256 token encryption key is required")
        self.path = Path(path)
        self._key = bytes(encryption_key)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise OAuthStorageError("OAuth state cannot be a symlink")
        if self.path.exists():
            mode = stat.S_IMODE(self.path.stat().st_mode)
            if not self.path.is_file() or mode & 0o077:
                raise OAuthStorageError("OAuth state permissions are unsafe")
        con = sqlite3.connect(str(self.path), isolation_level=None, timeout=10)
        os.chmod(self.path, 0o600)
        con.execute("CREATE TABLE IF NOT EXISTS pending (state_hash TEXT PRIMARY KEY, expires INTEGER NOT NULL)")
        con.execute("CREATE TABLE IF NOT EXISTS tokens (id INTEGER PRIMARY KEY CHECK (id = 1), ciphertext BLOB NOT NULL)")
        return con

    @staticmethod
    def _hash_state(state: str) -> str:
        import hashlib
        if len(state) < 32:
            raise OAuthStorageError("Invalid OAuth state")
        return hashlib.sha256(state.encode("utf-8")).hexdigest()

    def issue_state(self, lifetime: int = 600) -> str:
        if lifetime < 60 or lifetime > 900:
            raise OAuthStorageError("Invalid pending authorization lifetime")
        state = secrets.token_urlsafe(48)
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute("DELETE FROM pending WHERE expires < ?", (int(time.time()),))
            con.execute(
                "INSERT INTO pending(state_hash, expires) VALUES (?, ?)",
                (self._hash_state(state), int(time.time()) + lifetime),
            )
            con.execute("COMMIT")
        return state

    def consume_state(self, state: str) -> None:
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT expires FROM pending WHERE state_hash = ?", (self._hash_state(state),)).fetchone()
            con.execute("DELETE FROM pending WHERE state_hash = ?", (self._hash_state(state),))
            con.execute("COMMIT")
        if row is None or row[0] < int(time.time()):
            raise OAuthStorageError("OAuth state missing, expired, or already used")

    def save_tokens(self, token_payload: Mapping[str, object]) -> None:
        access = token_payload.get("access_token")
        refresh = token_payload.get("refresh_token")
        if not isinstance(access, str) or not access or not isinstance(refresh, str) or not refresh:
            raise OAuthStorageError("OAuth token response missing required credentials")
        nonce = os.urandom(12)
        try:
            plaintext = json.dumps(dict(token_payload), separators=(",", ":")).encode()
            ciphertext = nonce + AESGCM(self._key).encrypt(nonce, plaintext, AAD)
        except (TypeError, ValueError) as exc:
            raise OAuthStorageError("Malformed OAuth token response") from None
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute("INSERT INTO tokens(id, ciphertext) VALUES (1, ?) "
                        "ON CONFLICT(id) DO UPDATE SET ciphertext=excluded.ciphertext", (ciphertext,))
            con.execute("COMMIT")

    def load_tokens(self) -> dict[str, object] | None:
        with self._connect() as con:
            row = con.execute("SELECT ciphertext FROM tokens WHERE id = 1").fetchone()
        if row is None:
            return None
        try:
            blob = bytes(row[0])
            result = json.loads(AESGCM(self._key).decrypt(blob[:12], blob[12:], AAD))
            if not isinstance(result, dict) or not result.get("access_token") or not result.get("refresh_token"):
                raise ValueError("Malformed token")
            return result
        except Exception:
            raise OAuthStorageError("Unable to decrypt OAuth state") from None

    def disconnect_local(self) -> None:
        """Local erasure only; provider revocation is a separate governed action."""
        with self._connect() as con:
            con.execute("DELETE FROM tokens")
            con.execute("DELETE FROM pending")
