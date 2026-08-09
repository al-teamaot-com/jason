"""Production Microsoft JWKS-backed JWT signature verification.

Network retrieval is isolated behind ``JsonDocumentFetcher`` for deterministic
validation and future governed transport replacement. Only canonical Microsoft
login endpoints are accepted. Cached signing keys have a bounded lifetime and an
unknown ``kid`` triggers one controlled refresh to support Microsoft key rotation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol
from urllib.parse import urlparse

import jwt


class MicrosoftJwksVerificationError(PermissionError):
    pass


class JsonDocumentFetcher(Protocol):
    def get_json(self, url: str) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class MicrosoftJwksPolicy:
    tenant_id: str
    cache_ttl_seconds: int = 3600
    allowed_algorithms: tuple[str, ...] = ("RS256",)

    def validate(self) -> None:
        if not self.tenant_id.strip():
            raise ValueError("tenant_id must be non-empty")
        if self.cache_ttl_seconds < 60 or self.cache_ttl_seconds > 86400:
            raise ValueError("JWKS cache TTL must be between 60 and 86400 seconds")
        if self.allowed_algorithms != ("RS256",):
            raise ValueError("Microsoft approval ingress currently permits RS256 only")


@dataclass
class MicrosoftJwksVerifier:
    fetcher: JsonDocumentFetcher
    policy: MicrosoftJwksPolicy
    clock: callable = lambda: datetime.now(timezone.utc)
    _jwks_uri: str | None = field(default=None, init=False)
    _keys: dict[str, Mapping[str, Any]] = field(default_factory=dict, init=False)
    _cache_expires_at: int = field(default=0, init=False)

    def verify_signature(self, token: str) -> Mapping[str, Any]:
        self.policy.validate()
        if not token.strip():
            raise MicrosoftJwksVerificationError("JWT is required")
        try:
            header = jwt.get_unverified_header(token)
        except Exception as exc:
            raise MicrosoftJwksVerificationError("JWT header is malformed") from exc

        algorithm = header.get("alg")
        key_id = header.get("kid")
        if algorithm not in self.policy.allowed_algorithms:
            raise MicrosoftJwksVerificationError("JWT algorithm is not approved")
        if not isinstance(key_id, str) or not key_id.strip():
            raise MicrosoftJwksVerificationError("JWT signing key id is required")

        self._ensure_keys()
        key = self._keys.get(key_id)
        if key is None:
            self._refresh_keys()
            key = self._keys.get(key_id)
        if key is None:
            raise MicrosoftJwksVerificationError("JWT signing key is unknown after controlled refresh")

        try:
            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(dict(key))
            return jwt.decode(
                token,
                key=public_key,
                algorithms=list(self.policy.allowed_algorithms),
                options={
                    "verify_signature": True,
                    "verify_aud": False,
                    "verify_iss": False,
                    "verify_exp": False,
                    "verify_nbf": False,
                    "verify_iat": False,
                    "require": [],
                },
            )
        except Exception as exc:
            raise MicrosoftJwksVerificationError("JWT cryptographic signature verification failed") from exc

    def _ensure_keys(self) -> None:
        if not self._keys or self._now_epoch() >= self._cache_expires_at:
            self._refresh_keys()

    def _refresh_keys(self) -> None:
        discovery_url = (
            "https://login.microsoftonline.com/"
            f"{self.policy.tenant_id}/v2.0/.well-known/openid-configuration"
        )
        discovery = self.fetcher.get_json(discovery_url)
        jwks_uri = discovery.get("jwks_uri")
        if not isinstance(jwks_uri, str):
            raise MicrosoftJwksVerificationError("Microsoft discovery document lacks jwks_uri")
        self._validate_microsoft_url(jwks_uri)

        document = self.fetcher.get_json(jwks_uri)
        keys = document.get("keys")
        if not isinstance(keys, list) or not keys:
            raise MicrosoftJwksVerificationError("Microsoft JWKS document contains no keys")

        accepted: dict[str, Mapping[str, Any]] = {}
        for key in keys:
            if not isinstance(key, Mapping):
                continue
            kid = key.get("kid")
            if not isinstance(kid, str) or not kid.strip():
                continue
            if key.get("kty") != "RSA":
                continue
            use = key.get("use")
            if use not in (None, "sig"):
                continue
            key_alg = key.get("alg")
            if key_alg not in (None, *self.policy.allowed_algorithms):
                continue
            accepted[kid] = key
        if not accepted:
            raise MicrosoftJwksVerificationError("Microsoft JWKS contains no approved signing keys")

        self._jwks_uri = jwks_uri
        self._keys = accepted
        self._cache_expires_at = self._now_epoch() + self.policy.cache_ttl_seconds

    @staticmethod
    def _validate_microsoft_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "login.microsoftonline.com":
            raise MicrosoftJwksVerificationError("JWKS URL is not an approved Microsoft endpoint")
        if parsed.username is not None or parsed.password is not None or parsed.port not in (None, 443):
            raise MicrosoftJwksVerificationError("JWKS URL contains unapproved authority components")

    def _now_epoch(self) -> int:
        now = self.clock()
        if now.tzinfo is None:
            raise ValueError("JWKS verifier clock must be timezone-aware")
        return int(now.astimezone(timezone.utc).timestamp())
