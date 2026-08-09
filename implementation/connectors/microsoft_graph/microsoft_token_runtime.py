"""Production composition for Microsoft approval-ingress token verification.

This module assembles the already-governed Microsoft OpenID/JWKS transport,
cryptographic verifier, and claim-policy verifier. It creates no Jason identity or
approval authority; successful verification only yields a Microsoft principal that
must still pass tenant and identity bindings before provider-neutral approval logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from .microsoft_jwks_verifier import MicrosoftJwksPolicy, MicrosoftJwksVerifier
from .microsoft_openid_http import MicrosoftOpenIdJsonFetcher
from .microsoft_token_verification import MicrosoftTokenPolicy, MicrosoftTokenVerifier


@dataclass(frozen=True, slots=True)
class MicrosoftTokenVerifierRuntimeConfig:
    tenant_id: str
    audience: str
    clock_skew_seconds: int = 120
    jwks_cache_ttl_seconds: int = 3600
    http_timeout_seconds: float = 10.0
    max_response_bytes: int = 1_048_576

    def validate(self) -> None:
        if not self.tenant_id.strip():
            raise ValueError("Microsoft token runtime tenant_id must be non-empty")
        if not self.audience.strip():
            raise ValueError("Microsoft token runtime audience must be non-empty")
        MicrosoftTokenPolicy(
            audience=self.audience,
            allowed_tenant_ids=(self.tenant_id,),
            clock_skew_seconds=self.clock_skew_seconds,
        ).validate()
        MicrosoftJwksPolicy(
            tenant_id=self.tenant_id,
            cache_ttl_seconds=self.jwks_cache_ttl_seconds,
        ).validate()
        MicrosoftOpenIdJsonFetcher(
            timeout_seconds=self.http_timeout_seconds,
            max_response_bytes=self.max_response_bytes,
        )


def build_microsoft_token_verifier(
    *,
    config: MicrosoftTokenVerifierRuntimeConfig,
) -> MicrosoftTokenVerifier:
    """Build the production verifier without granting downstream Jason authority."""

    config.validate()
    fetcher = MicrosoftOpenIdJsonFetcher(
        timeout_seconds=config.http_timeout_seconds,
        max_response_bytes=config.max_response_bytes,
    )
    crypto = MicrosoftJwksVerifier(
        fetcher=fetcher,
        policy=MicrosoftJwksPolicy(
            tenant_id=config.tenant_id,
            cache_ttl_seconds=config.jwks_cache_ttl_seconds,
        ),
    )
    return MicrosoftTokenVerifier(
        crypto=crypto,
        policy=MicrosoftTokenPolicy(
            audience=config.audience,
            allowed_tenant_ids=(config.tenant_id,),
            clock_skew_seconds=config.clock_skew_seconds,
        ),
    )
