from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from connectors.core.http_transport import UrlLibJsonHttpTransport
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.microsoft_graph.openbao_credentials import OpenBaoMicrosoftCredentialSource
from connectors.microsoft_graph.tenant_tokens import GovernedTenantApplicationTokenProvider
from connectors.microsoft_graph.token import MsalCertificateTokenProvider, default_msal_application_factory
from connectors.microsoft_graph.user_directory import MicrosoftGraphUserDirectoryReader
from kernel.client_boundaries import SQLiteClientBoundaryRepository, SQLiteClientBoundaryStore


@dataclass(frozen=True, slots=True)
class MicrosoftDirectoryRuntime:
    store: SQLiteClientBoundaryStore
    directory: MicrosoftGraphUserDirectoryReader


def build_microsoft_directory_runtime(
    *,
    boundary_db: Path,
    openbao_url: str,
    role_id_path: Path,
    secret_id_path: Path,
    transport: UrlLibJsonHttpTransport,
) -> MicrosoftDirectoryRuntime:
    """Compose Microsoft identity enrichment through governed Jason primitives.

    The runtime holds only durable non-secret boundary metadata. Certificate material is
    resolved from OpenBao through the dedicated AppRole when an application token is
    actually required. There is no environment, filesystem-certificate, or transport-
    supplied email fallback in this composition.
    """

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
        logical_secret="microsoft_graph.directory_read",
        provider_name="microsoft_graph",
        profile_name="directory-read",
    )
    tenant_tokens = GovernedTenantApplicationTokenProvider(
        boundaries=boundaries,
        tokens=application_tokens,
        provider_name="microsoft_graph",
        profile_name="directory-read",
    )
    directory = MicrosoftGraphUserDirectoryReader(
        tokens=tenant_tokens,
        transport=transport,
    )
    return MicrosoftDirectoryRuntime(store=store, directory=directory)
