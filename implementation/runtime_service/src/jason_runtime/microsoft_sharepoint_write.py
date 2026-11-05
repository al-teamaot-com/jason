"""Production composition for the narrow AOT SharePoint write profile."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from connectors.core.http_transport import UrlLibJsonHttpTransport
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.microsoft_graph.openbao_credentials import OpenBaoMicrosoftCredentialSource
from connectors.microsoft_graph.sharepoint_files import SharePointFileClient
from connectors.microsoft_graph.tenant_tokens import GovernedTenantApplicationTokenProvider
from connectors.microsoft_graph.token import MsalCertificateTokenProvider, default_msal_application_factory
from kernel.client_boundaries import SQLiteClientBoundaryRepository, SQLiteClientBoundaryStore


@dataclass(frozen=True, slots=True)
class MicrosoftSharePointRuntime:
    store: SQLiteClientBoundaryStore
    files: SharePointFileClient


def build_microsoft_sharepoint_runtime(*, boundary_db: Path, openbao_url: str,
                                       role_id_path: Path, secret_id_path: Path,
                                       transport: UrlLibJsonHttpTransport) -> MicrosoftSharePointRuntime:
    """Build an isolated SharePoint writer; missing consent/secret fails closed."""
    store = SQLiteClientBoundaryStore(boundary_db)
    boundaries = SQLiteClientBoundaryRepository(store)
    secrets = OpenBaoSecretResolver(base_url=openbao_url, role_id_path=role_id_path, secret_id_path=secret_id_path)
    credentials = OpenBaoMicrosoftCredentialSource(secrets=secrets)
    application_tokens = MsalCertificateTokenProvider(
        boundaries=boundaries,
        credentials=credentials,
        application_factory=default_msal_application_factory,
        logical_secret="microsoft_graph.sharepoint_write",
        provider_name="microsoft_sharepoint",
        profile_name="sharepoint-write",
    )
    tenant_tokens = GovernedTenantApplicationTokenProvider(
        boundaries=boundaries,
        tokens=application_tokens,
        provider_name="microsoft_sharepoint",
        profile_name="sharepoint-write",
    )
    return MicrosoftSharePointRuntime(
        store=store,
        files=SharePointFileClient(tokens=tenant_tokens, transport=transport),
    )
