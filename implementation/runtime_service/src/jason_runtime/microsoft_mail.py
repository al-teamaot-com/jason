from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from connectors.core.http_transport import UrlLibJsonHttpTransport
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.microsoft_graph.mailbox_reader import MicrosoftGraphMailboxReader
from connectors.microsoft_graph.openbao_credentials import OpenBaoMicrosoftCredentialSource
from connectors.microsoft_graph.tenant_tokens import GovernedTenantApplicationTokenProvider
from connectors.microsoft_graph.token import MsalCertificateTokenProvider, default_msal_application_factory
from kernel.client_boundaries import SQLiteClientBoundaryRepository, SQLiteClientBoundaryStore


@dataclass(frozen=True, slots=True)
class MicrosoftMailRuntime:
    store: SQLiteClientBoundaryStore
    reader: MicrosoftGraphMailboxReader


def build_microsoft_mail_runtime(
    *,
    boundary_db: Path,
    openbao_url: str,
    role_id_path: Path,
    secret_id_path: Path,
    transport: UrlLibJsonHttpTransport,
) -> MicrosoftMailRuntime:
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
        logical_secret="microsoft_graph.mail_read",
        provider_name="microsoft_graph_mail",
        profile_name="mail-read",
    )
    tenant_tokens = GovernedTenantApplicationTokenProvider(
        boundaries=boundaries,
        tokens=application_tokens,
        provider_name="microsoft_graph_mail",
        profile_name="mail-read",
    )
    return MicrosoftMailRuntime(
        store=store,
        reader=MicrosoftGraphMailboxReader(
            tokens=tenant_tokens,
            transport=transport,
        ),
    )
