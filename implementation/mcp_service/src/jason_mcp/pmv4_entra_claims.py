"""Pure Entra JWT signature/issuer/audience/time verification for Jason MCP.

Called with the existing trusted Entra JWKS key resolver. No network client,
audience, issuer, or public key can be supplied by MCP tool arguments.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping
import jwt
from jwt.exceptions import PyJWTError


def verify_signed_entra_claims(
    bearer_token: str,
    *,
    signing_key_lookup: Callable[[str], Any],
    audience: str,
    issuer: str,
) -> Mapping[str, Any] | None:
    if (not isinstance(bearer_token, str) or not bearer_token
            or not callable(signing_key_lookup)
            or not isinstance(audience, str) or not audience
            or not isinstance(issuer, str) or not issuer):
        return None
    try:
        signing_key = signing_key_lookup(bearer_token)
        claims = jwt.decode(
            bearer_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
            leeway=60,
            options={
                "require": ["exp", "iat", "nbf", "aud", "iss", "tid", "oid"],
            },
        )
        return claims if isinstance(claims, dict) else None
    except (PyJWTError, ValueError, TypeError, KeyError, AttributeError):
        return None
    except Exception:
        # Network/JWKS failures never authenticate the user.
        return None
