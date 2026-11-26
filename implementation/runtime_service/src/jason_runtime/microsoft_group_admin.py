"""Isolated Microsoft 365 group mutation composition, not a production registration.

Injected dependencies are the existing central Kernel boundary repository,
independent MSAL/OpenBao read and write token providers, shared transport,
ordinary authenticated technician entitlement and audit sink. Production
composition must deliberately activate and register this after a reviewed
release and tenant consent. Merely importing this module creates no authority.
"""
from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass
from typing import Mapping

from connectors.core.contracts import ConnectorAuthorizationError, ConnectorContext
from orchestrator.microsoft_group_admin_catalog import (
    AOT_PILOT_CLIENT_ID, AOT_PILOT_TENANT_ID, AOT_PILOT_OWNER_ID,
    AOT_PILOT_OWNER_PRINCIPAL_ID, AOT_PILOT_GROUP_NAME, AOT_PILOT_GROUP_ALIAS,
    GROUP_ADMIN_CAPABILITIES,
)

from connectors.core.contracts import AuditSink, HttpTransport
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.microsoft_graph.openbao_credentials import OpenBaoMicrosoftCredentialSource
from connectors.microsoft_graph.group_executor import (
    MicrosoftGraphGovernedGroupConnector, MicrosoftGraphGroupWriter,
    MicrosoftGroupBoundaryValidator, MicrosoftWriteEntitlement, MicrosoftGroupReader,
    GroupWriteScope, READ_PROFILE, READ_PROVIDER, WRITE_PROVIDER,
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


@dataclass(frozen=True, slots=True)
class AotPilotGroupEntitlement:
    """Exact approved pilot group and active Owner only; not a generic tenant grant."""
    reader: MicrosoftGroupReader

    def require_entitled(
        self, *, context: ConnectorContext, operation_name: str,
        scope: GroupWriteScope, arguments: Mapping[str, str],
    ) -> None:
        if (context.organization_id != "aot"
                or context.client_id != AOT_PILOT_CLIENT_ID
                or context.principal_id != AOT_PILOT_OWNER_PRINCIPAL_ID
                or scope.client_id != AOT_PILOT_CLIENT_ID
                or scope.tenant_id != AOT_PILOT_TENANT_ID
                or operation_name not in GROUP_ADMIN_CAPABILITIES):
            raise ConnectorAuthorizationError("M365_PILOT_PRINCIPAL_TENANT_NOT_AUTHORIZED")
        if operation_name == "identity.group.create":
            if (arguments.get("display_name") != AOT_PILOT_GROUP_NAME
                    or arguments.get("mail_nickname") != AOT_PILOT_GROUP_ALIAS
                    or arguments.get("group_type") != "security"
                    or arguments.get("verified_owner_id") != AOT_PILOT_OWNER_ID
                    or arguments.get("description")
                    not in (None, "AOT authorized Jason group administration acceptance pilot")):
                raise ConnectorAuthorizationError("M365_PILOT_CREATE_ARGUMENTS_NOT_APPROVED")
            return
        if arguments.get("verified_member_id") != AOT_PILOT_OWNER_ID:
            raise ConnectorAuthorizationError("M365_PILOT_MEMBER_NOT_APPROVED")
        group_id = arguments.get("verified_group_id")
        if not group_id:
            raise ConnectorAuthorizationError("M365_PILOT_GROUP_ID_REQUIRED")
        match = self.reader.find_groups_by_alias(
            tenant_id=scope.tenant_id, alias=AOT_PILOT_GROUP_ALIAS,
        )
        if len(match) != 1 or match[0].get("id") != group_id:
            raise ConnectorAuthorizationError("M365_PILOT_TARGET_NOT_APPROVED")
        group = self.reader.read_group(tenant_id=scope.tenant_id, group_id=group_id)
        if (group.get("displayName") != AOT_PILOT_GROUP_NAME
                or group.get("mailNickname") != AOT_PILOT_GROUP_ALIAS
                or group.get("groupTypes") != []
                or group.get("mailEnabled") is not False
                or group.get("securityEnabled") is not True
                or group.get("isAssignableToRole") is not False
                or group.get("onPremisesSyncEnabled") is True
                or not self.reader.is_owner(
                    tenant_id=scope.tenant_id, group_id=group_id,
                    user_id=AOT_PILOT_OWNER_ID,
                )):
            raise ConnectorAuthorizationError("M365_PILOT_GROUP_NOT_OWNER_VERIFIED")


def build_microsoft_group_admin_invoker(
    *,
    boundaries: ClientBoundaryRepository,
    read_tokens: MicrosoftApplicationTokenProvider,
    write_tokens: MicrosoftApplicationTokenProvider,
    transport: HttpTransport,
    entitlement: MicrosoftWriteEntitlement | None,
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
        entitlement=entitlement if entitlement is not None else AotPilotGroupEntitlement(reader),
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
    entitlement: MicrosoftWriteEntitlement | None,
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
