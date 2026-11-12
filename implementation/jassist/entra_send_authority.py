"""Preproduction-only Entra JWT verifier for the narrow JAssist.Send API scope.

AOT's existing Jason.Read MCP verifier must remain unchanged. This adapter
is exclusively for a future scoped browser screenshot intake endpoint.
No endpoint, token persistence, app registration or Datto access is enabled.
"""
from __future__ import annotations

from typing import Callable
import re
import jwt
from jwt.exceptions import PyJWTError

from .session_gate import Denied, VerifiedTechnician

AOT_ENTRA_TENANT_ID = "f7054323-d52b-4863-8c2f-1898f0b6077c"
JASON_RESOURCE_CLIENT_ID = "9b9996e9-5c34-48b7-948c-f44f89352f89"
ENTRA_ISSUER = (
    "https://login.microsoftonline.com/"
    + AOT_ENTRA_TENANT_ID
    + "/v2.0"
)
DELEGATED_SEND_SCOPE = "JAssist.Send"


class EntraSendAuthority:
    """RS256, audience, tenant, client, scope and ACTIVE identity binding.

    signing_key_for is a trusted server-owned Entra JWKS resolver.
    resolve_active_aot_identity is the server-owned verified Microsoft
    identity -> active Jason identity binding. Neither may be browser/model
    supplied. Datto native authorization is a separate mandatory gate.
    """

    def __init__(
        self,
        *,
        allowed_spa_client_id: str,
        signing_key_for: Callable[[str], object],
        resolve_active_aot_identity: Callable[[str, str], VerifiedTechnician | None],
        resolve_verified_entra_oid: Callable[[VerifiedTechnician], str | None] | None = None,
    ) -> None:
        if (
            not isinstance(allowed_spa_client_id, str)
            or not allowed_spa_client_id.strip()
            or re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", allowed_spa_client_id, re.I) is None
            or not callable(signing_key_for)
            or not callable(resolve_active_aot_identity)
            or (resolve_verified_entra_oid is not None
                and not callable(resolve_verified_entra_oid))
        ):
            raise ValueError("verified pilot SPA app registration required")
        self._client_id = allowed_spa_client_id.casefold()
        self._key_for = signing_key_for
        self._identity = resolve_active_aot_identity
        self._reverse_oid = resolve_verified_entra_oid

    def authenticate(self, bearer: str) -> VerifiedTechnician:
        if not isinstance(bearer, str) or not 100 <= len(bearer) <= 8192:
            raise Denied("signed Entra access token required")
        try:
            public_key = self._key_for(bearer)
            if public_key is None:
                raise Denied("Entra key unavailable")
            claims = jwt.decode(
                bearer,
                public_key,
                algorithms=["RS256"],
                audience=JASON_RESOURCE_CLIENT_ID,
                issuer=ENTRA_ISSUER,
                leeway=30,
                options={
                    "require": [
                        "iss", "aud", "exp", "iat", "nbf",
                        "tid", "oid", "scp", "azp",
                    ]
                },
            )
            tenant = claims["tid"]
            oid = claims["oid"]
            client = claims["azp"]
            scopes = claims["scp"]
            if (
                tenant != AOT_ENTRA_TENANT_ID
                or not isinstance(oid, str)
                or re.fullmatch(
                    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                    oid,re.I) is None
                or not isinstance(client, str)
                or client.casefold() != self._client_id
                or not isinstance(scopes, str)
                or set(scopes.split()) != {DELEGATED_SEND_SCOPE}
            ):
                raise Denied("J-Assist scope or client mismatch")
            person = self._identity(tenant, oid)
            if (
                not isinstance(person, VerifiedTechnician)
                or not person.subject.strip()
                or person.tenant_id != "aot"
            ):
                raise Denied("active AOT technician binding unavailable")
            # The identity reported to ChatGPT MCP must be the same
            # authenticated Entra oid, not just a different group member.
            if self._reverse_oid is not None:
                canonical_oid = self._reverse_oid(person)
                if (not isinstance(canonical_oid,str)
                        or canonical_oid.casefold()!=oid.casefold()):
                    raise Denied("J-Assist individual Entra identity binding mismatch")
            return person
        except Denied:
            raise
        except (PyJWTError, ValueError, TypeError, KeyError) as exc:
            raise Denied("invalid or expired J-Assist Entra access token") from exc
        except Exception as exc:
            # Fail closed when JWKS or authoritative identity systems are down.
            raise Denied("J-Assist authentication dependencies unavailable") from exc
