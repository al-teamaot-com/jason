from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from connectors.core.contracts import AuditSink
from connectors.core.http_transport import UrlLibJsonHttpTransport
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.microsoft_graph.openbao_credentials import OpenBaoMicrosoftCredentialSource
from connectors.microsoft_graph.sharepoint_read import MicrosoftSharePointReadConnector
from connectors.microsoft_graph.token import MsalCertificateTokenProvider, default_msal_application_factory
from kernel.client_boundaries import SQLiteClientBoundaryRepository, SQLiteClientBoundaryStore


@dataclass(frozen=True, slots=True)
class MicrosoftSharePointRuntime:
    store: SQLiteClientBoundaryStore
    connector: MicrosoftSharePointReadConnector


def build_microsoft_sharepoint_runtime(
    *,
    boundary_db: Path,
    openbao_url: str,
    role_id_path: Path,
    secret_id_path: Path,
    transport: UrlLibJsonHttpTransport,
    audit: AuditSink,
) -> MicrosoftSharePointRuntime:
    """Compose Jason's governed application-only SharePoint read path."""

    store = SQLiteClientBoundaryStore(boundary_db)
    boundaries = SQLiteClientBoundaryRepository(store)
    secrets = OpenBaoSecretResolver(
        base_url=openbao_url,
        role_id_path=role_id_path,
        secret_id_path=secret_id_path,
    )
    credentials = OpenBaoMicrosoftCredentialSource(secrets=secrets)
    application_tokens = MsalCertificateTokenProvider(
        boundaries=boundaries,
        credentials=credentials,
        application_factory=default_msal_application_factory,
        logical_secret="microsoft_sharepoint.read",
        provider_name="microsoft_sharepoint",
        profile_name="sharepoint-read",
    )
    connector = MicrosoftSharePointReadConnector(
        tokens=application_tokens,
        transport=transport,
        audit=audit,
    )
    return MicrosoftSharePointRuntime(store=store, connector=connector)
