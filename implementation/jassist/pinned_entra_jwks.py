"""Pinned, Entra-tenant-specific RS256 key resolution for JAssist.Send.

The JWT header may only select a key ID from a fixed AOT tenant JWKS
endpoint; untrusted jku/x5u URLs or algorithms are never followed.
No credentials, browser tokens or secrets are stored in this module.
"""
from __future__ import annotations

import re
import jwt
from jwt import PyJWKClient

from .entra_send_authority import AOT_ENTRA_TENANT_ID

_JWKS_URL = (
    "https://login.microsoftonline.com/" + AOT_ENTRA_TENANT_ID
    + "/discovery/v2.0/keys"
)
_KID = re.compile(r"^[A-Za-z0-9._=+/-]{1,160}$")


class PinnedAotEntraJwks:
    def __init__(self, *, client=None):
        self._client = client if client is not None else PyJWKClient(
            _JWKS_URL, cache_keys=True, lifespan=300, timeout=5
        )
        if not callable(getattr(self._client, "get_signing_key_from_jwt", None)):
            raise ValueError("verified tenant-specific JWKS client required")

    @property
    def url(self):
        return _JWKS_URL

    def __call__(self, access_token: str):
        if not isinstance(access_token, str) or not 100 <= len(access_token) <= 8192:
            raise ValueError("signed Entra token required")
        try:
            unverified = jwt.get_unverified_header(access_token)
            if not isinstance(unverified, dict):
                raise ValueError("malformed JWT header")
            if unverified.get("alg") != "RS256":
                raise ValueError("unapproved JWT signature algorithm")
            kid = unverified.get("kid")
            if not isinstance(kid, str) or not _KID.fullmatch(kid):
                raise ValueError("invalid Entra signing key selector")
            if any(key in unverified for key in ("jku", "x5u", "jwk", "crit")):
                raise ValueError("untrusted JWT key material")
            result = self._client.get_signing_key_from_jwt(access_token)
            key = getattr(result, "key", None)
            if key is None:
                raise ValueError("Entra JWKS key unavailable")
            return key
        except Exception as exc:
            raise ValueError("AOT Entra signing key verification unavailable") from exc
