from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from kernel.client_boundaries import BoundaryStatus, ClientBoundaryRepository

from .token import MicrosoftApplicationTokenProvider, MicrosoftBoundaryError


@dataclass(frozen=True, slots=True)
class GovernedTenantApplicationTokenProvider:
    """Resolve an authenticated Microsoft tenant through a Kernel boundary.

    Conversation transports may assert only the already-authenticated Microsoft tenant
    identifier. This adapter maps that external tenant to a validated Jason client
    boundary, then delegates token acquisition to the existing governed application-token
    provider. It never accepts an application ID, credential, provider, profile, or secret
    from conversation input.
    """

    boundaries: ClientBoundaryRepository
    tokens: MicrosoftApplicationTokenProvider
    provider_name: str = "microsoft_graph"
    profile_name: str = "directory-read"

    def __post_init__(self) -> None:
        if not self.provider_name.strip():
            raise ValueError("provider_name must be non-empty")
        if not self.profile_name.strip():
            raise ValueError("profile_name must be non-empty")

    def access_token_for_tenant(self, *, microsoft_tenant_id: str) -> str:
        tenant_id = microsoft_tenant_id.strip().lower()
        try:
            tenant_id = str(UUID(tenant_id))
        except (ValueError, AttributeError) as error:
            raise MicrosoftBoundaryError(
                error_code="MICROSOFT_TENANT_IDENTIFIER_INVALID",
                message="Authenticated Microsoft tenant identifier is invalid.",
            ) from error

        boundary = self.boundaries.find_active_for_external_tenant(
            provider=self.provider_name,
            external_tenant_id=tenant_id,
        )
        if boundary is None:
            raise MicrosoftBoundaryError(
                error_code="MICROSOFT_BOUNDARY_NOT_FOUND",
                message="No active Microsoft tenant boundary was found.",
            )
        if boundary.status is not BoundaryStatus.VALIDATED:
            raise MicrosoftBoundaryError(
                error_code="MICROSOFT_BOUNDARY_NOT_VALIDATED",
                message="Microsoft tenant boundary is not validated.",
            )
        if boundary.profile != self.profile_name:
            raise MicrosoftBoundaryError(
                error_code="MICROSOFT_PROFILE_NOT_APPROVED",
                message="Microsoft tenant boundary uses an unapproved profile.",
            )
        if boundary.external_tenant_id.lower() != tenant_id:
            raise MicrosoftBoundaryError(
                error_code="MICROSOFT_BOUNDARY_TENANT_MISMATCH",
                message="Microsoft tenant boundary did not match authenticated tenant.",
            )

        token = self.tokens.acquire_for_client(
            client_id=boundary.client_id,
            correlation_id=f"microsoft-directory:{tenant_id}",
        )
        if token.tenant_id.lower() != tenant_id:
            raise MicrosoftBoundaryError(
                error_code="MICROSOFT_TOKEN_TENANT_MISMATCH",
                message="Microsoft token tenant did not match authenticated tenant.",
            )
        if token.application_id.lower() != boundary.application_id.lower():
            raise MicrosoftBoundaryError(
                error_code="MICROSOFT_TOKEN_APPLICATION_MISMATCH",
                message="Microsoft token application did not match governed boundary.",
            )
        return token.access_token
