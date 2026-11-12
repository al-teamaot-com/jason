"""Isolated Microsoft 365 group mutation composition, not a production registration.

Injected dependencies are the existing central Kernel boundary repository,
independent MSAL/OpenBao read and write token providers, shared transport,
ordinary authenticated technician entitlement and audit sink. Production
composition must deliberately activate and register this after a reviewed
release and tenant consent. Merely importing this module creates no authority.
"""
from __future__ import annotations

from pathlib import Path

from connectors.core.contracts import AuditSink, HttpTransport
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.microsoft_graph.openbao_credentials import OpenBaoMicrosoftCredentialSource
from connectors.microsoft_graph.group_executor import (
    MicrosoftGraphGovernedGroupConnector, MicrosoftGraphGroupWriter,
    MicrosoftGroupBoundaryValidator, MicrosoftWriteEntitlement,
    READ_PROFILE, READ_PROVIDER, WRITE_PROVIDER,
)
from connectors.microsoft_graph.group_reader import MicrosoftGraphGroupReader
from connectors.microsoft_graph.governed_operations import MICROSOFT_GOVERNED_OPERATIONS
from connectors.microsoft_graph.tenant_tokens import GovernedTenantApplicationTokenProvider
from connectors.microsoft_graph.token import (
    MicrosoftApplicationTokenProvider, MsalCertificateTokenProvider,
    default_msal_application_factory,
)
from connectors.microsoft_graph.user_directory import MicrosoftGraphUserDirectoryReader
from kernel.client_boundaries import ClientBoundaryRepository
from orchestrator.connector_invoker import GovernedConnectorCapabilityInvoker
from orchestrator.invokers import CapabilityInvokerRegistry


def build_microsoft_group_admin_invoker(
    *,
    boundaries: ClientBoundaryRepository,
    read_tokens: MicrosoftApplicationTokenProvider,
    write_tokens: MicrosoftApplicationTokenProvider,
    transport: HttpTransport,
    entitlement: MicrosoftWriteEntitlement,
    audit: AuditSink,
) -> GovernedConnectorCapabilityInvoker:
    reader_tokens = GovernedTenantApplicationTokenProvider(
        boundaries=boundaries, tokens=read_tokens,
        provider_name=READ_PROVIDER, profile_name=READ_PROFILE,
    )
    reader = MicrosoftGraphGroupReader(
        tokens=reader_tokens,
        transport=transport,
        users=MicrosoftGraphUserDirectoryReader(tokens=reader_tokens, transport=transport),
    )
    connector = MicrosoftGraphGovernedGroupConnector(
        boundaries=MicrosoftGroupBoundaryValidator(boundaries),
        reader=reader,
        writer=MicrosoftGraphGroupWriter(tokens=write_tokens, transport=transport),
        entitlement=entitlement,
        audit=audit,
    )
    return GovernedConnectorCapabilityInvoker(
        connectors={WRITE_PROVIDER: connector},
        provider_capability_map={
            (WRITE_PROVIDER, name): name for name in MICROSOFT_GOVERNED_OPERATIONS
        },
    )


def register_microsoft_group_admin_invoker(
    *, invokers: CapabilityInvokerRegistry,
    invoker: GovernedConnectorCapabilityInvoker,
) -> None:
    """Register only under a separately authorized runtime activation flow."""
    for capability_name in sorted(MICROSOFT_GOVERNED_OPERATIONS):
        invokers.register(capability_name, invoker)



def build_microsoft_group_admin_openbao_invoker(
    *,
    boundaries: ClientBoundaryRepository,
    openbao_url: str,
    read_role_id_path: Path,
    read_secret_id_path: Path,
    write_role_id_path: Path,
    write_secret_id_path: Path,
    transport: HttpTransport,
    entitlement: MicrosoftWriteEntitlement,
    audit: AuditSink,
) -> GovernedConnectorCapabilityInvoker:
    """Source-only reusable assembly from separate approved OpenBao AppRoles.

    No calls or role registration are made during assembly. Both AppRole
    credentials must be separately provisioned through governed release paths.
    """
    read_paths = {read_role_id_path, read_secret_id_path}
    write_paths = {write_role_id_path, write_secret_id_path}
    if (len(read_paths) != 2 or len(write_paths) != 2
            or read_paths & write_paths or not openbao_url):
        raise ValueError("M365_GROUP_APPROLE_IDENTITIES_MUST_BE_DISTINCT")
    read_secrets = OpenBaoSecretResolver(
        base_url=openbao_url,
        role_id_path=read_role_id_path, secret_id_path=read_secret_id_path,
    )
    write_secrets = OpenBaoSecretResolver(
        base_url=openbao_url,
        role_id_path=write_role_id_path, secret_id_path=write_secret_id_path,
    )
    read_tokens = MsalCertificateTokenProvider(
        boundaries=boundaries,
        credentials=OpenBaoMicrosoftCredentialSource(secrets=read_secrets),
        application_factory=default_msal_application_factory,
        logical_secret="microsoft_graph.group_read",
        provider_name=READ_PROVIDER, profile_name=READ_PROFILE,
    )
    write_tokens = MsalCertificateTokenProvider(
        boundaries=boundaries,
        credentials=OpenBaoMicrosoftCredentialSource(secrets=write_secrets),
        application_factory=default_msal_application_factory,
        logical_secret="microsoft_graph.group_write",
        provider_name=WRITE_PROVIDER, profile_name="group-write",
    )
    return build_microsoft_group_admin_invoker(
        boundaries=boundaries, read_tokens=read_tokens,
        write_tokens=write_tokens, transport=transport,
        entitlement=entitlement, audit=audit,
    )
