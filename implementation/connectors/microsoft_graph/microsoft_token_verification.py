"""Governed Microsoft token verification boundary for approval ingress.

The concrete JWT crypto implementation is injected behind ``JwtCryptoVerifier``
so Jason is not coupled to one library. The verifier implementation MUST validate
the JWT signature against trusted Microsoft signing keys before returning claims.
This module then independently enforces Microsoft issuer, audience, tenant, token
lifetime, and required identity claims before constructing a trusted principal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol

from .teams_approval_ingress import VerifiedMicrosoftPrincipal


class MicrosoftTokenVerificationError(PermissionError):
    """Raised when a Microsoft authentication token fails closed."""


class JwtCryptoVerifier(Protocol):
    def verify_signature(self, token: str) -> Mapping[str, Any]:
        """Return claims only after cryptographic JWT signature verification.

        Implementations must select keys from an orchestrator-approved Microsoft
        OpenID/JWKS source and reject unknown algorithms, keys, or invalid signatures.
        """
        ...


@dataclass(frozen=True, slots=True)
class MicrosoftTokenPolicy:
    audience: str
    allowed_tenant_ids: tuple[str, ...]
    issuer_host: str = "https://login.microsoftonline.com"
    clock_skew_seconds: int = 120

    def validate(self) -> None:
        if not self.audience.strip():
            raise ValueError("audience must be non-empty")
        if not self.allowed_tenant_ids or any(not tenant.strip() for tenant in self.allowed_tenant_ids):
            raise ValueError("at least one allowed Microsoft tenant is required")
        if len(set(self.allowed_tenant_ids)) != len(self.allowed_tenant_ids):
            raise ValueError("allowed Microsoft tenants must be unique")
        if self.issuer_host.rstrip("/") != "https://login.microsoftonline.com":
            raise ValueError("only the canonical Microsoft issuer host is approved")
        if self.clock_skew_seconds < 0 or self.clock_skew_seconds > 300:
            raise ValueError("clock skew must be between 0 and 300 seconds")


@dataclass(frozen=True, slots=True)
class MicrosoftTokenVerifier:
    crypto: JwtCryptoVerifier
    policy: MicrosoftTokenPolicy
    clock: callable = lambda: datetime.now(timezone.utc)

    def verify(self, token: str) -> VerifiedMicrosoftPrincipal:
        self.policy.validate()
        if not isinstance(token, str) or not token.strip():
            raise MicrosoftTokenVerificationError("Microsoft token is required")

        try:
            claims = self.crypto.verify_signature(token)
        except Exception as exc:
            raise MicrosoftTokenVerificationError("Microsoft token signature verification failed") from exc

        tenant_id = self._required_string(claims, "tid")
        object_id = self._required_string(claims, "oid")
        subject = self._required_string(claims, "sub")
        issuer = self._required_string(claims, "iss")
        audience = self._required_audience(claims)
        issued_at = self._required_epoch(claims, "iat")
        not_before = self._required_epoch(claims, "nbf")
        expires_at = self._required_epoch(claims, "exp")

        if tenant_id not in self.policy.allowed_tenant_ids:
            raise MicrosoftTokenVerificationError("Microsoft tenant is not approved")

        expected_issuers = {
            f"https://login.microsoftonline.com/{tenant_id}/v2.0",
            f"https://sts.windows.net/{tenant_id}/",
        }
        if issuer not in expected_issuers:
            raise MicrosoftTokenVerificationError("Microsoft token issuer does not match tenant")
        if audience != self.policy.audience:
            raise MicrosoftTokenVerificationError("Microsoft token audience mismatch")

        now = self._now_epoch()
        skew = self.policy.clock_skew_seconds
        if issued_at > now + skew:
            raise MicrosoftTokenVerificationError("Microsoft token issued-at time is in the future")
        if not_before > now + skew:
            raise MicrosoftTokenVerificationError("Microsoft token is not yet valid")
        if expires_at <= now - skew:
            raise MicrosoftTokenVerificationError("Microsoft token is expired")
        if expires_at <= not_before:
            raise MicrosoftTokenVerificationError("Microsoft token lifetime is invalid")

        assurance = self._authentication_assurance(claims)
        principal = VerifiedMicrosoftPrincipal(
            tenant_id=tenant_id,
            object_id=object_id,
            subject=subject,
            audience=audience,
            issuer=issuer,
            authentication_assurance=assurance,
        )
        principal.validate()
        return principal

    @staticmethod
    def _required_string(claims: Mapping[str, Any], name: str) -> str:
        value = claims.get(name)
        if not isinstance(value, str) or not value.strip():
            raise MicrosoftTokenVerificationError(f"Microsoft token missing required {name} claim")
        return value.strip()

    @staticmethod
    def _required_audience(claims: Mapping[str, Any]) -> str:
        value = claims.get("aud")
        if isinstance(value, str) and value.strip():
            return value.strip()
        raise MicrosoftTokenVerificationError("Microsoft token audience must be a single value")

    @staticmethod
    def _required_epoch(claims: Mapping[str, Any], name: str) -> int:
        value = claims.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MicrosoftTokenVerificationError(f"Microsoft token missing valid {name} claim")
        return int(value)

    @staticmethod
    def _authentication_assurance(claims: Mapping[str, Any]) -> str:
        amr = claims.get("amr")
        if isinstance(amr, (list, tuple)):
            methods = {str(item).strip().lower() for item in amr if str(item).strip()}
            if "mfa" in methods:
                return "mfa"
            if methods:
                return "authenticated:" + ",".join(sorted(methods))
        acr = claims.get("acr")
        if isinstance(acr, str) and acr.strip():
            return f"acr:{acr.strip()}"
        raise MicrosoftTokenVerificationError("Microsoft token lacks authentication assurance")

    def _now_epoch(self) -> int:
        now = self.clock()
        if now.tzinfo is None:
            raise ValueError("Microsoft token verifier clock must be timezone-aware")
        return int(now.astimezone(timezone.utc).timestamp())
