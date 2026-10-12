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
from kernel.client_boundaries import SQLiteClientBoundaryRepository, SQLiteClientBoundaryStore


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
