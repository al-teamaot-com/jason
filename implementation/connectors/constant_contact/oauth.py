"""Constant Contact V3 OAuth request and callback validation primitives.

Source-only engineering component. It does not stage credentials, exchange tokens,
store authorization state, expose HTTP routes, or authorize provider writes.
"""
from __future__ import annotations

import hmac
from urllib.parse import parse_qs, urlencode, urlsplit

AUTHORIZE_URL = "https://authz.constantcontact.com/oauth2/default/v1/authorize"
TOKEN_URL = "https://authz.constantcontact.com/oauth2/default/v1/token"
REDIRECT_URI = "https://mcp-jason.teamaot.com/oauth/constant-contact/callback"
SCOPES = ("contact_data", "offline_access")


class ConstantContactOAuthError(ValueError):
    """Safe authorization error without revealing codes or tokens."""


def authorization_url(*, client_id: str, state: str, redirect_uri: str = REDIRECT_URI) -> str:
    """Build narrowly-scoped authorization URL; caller must persist one-time state."""
    if not client_id or not client_id.strip() or not state or len(state) < 32:
        raise ConstantContactOAuthError("Missing client ID or valid OAuth state")
    if redirect_uri != REDIRECT_URI:
        raise ConstantContactOAuthError("Redirect URI is not registered for Jason")
    return AUTHORIZE_URL + "?" + urlencode({
        "client_id": client_id.strip(),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
    })


def callback_code(*, query_string: str, expected_state: str) -> str:
    """Validate OAuth callback before a separately governed token exchange.

    The caller must consume and invalidate expected_state atomically in durable
    storage before invoking this function; replay protection is not implemented
    by this pure helper. Never log the return value.
    """
    if not expected_state or len(expected_state) < 32:
        raise ConstantContactOAuthError("Missing pending OAuth authorization")
    if len(query_string) > 8192:
        raise ConstantContactOAuthError("OAuth response too large")
    try:
        params = parse_qs(query_string, strict_parsing=True, keep_blank_values=True)
    except ValueError as exc:
        raise ConstantContactOAuthError("Malformed OAuth callback") from exc
    if params.get("error"):
        raise ConstantContactOAuthError("Constant Contact authorization denied")
    if set(params) - {"code", "state", "scope"}:
        raise ConstantContactOAuthError("Unexpected OAuth callback parameters")
    if len(params.get("state", [])) != 1 or len(params.get("code", [])) != 1:
        raise ConstantContactOAuthError("OAuth callback requires one code and state")
    returned_state = params["state"][0]
    if not hmac.compare_digest(returned_state, expected_state):
        raise ConstantContactOAuthError("OAuth state mismatch")
    code = params["code"][0]
    if not code or len(code) > 4096:
        raise ConstantContactOAuthError("Invalid OAuth code")
    return code
