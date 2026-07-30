from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Mapping, Protocol


class SecretProviderStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class SecretRequest:
    secret_name: str
    purpose: str
    execution_context_id: str
    requester_id: str
    capability: str
    correlation_id: str
    client_id: str | None = None
    minimum_version: str | None = None


@dataclass(frozen=True, slots=True)
class SecretLease:
    secret_name: str
    values: Mapping[str, str]
    version: str
    issued_at: datetime
    expires_at: datetime | None
    renewable: bool = False
    lease_id: str | None = None
    sensitivity: str = "secret"

    def __repr__(self) -> str:
        return (
            "SecretLease("
            f"secret_name={self.secret_name!r}, version={self.version!r}, "
            f"issued_at={self.issued_at!r}, expires_at={self.expires_at!r}, "
            f"renewable={self.renewable!r}, lease_id={'<redacted>' if self.lease_id else None}, "
            f"values=<redacted>, sensitivity={self.sensitivity!r})"
        )


@dataclass(frozen=True, slots=True)
class SecretMetadata:
    secret_name: str
    version: str
    updated_at: datetime | None
    field_names: tuple[str, ...]


class SecretsProvider(Protocol):
    def health(self) -> SecretProviderStatus: ...

    def resolve(self, request: SecretRequest) -> SecretLease: ...

    def renew(self, lease: SecretLease) -> SecretLease:
        raise NotImplementedError

    def revoke(self, lease: SecretLease) -> None:
        raise NotImplementedError

    def metadata(self, secret_name: str) -> SecretMetadata: ...


class SecretResolutionError(RuntimeError):
    """Raised when a secret cannot be resolved safely.

    Error messages must never contain secret values or provider credentials.
    """


class InMemorySecretsProvider:
    """Synthetic provider for contract tests only."""

    def __init__(self, secrets: Mapping[str, Mapping[str, str]], *, version: str = "test-1") -> None:
        self._secrets = {name: dict(values) for name, values in secrets.items()}
        self._version = version

    def health(self) -> SecretProviderStatus:
        return SecretProviderStatus.HEALTHY

    def resolve(self, request: SecretRequest) -> SecretLease:
        values = self._secrets.get(request.secret_name)
        if values is None:
            raise SecretResolutionError(f"Logical secret {request.secret_name!r} is unavailable.")
        now = datetime.now().astimezone()
        return SecretLease(
            secret_name=request.secret_name,
            values=dict(values),
            version=self._version,
            issued_at=now,
            expires_at=None,
        )

    def renew(self, lease: SecretLease) -> SecretLease:
        raise NotImplementedError("Synthetic leases are not renewable.")

    def revoke(self, lease: SecretLease) -> None:
        return None

    def metadata(self, secret_name: str) -> SecretMetadata:
        values = self._secrets.get(secret_name)
        if values is None:
            raise SecretResolutionError(f"Logical secret {secret_name!r} is unavailable.")
        return SecretMetadata(
            secret_name=secret_name,
            version=self._version,
            updated_at=None,
            field_names=tuple(sorted(values)),
        )
