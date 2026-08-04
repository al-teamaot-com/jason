from __future__ import annotations

import re
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from kernel.client_boundaries import (
    BoundaryStatus,
    ClientBoundary,
    ClientBoundaryRepository,
)


GRAPH_DEFAULT_SCOPE = (
    "https://graph.microsoft.com/.default"
)
MICROSOFT_AUTHORITY_HOST = (
    "https://login.microsoftonline.com"
)

_THUMBPRINT_PATTERN = re.compile(
    r"^(?:[A-F0-9]{40}|[A-F0-9]{64})$"
)


class MicrosoftTokenError(RuntimeError):
    """Safe Microsoft application-token failure."""

    def __init__(
        self,
        *,
        error_code: str,
        message: str,
    ) -> None:
        self.error_code = error_code
        super().__init__(message)


class MicrosoftBoundaryError(MicrosoftTokenError):
    """The requested Kernel client boundary is not authorized."""


class MicrosoftCredentialError(MicrosoftTokenError):
    """The Microsoft application credential is invalid."""


class MicrosoftTokenAcquisitionError(MicrosoftTokenError):
    """MSAL could not acquire a valid application token."""


@dataclass(frozen=True)
class MicrosoftCertificateCredential:
    private_key_pem: str
    certificate_pem: str
    certificate_thumbprint: str
    generation: str

    def __post_init__(self) -> None:
        if "PRIVATE KEY" not in self.private_key_pem:
            raise ValueError(
                "private_key_pem must contain a PEM private key."
            )

        if "BEGIN CERTIFICATE" not in self.certificate_pem:
            raise ValueError(
                "certificate_pem must contain a PEM certificate."
            )

        normalized_thumbprint = re.sub(
            r"[^A-Fa-f0-9]",
            "",
            self.certificate_thumbprint,
        ).upper()

        if not _THUMBPRINT_PATTERN.fullmatch(
            normalized_thumbprint
        ):
            raise ValueError(
                "certificate_thumbprint must be a valid "
                "SHA-1 or SHA-256 hexadecimal thumbprint."
            )

        if (
            not isinstance(self.generation, str)
            or not self.generation.strip()
        ):
            raise ValueError(
                "generation must be a non-empty string."
            )

        object.__setattr__(
            self,
            "certificate_thumbprint",
            normalized_thumbprint,
        )


@dataclass(frozen=True)
class MicrosoftApplicationToken:
    access_token: str
    token_type: str
    expires_at_epoch: int
    tenant_id: str
    application_id: str
    scope: str
    certificate_thumbprint: str

    def __post_init__(self) -> None:
        if not self.access_token:
            raise ValueError(
                "access_token must not be empty."
            )

        if self.token_type.lower() != "bearer":
            raise ValueError(
                "Only Bearer Microsoft tokens are supported."
            )

        if self.expires_at_epoch <= 0:
            raise ValueError(
                "expires_at_epoch must be positive."
            )


class MicrosoftCredentialSource(Protocol):
    def resolve(
        self,
        logical_secret: str,
    ) -> MicrosoftCertificateCredential:
        ...


class MicrosoftApplicationTokenProvider(Protocol):
    def acquire_for_client(
        self,
        *,
        client_id: str,
        correlation_id: str,
    ) -> MicrosoftApplicationToken:
        ...

    def invalidate_client(
        self,
        *,
        client_id: str,
    ) -> None:
        ...


class MsalConfidentialApplication(Protocol):
    def acquire_token_for_client(
        self,
        scopes: list[str],
    ) -> Mapping[str, object]:
        ...

    def remove_tokens_for_client(self) -> None:
        ...


class MsalApplicationFactory(Protocol):
    def __call__(
        self,
        *,
        client_id: str,
        authority: str,
        client_credential: Mapping[str, str],
    ) -> MsalConfidentialApplication:
        ...


@dataclass(frozen=True)
class _ApplicationCacheKey:
    application_id: str
    tenant_id: str
    scope: str
    credential_generation: str


class MsalCertificateTokenProvider:
    def __init__(
        self,
        *,
        boundaries: ClientBoundaryRepository,
        credentials: MicrosoftCredentialSource,
        application_factory: MsalApplicationFactory,
        logical_secret: str = (
            "microsoft_graph.directory_read"
        ),
        provider_name: str = "microsoft_graph",
        profile_name: str = "directory-read",
        scope: str = GRAPH_DEFAULT_SCOPE,
        authority_host: str = MICROSOFT_AUTHORITY_HOST,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if not logical_secret.strip():
            raise ValueError(
                "logical_secret must be non-empty."
            )

        if not provider_name.strip():
            raise ValueError(
                "provider_name must be non-empty."
            )

        if not profile_name.strip():
            raise ValueError(
                "profile_name must be non-empty."
            )

        if scope != GRAPH_DEFAULT_SCOPE:
            raise ValueError(
                "Only Microsoft Graph .default scope "
                "is approved."
            )

        if authority_host != MICROSOFT_AUTHORITY_HOST:
            raise ValueError(
                "Only the Microsoft public-cloud authority "
                "is approved."
            )

        self._boundaries = boundaries
        self._credentials = credentials
        self._application_factory = application_factory
        self._logical_secret = logical_secret
        self._provider_name = provider_name
        self._profile_name = profile_name
        self._scope = scope
        self._authority_host = authority_host.rstrip("/")
        self._clock = clock or time.time
        self._applications: dict[
            _ApplicationCacheKey,
            MsalConfidentialApplication,
        ] = {}

    def acquire_for_client(
        self,
        *,
        client_id: str,
        correlation_id: str,
    ) -> MicrosoftApplicationToken:
        self._require_identifier(
            client_id,
            "client_id",
        )
        self._require_identifier(
            correlation_id,
            "correlation_id",
        )

        boundary = self._resolve_boundary(client_id)

        try:
            credential = self._credentials.resolve(
                self._logical_secret
            )
        except MicrosoftTokenError:
            raise
        except Exception as error:
            raise MicrosoftCredentialError(
                error_code=(
                    "MICROSOFT_CREDENTIAL_RESOLUTION_FAILED"
                ),
                message=(
                    "Microsoft application credential "
                    "could not be resolved."
                ),
            ) from error

        cache_key = _ApplicationCacheKey(
            application_id=boundary.application_id,
            tenant_id=boundary.external_tenant_id,
            scope=self._scope,
            credential_generation=credential.generation,
        )

        application = self._applications.get(cache_key)

        if application is None:
            authority = (
                f"{self._authority_host}/"
                f"{boundary.external_tenant_id}"
            )

            application = self._application_factory(
                client_id=boundary.application_id,
                authority=authority,
                client_credential={
                    "private_key": (
                        credential.private_key_pem
                    ),
                    "thumbprint": (
                        credential.certificate_thumbprint
                    ),
                    "public_certificate": (
                        credential.certificate_pem
                    ),
                },
            )
            self._applications[cache_key] = application

        try:
            response = application.acquire_token_for_client(
                scopes=[self._scope]
            )
        except Exception as error:
            raise MicrosoftTokenAcquisitionError(
                error_code=(
                    "MICROSOFT_TOKEN_SERVICE_UNAVAILABLE"
                ),
                message=(
                    "Microsoft application token acquisition "
                    "failed."
                ),
            ) from error

        return self._parse_response(
            response=response,
            boundary=boundary,
            credential=credential,
        )

    def invalidate_client(
        self,
        *,
        client_id: str,
    ) -> None:
        self._require_identifier(
            client_id,
            "client_id",
        )

        boundary = self._boundaries.find_active_for_client(
            client_id=client_id,
            provider=self._provider_name,
        )

        if boundary is None:
            return

        matching_keys = [
            key
            for key in self._applications
            if (
                key.application_id
                == boundary.application_id
                and key.tenant_id
                == boundary.external_tenant_id
            )
        ]

        for key in matching_keys:
            application = self._applications.pop(key)

            try:
                application.remove_tokens_for_client()
            except Exception:
                # Local cache eviction has already occurred.
                # Remote access-token revocation is not implied.
                continue

    def _resolve_boundary(
        self,
        client_id: str,
    ) -> ClientBoundary:
        boundary = self._boundaries.find_active_for_client(
            client_id=client_id,
            provider=self._provider_name,
        )

        if boundary is None:
            raise MicrosoftBoundaryError(
                error_code=(
                    "MICROSOFT_BOUNDARY_NOT_FOUND"
                ),
                message=(
                    "No active Microsoft client boundary "
                    "was found."
                ),
            )

        if boundary.status is not BoundaryStatus.VALIDATED:
            raise MicrosoftBoundaryError(
                error_code=(
                    "MICROSOFT_BOUNDARY_NOT_VALIDATED"
                ),
                message=(
                    "Microsoft client boundary is not "
                    "validated."
                ),
            )

        if boundary.profile != self._profile_name:
            raise MicrosoftBoundaryError(
                error_code=(
                    "MICROSOFT_PROFILE_NOT_APPROVED"
                ),
                message=(
                    "Microsoft client boundary uses an "
                    "unapproved profile."
                ),
            )

        try:
            normalized_tenant = str(
                uuid.UUID(boundary.external_tenant_id)
            )
            normalized_application = str(
                uuid.UUID(boundary.application_id)
            )
        except ValueError as error:
            raise MicrosoftBoundaryError(
                error_code=(
                    "MICROSOFT_BOUNDARY_IDENTIFIER_INVALID"
                ),
                message=(
                    "Microsoft client boundary contains "
                    "an invalid identifier."
                ),
            ) from error

        if (
            normalized_tenant
            != boundary.external_tenant_id.lower()
            or normalized_application
            != boundary.application_id.lower()
        ):
            raise MicrosoftBoundaryError(
                error_code=(
                    "MICROSOFT_BOUNDARY_IDENTIFIER_INVALID"
                ),
                message=(
                    "Microsoft client boundary contains "
                    "an invalid identifier."
                ),
            )

        return boundary

    def _parse_response(
        self,
        *,
        response: Mapping[str, object],
        boundary: ClientBoundary,
        credential: MicrosoftCertificateCredential,
    ) -> MicrosoftApplicationToken:
        access_token = response.get("access_token")

        if isinstance(access_token, str) and access_token:
            token_type = response.get(
                "token_type",
                "Bearer",
            )
            expires_in = response.get("expires_in")

            if (
                not isinstance(token_type, str)
                or token_type.lower() != "bearer"
            ):
                raise self._invalid_response()

            if (
                isinstance(expires_in, bool)
                or not isinstance(expires_in, (int, float))
                or expires_in <= 0
            ):
                raise self._invalid_response()

            return MicrosoftApplicationToken(
                access_token=access_token,
                token_type="Bearer",
                expires_at_epoch=(
                    int(self._clock()) + int(expires_in)
                ),
                tenant_id=boundary.external_tenant_id,
                application_id=boundary.application_id,
                scope=self._scope,
                certificate_thumbprint=(
                    credential.certificate_thumbprint
                ),
            )

        provider_error = response.get("error")

        if isinstance(provider_error, str):
            error_code = self._translate_error(
                provider_error
            )
        else:
            error_code = (
                "MICROSOFT_TOKEN_RESPONSE_INVALID"
            )

        raise MicrosoftTokenAcquisitionError(
            error_code=error_code,
            message=(
                "Microsoft application token could not "
                "be acquired."
            ),
        )

    @staticmethod
    def _translate_error(provider_error: str) -> str:
        translations = {
            "invalid_client": (
                "MICROSOFT_CERTIFICATE_REJECTED"
            ),
            "unauthorized_client": (
                "MICROSOFT_APPLICATION_NOT_FOUND"
            ),
            "invalid_grant": (
                "MICROSOFT_CONSENT_REQUIRED"
            ),
            "invalid_scope": (
                "MICROSOFT_PERMISSION_DENIED"
            ),
        }

        return translations.get(
            provider_error,
            "MICROSOFT_TOKEN_ACQUISITION_FAILED",
        )

    @staticmethod
    def _invalid_response() -> MicrosoftTokenAcquisitionError:
        return MicrosoftTokenAcquisitionError(
            error_code="MICROSOFT_TOKEN_RESPONSE_INVALID",
            message=(
                "Microsoft token service returned an "
                "invalid response."
            ),
        )

    @staticmethod
    def _require_identifier(
        value: str,
        field_name: str,
    ) -> None:
        if (
            not isinstance(value, str)
            or not value.strip()
        ):
            raise ValueError(
                f"{field_name} must be a non-empty string."
            )


def default_msal_application_factory(
    *,
    client_id: str,
    authority: str,
    client_credential: Mapping[str, str],
) -> MsalConfidentialApplication:
    from msal import ConfidentialClientApplication

    return ConfidentialClientApplication(
        client_id=client_id,
        authority=authority,
        client_credential=dict(client_credential),
    )
