"""Serialized Constant Contact refresh-token lifecycle.

This utility runs only behind an authorized Jason capability. Refresh is
synchronized across local processes to avoid invalidating a rotating token
through concurrent requests. All token state is encrypted at rest.
"""
from __future__ import annotations

import fcntl
import os
import time
from collections.abc import Callable, Mapping
from pathlib import Path

from .oauth_store import EncryptedOAuthStore, OAuthStorageError
from .token_exchange import OAuthTokenError, rotate_refresh_token


def current_access_token(
    store: EncryptedOAuthStore,
    credentials: Mapping[str, str],
    *,
    token_transport: Callable | None = None,
    expiry_margin_seconds: int = 300,
) -> str:
    if not 0 <= expiry_margin_seconds <= 900:
        raise OAuthStorageError("Invalid refresh safety margin")
    # A separate owner-only lock serializes refresh across MCP replicas/processes.
    lock_path = store.path.with_name(store.path.name + ".refresh.lock")
    lock_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if lock_path.is_symlink():
        raise OAuthStorageError("OAuth refresh lock must not be a symlink")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        if os.fstat(fd).st_mode & 0o077:
            raise OAuthStorageError("OAuth refresh lock permissions are unsafe")
        fcntl.flock(fd, fcntl.LOCK_EX)
        token = store.load_tokens()
        if token is None:
            raise OAuthStorageError("Constant Contact account requires authorization")
        if int(token.get("expires_at") or 0) > int(time.time()) + expiry_margin_seconds:
            return str(token["access_token"])
        kwargs = {}
        if token_transport is not None:
            kwargs["transport"] = token_transport
        rotated = rotate_refresh_token(
            str(token["refresh_token"]),
            client_id=credentials.get("client_id", ""),
            client_secret=credentials.get("client_secret", ""),
            **kwargs,
        )
        store.save_tokens(rotated)
        return str(rotated["access_token"])
    finally:
        os.close(fd)
