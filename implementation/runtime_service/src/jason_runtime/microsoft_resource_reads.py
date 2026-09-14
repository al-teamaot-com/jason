"""Source-only composition for metadata-driven Microsoft Graph reads.

This module intentionally does not choose Microsoft entities, fields, or business
question routes. It composes the existing client-boundary/token architecture with the
provider metadata catalog and generic ``provider.resource.search/read`` connector.
The permission profile and logical secret are explicit governance inputs supplied by
the runtime activation layer; they are not inferred by a model or conversation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.core.text_http_transport import UrlLibBoundedTextHttpTransport
from connectors.microsoft_graph.openbao_credentials import OpenBaoMicrosoftCredentialSource
from connectors.microsoft_graph.resource_catalog_source import MicrosoftGraphMetadataCatalogSource
from connectors.microsoft_graph.resource_connector import MicrosoftGraphResourceConnector
from connectors.microsoft_graph.resource_provider import build_microsoft_graph_resource_provider
from connectors.microsoft_graph.token import MsalCertificateTokenProvider, default_msal_application_factory
from kernel.client_boundaries import SQLiteClientBoundaryRepository, SQLiteClientBoundaryStore
from kernel.capabilities import CapabilityRegistryService
from kernel.execution_providers import ExecutionProviderRegistryService
from orchestrator.connector_invoker import GovernedConnectorCapabilityInvoker
from orchestrator.provider_resource_capability_catalog import (
    PROVIDER_RESOURCE_READ,
    PROVIDER_RESOURCE_SEARCH,
    register_provider_resource_capabilities,
)


@dataclass(frozen=True, slots=True)
class MicrosoftResourceReadRuntime:
    store: SQLiteClientBoundaryStore
    catalog_source: MicrosoftGraphMetadataCatalogSource
    connector: MicrosoftGraphResourceConnector
    invoker: GovernedConnectorCapabilityInvoker


def register_microsoft_resource_read_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
) -> None:
    """Register generic PILOT capabilities plus a non-operational Microsoft provider."""

    register_provider_resource_capabilities(capabilities=capabilities, now=now)
    providers.register(build_microsoft_graph_resource_provider(now=now))


def register_microsoft_resource_read_invokers(
    *,
    invokers,
    runtime: MicrosoftResourceReadRuntime,
) -> None:
    """Bind both generic resource operations to one governed connector invoker."""

    invokers.register(PROVIDER_RESOURCE_SEARCH, runtime.invoker)
    invokers.register(PROVIDER_RESOURCE_READ, runtime.invoker)


def build_microsoft_resource_read_runtime(
    *,
    boundary_db: Path,
    openbao_url: str,
    role_id_path: Path,
    secret_id_path: Path,
    json_transport,
    audit,
    permission_profile_name: str,
    logical_secret: str,
    metadata_transport: UrlLibBoundedTextHttpTransport | None = None,
) -> MicrosoftResourceReadRuntime:
    """Compose generic Graph reads without activating any provider or capability."""

    profile = str(permission_profile_name).strip()
    secret = str(logical_secret).strip()
    if not profile:
        raise ValueError("Microsoft resource-read permission profile is required")
    if not secret:
        raise ValueError("Microsoft resource-read logical secret is required")

    store = SQLiteClientBoundaryStore(boundary_db)
    boundaries = SQLiteClientBoundaryRepository(store)
    secrets = OpenBaoSecretResolver(
        base_url=openbao_url,
        role_id_path=role_id_path,
        secret_id_path=secret_id_path,
    )
    credentials = OpenBaoMicrosoftCredentialSource(secrets=secrets)
    tokens = MsalCertificateTokenProvider(
        boundaries=boundaries,
        credentials=credentials,
        application_factory=default_msal_application_factory,
        logical_secret=secret,
        provider_name="microsoft_graph",
        profile_name=profile,
    )

    # Structural Graph metadata is provider-global and does not consume tenant data.
    # Tenant/client authorization still occurs in ``tokens.acquire_for_client`` when
    # the actual connector executes a governed resource read.
    catalog_source = MicrosoftGraphMetadataCatalogSource(
        transport=metadata_transport or UrlLibBoundedTextHttpTransport(),
        permission_profile_name=profile,
    )
    connector = MicrosoftGraphResourceConnector(
        tokens=tokens,
        catalogs=catalog_source,
        transport=json_transport,
        audit=audit,
        permission_profile_name=profile,
    )
    invoker = GovernedConnectorCapabilityInvoker(
        connectors={"microsoft_graph": connector},
        provider_capability_map={
            ("microsoft_graph", PROVIDER_RESOURCE_SEARCH): PROVIDER_RESOURCE_SEARCH,
            ("microsoft_graph", PROVIDER_RESOURCE_READ): PROVIDER_RESOURCE_READ,
        },
    )
    return MicrosoftResourceReadRuntime(
        store=store,
        catalog_source=catalog_source,
        connector=connector,
        invoker=invoker,
    )
