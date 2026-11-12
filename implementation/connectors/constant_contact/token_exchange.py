"""Constant Contact OAuth token exchange with a fixed trusted issuer.

Callers must validate and consume OAuth state before exchanging a code, resolve
client credentials from the approved secret store and encrypt the returned
rotating refresh token via EncryptedOAuthStore. Never log bearer credentials.
"""
from __future__ import annotations

import base64
import json
import time
from collections.abc import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .oauth import REDIRECT_URI, TOKEN_URL

REQUIRED_SCOPES = frozenset({"account_read", "contact_data", "offline_access"})


class OAuthTokenError(RuntimeError):
    """Redacted OAuth failure."""


def _token_request(
    form: Mapping[str, str],
    *,
    client_id: str,
    client_secret: str,
    transport: Callable = urlopen,
) -> dict:
    if not client_id or not client_secret:
        raise OAuthTokenError("OAuth client credentials missing")
    basic = base64.b64encode((client_id + ":" + client_secret).encode()).decode()
    req = Request(TOKEN_URL, data=urlencode(dict(form)).encode(), method="POST", headers={
        "Authorization": "Basic " + basic,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    })
    try:
        with transport(req, timeout=15) as response:
            raw = response.read(16385)
        if len(raw) > 16384:
            raise OAuthTokenError("OAuth response too large")
        result = json.loads(raw)
        if not isinstance(result, dict) or result.get("token_type", "").casefold() != "bearer":
            raise OAuthTokenError("Invalid OAuth response")
        if not isinstance(result.get("access_token"), str) or not isinstance(result.get("refresh_token"), str):
            raise OAuthTokenError("OAuth response missing tokens")
        if not result["access_token"] or not result["refresh_token"]:
            raise OAuthTokenError("OAuth response missing tokens")
        scopes = set(str(result.get("scope") or "").split())
        if not REQUIRED_SCOPES <= scopes:
            raise OAuthTokenError("OAuth authorization missing account, contact or refresh scope")
        expires_in = int(result.get("expires_in") or 0)
        if not 1 <= expires_in <= 86400 * 2:
            raise OAuthTokenError("Invalid OAuth token lifetime")
        return {
            "access_token": result["access_token"],
            "refresh_token": result["refresh_token"],
            "scope": " ".join(sorted(scopes)),
            "expires_at": int(time.time()) + expires_in,
            "token_type": "Bearer",
        }
    except OAuthTokenError:
        raise
    except (HTTPError, URLError, TimeoutError, ValueError, TypeError, OSError, KeyError, AttributeError):
        raise OAuthTokenError("OAuth token exchange failed") from None


def exchange_code(
    code: str,
    *,
    client_id: str,
    client_secret: str,
    transport: Callable = urlopen,
) -> dict:
    if not code or len(code) > 4096:
        raise OAuthTokenError("Invalid OAuth authorization code")
    return _token_request({
        "code": code, "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }, client_id=client_id, client_secret=client_secret, transport=transport)


def rotate_refresh_token(
    refresh_token: str,
    *,
    client_id: str,
    client_secret: str,
    transport: Callable = urlopen,
) -> dict:
    if not refresh_token:
        raise OAuthTokenError("OAuth refresh token missing")
    return _token_request({
        "refresh_token": refresh_token, "grant_type": "refresh_token",
    }, client_id=client_id, client_secret=client_secret, transport=transport)
