"""Compose opt-in routine RW provider adapters under existing orchestration.

No new API transport, no new direct MCP tool, no credential fallback.
"""
from __future__ import annotations

import os
from pathlib import Path

from connectors.core.contracts import AuditSink, HttpTransport
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.it_glue.configuration_note_update import ItGlueConfigurationNoteUpdateConnector
from connectors.microsoft_graph.openbao_credentials import OpenBaoMicrosoftCredentialSource
from connectors.microsoft_graph.standard_user_create import (
    MicrosoftGraphStandardUserCreateConnector, MicrosoftGraphCreateUserWriter,
)
from connectors.microsoft_graph.token import (
    MsalCertificateTokenProvider, default_msal_application_factory,
)
from kernel.client_boundaries import ClientBoundaryRepository
from orchestrator.connector_invoker import GovernedConnectorCapabilityInvoker
from orchestrator.service import CapabilityInvoker

from .routine_rw_credentials import (
    GovernedGraphUserCreateTokens, OpenBaoOnboardingPasswordReader,
)
from .routine_rw_registration import (
    ENTRA_PROVIDER_ID, ENTRA_USER_CREATE, IT_GLUE_NOTES, IT_GLUE_PROVIDER_ID,
)
from .routine_rw_scope import AotEntraOnboardingScope, AotItGlueWriteScope


IT_GLUE_ROLE = "/run/jason-secrets/openbao/it-glue-write/role_id"
IT_GLUE_SECRET = "/run/jason-secrets/openbao/it-glue-write/secret_id"
ENTRA_ROLE = "/run/jason-secrets/openbao/microsoft-graph-user-create/role_id"
ENTRA_SECRET = "/run/jason-secrets/openbao/microsoft-graph-user-create/secret_id"
PASSWORD_ROLE = "/run/jason-secrets/openbao/microsoft-graph-onboarding-password/role_id"
PASSWORD_SECRET = "/run/jason-secrets/openbao/microsoft-graph-onboarding-password/secret_id"


def configured_credential_paths() -> dict[str, tuple[Path, Path]]:
    return {
        IT_GLUE_NOTES: (
            Path(os.getenv("JASON_IT_GLUE_RW_OPENBAO_ROLE_ID_PATH", IT_GLUE_ROLE)),
            Path(os.getenv("JASON_IT_GLUE_RW_OPENBAO_SECRET_ID_PATH", IT_GLUE_SECRET)),
        ),
        ENTRA_USER_CREATE: (
            Path(os.getenv("JASON_ENTRA_USER_CREATE_OPENBAO_ROLE_ID_PATH", ENTRA_ROLE)),
            Path(os.getenv("JASON_ENTRA_USER_CREATE_OPENBAO_SECRET_ID_PATH", ENTRA_SECRET)),
        ),
        "entra.initial_password": (
            Path(os.getenv("JASON_ENTRA_ONBOARDING_PASSWORD_OPENBAO_ROLE_ID_PATH", PASSWORD_ROLE)),
            Path(os.getenv("JASON_ENTRA_ONBOARDING_PASSWORD_OPENBAO_SECRET_ID_PATH", PASSWORD_SECRET)),
        ),
    }


def bootstrap_present(capability: str) -> bool:
    paths = configured_credential_paths()
    required = ([capability, "entra.initial_password"]
                if capability == ENTRA_USER_CREATE else [capability])
    for key in required:
        for path in paths[key]:
            try:
                # A devnull placeholder or a missing mount must never activate
                # a production mutation capability.
                if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
                    return False
            except OSError:
                return False
    return True


def build_routine_rw_invokers(
    *, enabled_capabilities: tuple[str, ...],
    openbao_url: str,
    boundaries: ClientBoundaryRepository,
    identities,
    approvals,
    directory,
    transport: HttpTransport,
    audit: AuditSink,
) -> dict[str, CapabilityInvoker]:
    paths = configured_credential_paths()
    invokers = {}

    if IT_GLUE_NOTES in enabled_capabilities:
        role, secret = paths[IT_GLUE_NOTES]
        connector = ItGlueConfigurationNoteUpdateConnector(
            transport=transport,
            credentials=OpenBaoSecretResolver(
                base_url=openbao_url, role_id_path=role, secret_id_path=secret,
            ),
            authorization=AotItGlueWriteScope(
                identities=identities, boundaries=boundaries,
            ),
            audit=audit,
        )
        invokers[IT_GLUE_NOTES] = GovernedConnectorCapabilityInvoker(
            connectors={IT_GLUE_PROVIDER_ID: connector},
            provider_capability_map={
                (IT_GLUE_PROVIDER_ID, IT_GLUE_NOTES): connector.provider_name + ".configuration.update",
            },
        )

    if ENTRA_USER_CREATE in enabled_capabilities:
        role, secret = paths[ENTRA_USER_CREATE]
        token_secrets = OpenBaoSecretResolver(
            base_url=openbao_url,
            role_id_path=role, secret_id_path=secret,
        )
        tokens = MsalCertificateTokenProvider(
            boundaries=boundaries,
            credentials=OpenBaoMicrosoftCredentialSource(secrets=token_secrets),
            application_factory=default_msal_application_factory,
            logical_secret="microsoft_graph.user_create",
            provider_name="microsoft_graph_user_create",
            profile_name="user-create",
        )
        password_role, password_secret = paths["entra.initial_password"]
        connector = MicrosoftGraphStandardUserCreateConnector(
            reader=directory,
            writer=MicrosoftGraphCreateUserWriter(
                tokens=GovernedGraphUserCreateTokens(
                    boundaries=boundaries, provider=tokens,
                ),
                transport=transport,
            ),
            authority=AotEntraOnboardingScope(
                identities=identities, approvals=approvals, boundaries=boundaries,
            ),
            credentials=OpenBaoOnboardingPasswordReader(
                openbao_url=openbao_url,
                role_id_path=password_role,
                secret_id_path=password_secret,
            ),
            audit=audit,
        )
        invokers[ENTRA_USER_CREATE] = GovernedConnectorCapabilityInvoker(
            connectors={ENTRA_PROVIDER_ID: connector},
            provider_capability_map={
                (ENTRA_PROVIDER_ID, ENTRA_USER_CREATE): ENTRA_USER_CREATE,
            },
        )
    return invokers
