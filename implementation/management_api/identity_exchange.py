from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping, Protocol
from uuid import uuid4


class ManagementIdentityExchangeDenied(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class ExternalIdentity:
    """Verified external identity presented by an approved upstream adapter."""

    issuer: str
    subject: str
    tenant_id: str
    authentication_assurance: str

    def __post_init__(self) -> None:
        for name, value in {
            "issuer": self.issuer,
            "subject": self.subject,
            "tenant_id": self.tenant_id,
            "authentication_assurance": self.authentication_assurance,
        }.items():
            if not value.strip():
                raise ValueError(f"{name} must be non-empty")


@dataclass(frozen=True, slots=True)
class ExternalIdentityBinding:
    """Governed binding from an external identity to Jason identity scope."""

    issuer: str
    subject: str
    tenant_id: str
    principal_id: str
    organization_id: str
    status: str = "active"

    def __post_init__(self) -> None:
        for name, value in {
            "issuer": self.issuer,
            "subject": self.subject,
            "tenant_id": self.tenant_id,
            "principal_id": self.principal_id,
            "organization_id": self.organization_id,
            "status": self.status,
        }.items():
            if not value.strip():
                raise ValueError(f"{name} must be non-empty")


class ExternalIdentityBindingRepository(Protocol):
    def get_binding(
        self,
        *,
        issuer: str,
        subject: str,
        tenant_id: str,
    ) -> ExternalIdentityBinding | None: ...


class ManagementTokenSigner(Protocol):
    def sign(self, claims: Mapping[str, object]) -> str: ...


@dataclass(frozen=True, slots=True)
class ManagementIdentityToken:
    token: str
    principal_id: str
    organization_id: str
    issued_at: datetime
    expires_at: datetime
    authentication_assurance: str


class ManagementIdentityExchange:
    """Exchange a verified external identity for a short-lived Jason token.

    The caller never supplies a Jason principal or organization. Those values are
    obtained only from the governed external-identity binding repository.
    """

    def __init__(
        self,
        *,
        bindings: ExternalIdentityBindingRepository,
        signer: ManagementTokenSigner,
        issuer: str,
        audience: str,
        maximum_ttl_seconds: int = 300,
    ) -> None:
        if not issuer.strip():
            raise ValueError("issuer must be non-empty")
        if not audience.strip():
            raise ValueError("audience must be non-empty")
        if maximum_ttl_seconds < 30 or maximum_ttl_seconds > 900:
            raise ValueError("maximum_ttl_seconds must be between 30 and 900")
        self._bindings = bindings
        self._signer = signer
        self._issuer = issuer
        self._audience = audience
        self._maximum_ttl_seconds = maximum_ttl_seconds

    def exchange(
        self,
        identity: ExternalIdentity,
        *,
        ttl_seconds: int = 300,
        now: datetime | None = None,
    ) -> ManagementIdentityToken:
        if ttl_seconds < 1 or ttl_seconds > self._maximum_ttl_seconds:
            raise ManagementIdentityExchangeDenied("requested token lifetime is not permitted")

        binding = self._bindings.get_binding(
            issuer=identity.issuer,
            subject=identity.subject,
            tenant_id=identity.tenant_id,
        )
        if binding is None:
            raise ManagementIdentityExchangeDenied("external identity is not bound to Jason")
        if binding.status != "active":
            raise ManagementIdentityExchangeDenied("external identity binding is not active")

        issued_at = now or datetime.now(timezone.utc)
        if issued_at.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        expires_at = issued_at + timedelta(seconds=ttl_seconds)

        claims: dict[str, object] = {
            "iss": self._issuer,
            "aud": self._audience,
            "sub": binding.principal_id,
            "organization_id": binding.organization_id,
            "authentication_assurance": identity.authentication_assurance,
            "external_issuer": identity.issuer,
            "external_subject": identity.subject,
            "external_tenant_id": identity.tenant_id,
            "iat": int(issued_at.timestamp()),
            "exp": int(expires_at.timestamp()),
            "jti": str(uuid4()),
        }
        token = self._signer.sign(claims)
        if not token.strip():
            raise RuntimeError("management token signer returned an empty token")

        return ManagementIdentityToken(
            token=token,
            principal_id=binding.principal_id,
            organization_id=binding.organization_id,
            issued_at=issued_at,
            expires_at=expires_at,
            authentication_assurance=identity.authentication_assurance,
        )
