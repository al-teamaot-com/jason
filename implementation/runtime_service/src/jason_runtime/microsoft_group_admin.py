"""Isolated Microsoft 365 group mutation composition, not a production registration.

Injected dependencies are the existing central Kernel boundary repository,
independent MSAL/OpenBao read and write token providers, shared transport,
ordinary authenticated technician entitlement and audit sink. Production
composition must deliberately activate and register this after a reviewed
release and tenant consent. Merely importing this module creates no authority.
"""
from __future__ import annotations

from connectors.core.contracts import AuditSink, HttpTransport
from connectors.microsoft_graph.group_executor import (
    MicrosoftGraphGovernedGroupConnector, MicrosoftGraphGroupWriter,
    MicrosoftGroupBoundaryValidator, MicrosoftWriteEntitlement,
    READ_PROFILE, READ_PROVIDER, WRITE_PROVIDER,
)
from connectors.microsoft_graph.group_reader import MicrosoftGraphGroupReader
from connectors.microsoft_graph.governed_operations import MICROSOFT_GOVERNED_OPERATIONS
from connectors.microsoft_graph.tenant_tokens import GovernedTenantApplicationTokenProvider
from connectors.microsoft_graph.token import MicrosoftApplicationTokenProvider
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
