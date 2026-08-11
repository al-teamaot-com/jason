from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

import jwt

from management_api.service import ManagementReadContext


class ManagementAuthenticationFailed(PermissionError):
    pass


class ManagementContextResolver(Protocol):
    def resolve(self, environ: Mapping[str, object]) -> ManagementReadContext: ...


@dataclass(frozen=True, slots=True)
class JwtManagementContextResolver:
    """Resolve Jason management identity only from a verified bearer token.

    The token is expected to be minted by an approved upstream identity boundary.
    Browser-supplied principal/organization headers are deliberately ignored.
    """

    public_key: str
    issuer: str
    audience: str
    organization_claim: str = "organization_id"
    principal_claim: str = "sub"
    algorithms: tuple[str, ...] = ("RS256",)

    def __post_init__(self) -> None:
        if not self.public_key.strip():
            raise ValueError("public_key must be non-empty")
        if not self.issuer.strip():
            raise ValueError("issuer must be non-empty")
        if not self.audience.strip():
            raise ValueError("audience must be non-empty")
        if not self.algorithms:
            raise ValueError("algorithms must not be empty")
        if any(algorithm.startswith("HS") for algorithm in self.algorithms):
            raise ValueError("shared-secret JWT algorithms are not permitted")

    def resolve(self, environ: Mapping[str, object]) -> ManagementReadContext:
        authorization = str(environ.get("HTTP_AUTHORIZATION", ""))
        scheme, separator, token = authorization.partition(" ")
        if separator != " " or scheme.lower() != "bearer" or not token.strip():
            raise ManagementAuthenticationFailed("bearer token required")

        try:
            claims = jwt.decode(
                token.strip(),
                self.public_key,
                algorithms=list(self.algorithms),
                issuer=self.issuer,
                audience=self.audience,
                options={
                    "require": [
                        "exp",
                        "iat",
                        self.principal_claim,
                        self.organization_claim,
                    ]
                },
            )
        except jwt.PyJWTError as exc:
            raise ManagementAuthenticationFailed("invalid management identity token") from exc

        principal = claims.get(self.principal_claim)
        organization = claims.get(self.organization_claim)
        if not isinstance(principal, str) or not principal.strip():
            raise ManagementAuthenticationFailed("principal claim is invalid")
        if not isinstance(organization, str) or not organization.strip():
            raise ManagementAuthenticationFailed("organization claim is invalid")

        return ManagementReadContext(
            principal_id=principal,
            organization_id=organization,
        )
