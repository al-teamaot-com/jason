"""Unactivated SharePoint runtime composition using isolated Microsoft certificate identity."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from connectors.core.http_transport import UrlLibJsonHttpTransport
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.microsoft_graph.openbao_credentials import OpenBaoMicrosoftCredentialSource
from connectors.microsoft_graph.sharepoint_reader import MicrosoftGraphSharePointReader
from connectors.microsoft_graph.tenant_tokens import GovernedTenantApplicationTokenProvider
from connectors.microsoft_graph.token import MsalCertificateTokenProvider, default_msal_application_factory
from kernel.client_boundaries import (
    BoundaryStatus, ClientBoundaryRepository,
    SQLiteClientBoundaryRepository, SQLiteClientBoundaryStore,
)


@dataclass(frozen=True, slots=True)
class MicrosoftSharePointRuntime:
    store: SQLiteClientBoundaryStore
    reader: MicrosoftGraphSharePointReader


def build_microsoft_sharepoint_runtime(
    *,
    boundary_db: Path,
    openbao_url: str,
    role_id_path: Path,
    secret_id_path: Path,
    transport: UrlLibJsonHttpTransport,
) -> MicrosoftSharePointRuntime:
    """Compose an independent sharepoint-read profile, never borrowing mail/directory access.

    The caller must separately install/validate the client boundary and run the
    governed document connector. This builder never permits automatic activation.
    """
    store = SQLiteClientBoundaryStore(boundary_db)
    boundaries = SQLiteClientBoundaryRepository(store)
    resolver = OpenBaoSecretResolver(
        base_url=openbao_url,
        role_id_path=role_id_path,
        secret_id_path=secret_id_path,
    )
    application_tokens = MsalCertificateTokenProvider(
        boundaries=boundaries,
        credentials=OpenBaoMicrosoftCredentialSource(secrets=resolver),
        application_factory=default_msal_application_factory,
        logical_secret="microsoft_graph.sharepoint_read",
        provider_name="microsoft_graph_sharepoint",
        profile_name="sharepoint-read",
    )
    tenant_tokens = GovernedTenantApplicationTokenProvider(
        boundaries=boundaries,
        tokens=application_tokens,
        provider_name="microsoft_graph_sharepoint",
        profile_name="sharepoint-read",
    )
    return MicrosoftSharePointRuntime(
        store=store,
        reader=MicrosoftGraphSharePointReader(
            tokens=tenant_tokens,
            transport=transport,
        ),
    )



def require_validated_sharepoint_service_boundary(
    *, boundaries: ClientBoundaryRepository, tenant_id: str,
    expected_client_id: str, expected_domain: str,
) -> None:
    """Fail closed unless the dedicated Graph SharePoint profile was consented.

    An AOT directory-read or mail-read binding is NOT a SharePoint binding.
    Separate Entra admin consent and a validated service principal are required
    before a workload can use document read capabilities. No credentials are
    resolved or Graph calls made here.
    """
    if not tenant_id or not expected_client_id or not expected_domain:
        raise ValueError("validated SharePoint boundary identifiers required")
    boundary = boundaries.find_active_for_external_tenant(
        provider="microsoft_graph_sharepoint",
        external_tenant_id=tenant_id,
    )
    if (
        boundary is None
        or boundary.provider != "microsoft_graph_sharepoint"
        or boundary.status is not BoundaryStatus.VALIDATED
        or boundary.profile != "sharepoint-read"
        or boundary.client_id != expected_client_id
        or boundary.external_tenant_id != tenant_id
        or boundary.primary_domain.casefold() != expected_domain.casefold()
        or not boundary.application_id
        or not boundary.service_principal_id
        or boundary.validated_at is None
    ):
        raise PermissionError(
            "Dedicated validated Microsoft Graph SharePoint service binding is required"
        )
