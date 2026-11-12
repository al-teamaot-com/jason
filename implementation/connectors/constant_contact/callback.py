"""One-time OAuth callback completion for a locally initiated AOT connection.

HTTP route must call this service with OpenBao-resolved app credentials and
the encrypted store. Only the narrow result is returned to the browser.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from urllib.parse import parse_qs

from .oauth import ConstantContactOAuthError, callback_code
from .oauth_store import EncryptedOAuthStore, OAuthStorageError
from .token_exchange import exchange_code


def complete_authorization(
    *,
    query_string: str,
    store: EncryptedOAuthStore,
    credentials: Mapping[str, str],
    token_transport: Callable | None = None,
) -> dict[str, object]:
    """Consume state before token exchange, preventing replay on a failed exchange."""
    if len(query_string) > 8192:
        raise ConstantContactOAuthError("OAuth callback too large")
    params = parse_qs(query_string, strict_parsing=True, keep_blank_values=True)
    if len(params.get("state", [])) != 1:
        raise ConstantContactOAuthError("OAuth callback requires one state")
    state = params["state"][0]
    # Validate full callback without consuming state on a malformed request.
    code = callback_code(query_string=query_string, expected_state=state)
    store.consume_state(state)
    kwargs = {}
    if token_transport is not None:
        kwargs["transport"] = token_transport
    token = exchange_code(
        code,
        client_id=credentials.get("client_id", ""),
        client_secret=credentials.get("client_secret", ""),
        **kwargs,
    )
    store.save_tokens(token)
    return {"status": "connected", "provider": "constant_contact", "connected": True}
