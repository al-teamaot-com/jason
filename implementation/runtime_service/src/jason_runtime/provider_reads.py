from __future__ import annotations

from datetime import datetime
from pathlib import Path

from connectors.autotask.capability_manifest import build_autotask_manifest
from connectors.autotask.connector import AutotaskConnector
from connectors.core.contracts import AuditSink, HttpTransport, SecretResolver
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.it_glue.capability_manifest import build_it_glue_manifest
from connectors.it_glue.connector import ItGlueConnector
from kernel.capabilities import CapabilityRegistryService
from kernel.execution_providers import ExecutionProviderRegistryService
from orchestrator.connector_invoker import GovernedConnectorCapabilityInvoker
from orchestrator.integration_broker import IntegrationBroker
from orchestrator.invokers import CapabilityInvokerRegistry
from orchestrator.provider_read_argument_adapter import GovernedProviderReadConnectorInvoker
from orchestrator.provider_read_capability_catalog import (
    AUTOTASK_CAPABILITIES,
    AUTOTASK_PROVIDER,
    DOCUMENTATION_CONFIGURATION_READ,
    DOCUMENTATION_CONFIGURATION_SEARCH,
    DOCUMENTATION_CONTACT_READ,
    DOCUMENTATION_CONTACT_SEARCH,
    DOCUMENTATION_DOCUMENT_READ,
    DOCUMENTATION_DOCUMENT_SEARCH,
    DOCUMENTATION_LOCATION_READ,
    DOCUMENTATION_LOCATION_SEARCH,
    DOCUMENTATION_ORGANIZATION_READ,
    DOCUMENTATION_ORGANIZATION_SEARCH,
    IT_GLUE_CAPABILITIES,
    IT_GLUE_PROVIDER,
    SERVICE_COMPANY_READ,
    SERVICE_COMPANY_SEARCH,
    SERVICE_CONFIGURATION_READ,
    SERVICE_CONFIGURATION_SEARCH,
    SERVICE_CONTACT_READ,
    SERVICE_CONTACT_SEARCH,
    SERVICE_ENTITY_DESCRIBE,
    SERVICE_TICKET_NOTES_SEARCH,
    SERVICE_TICKET_READ,
    SERVICE_TICKET_SEARCH,
    register_provider_read_foundation,
)

from .provider_read_activation import apply_provider_read_activation_from_env


_PROVIDER_CAPABILITY_MAP = {
    (IT_GLUE_PROVIDER, DOCUMENTATION_ORGANIZATION_SEARCH): "it_glue.entity.query",
    (IT_GLUE_PROVIDER, DOCUMENTATION_ORGANIZATION_READ): "it_glue.organization.get",
    (IT_GLUE_PROVIDER, DOCUMENTATION_CONTACT_SEARCH): "it_glue.entity.query",
    (IT_GLUE_PROVIDER, DOCUMENTATION_CONTACT_READ): "it_glue.entity.get",
    (IT_GLUE_PROVIDER, DOCUMENTATION_LOCATION_SEARCH): "it_glue.entity.query",
    (IT_GLUE_PROVIDER, DOCUMENTATION_LOCATION_READ): "it_glue.entity.get",
    (IT_GLUE_PROVIDER, DOCUMENTATION_CONFIGURATION_SEARCH): "it_glue.entity.query",
    (IT_GLUE_PROVIDER, DOCUMENTATION_CONFIGURATION_READ): "it_glue.entity.get",
    (IT_GLUE_PROVIDER, DOCUMENTATION_DOCUMENT_SEARCH): "it_glue.document.search",
    (IT_GLUE_PROVIDER, DOCUMENTATION_DOCUMENT_READ): "it_glue.document.get",
    (AUTOTASK_PROVIDER, SERVICE_COMPANY_SEARCH): "autotask.company.search",
    (AUTOTASK_PROVIDER, SERVICE_COMPANY_READ): "autotask.company.get",
    (AUTOTASK_PROVIDER, SERVICE_CONTACT_SEARCH): "autotask.contact.search",
    (AUTOTASK_PROVIDER, SERVICE_CONTACT_READ): "autotask.contact.get",
    (AUTOTASK_PROVIDER, SERVICE_TICKET_SEARCH): "autotask.ticket.search",
    (AUTOTASK_PROVIDER, SERVICE_TICKET_READ): "autotask.ticket.get",
    (AUTOTASK_PROVIDER, SERVICE_TICKET_NOTES_SEARCH): "autotask.ticket.notes.list",
    (AUTOTASK_PROVIDER, SERVICE_CONFIGURATION_SEARCH): "autotask.configuration.search",
    (AUTOTASK_PROVIDER, SERVICE_CONFIGURATION_READ): "autotask.configuration.get",
    (AUTOTASK_PROVIDER, SERVICE_ENTITY_DESCRIBE): "autotask.entity.describe",
}

_RUNTIME_OPENBAO_ROOT = Path("/run/jason-secrets/openbao")
_RUNTIME_ROLE_ID = _RUNTIME_OPENBAO_ROOT / "role_id"
_RUNTIME_SECRET_ID = _RUNTIME_OPENBAO_ROOT / "secret_id"
_RUNTIME_PROVIDER_CREDENTIALS = {
    IT_GLUE_PROVIDER: _RUNTIME_OPENBAO_ROOT / "it-glue",
    AUTOTASK_PROVIDER: _RUNTIME_OPENBAO_ROOT / "autotask",
}


def register_provider_read_runtime_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    integration_broker: IntegrationBroker,
    now: datetime,
) -> None:
    """Register provider-read contracts and apply only an explicit activation profile."""

    register_provider_read_foundation(
        capabilities=capabilities,
        providers=providers,
        now=now,
    )
    integration_broker.register(build_it_glue_manifest())
    integration_broker.register(build_autotask_manifest())
    apply_provider_read_activation_from_env(
        capabilities=capabilities,
        providers=providers,
    )


def scope_runtime_provider_secret_resolvers(
    secrets: SecretResolver,
) -> tuple[SecretResolver, SecretResolver]:
    """Split the known runtime OpenBao bootstrap into provider AppRoles.

    The runtime historically passes its DRMM/general OpenBao resolver into this
    composition seam. When, and only when, that resolver uses the canonical
    generic runtime bootstrap paths, clone its non-secret configuration onto
    provider-specific AppRole file paths. This preserves separate IT Glue and
    Autotask policies without changing DRMM or broadening an AppRole.

    Acceptance harnesses deliberately use provider-specific paths under /opt;
    those remain unchanged and continue to use the supplied compatibility
    resolver for their single selected provider.
    """

    if not isinstance(secrets, OpenBaoSecretResolver):
        return secrets, secrets
    if (
        secrets.role_id_path != _RUNTIME_ROLE_ID
        or secrets.secret_id_path != _RUNTIME_SECRET_ID
    ):
        return secrets, secrets

    it_glue_root = _RUNTIME_PROVIDER_CREDENTIALS[IT_GLUE_PROVIDER]
    autotask_root = _RUNTIME_PROVIDER_CREDENTIALS[AUTOTASK_PROVIDER]
    return (
        secrets.with_credential_paths(
            role_id_path=it_glue_root / "role_id",
            secret_id_path=it_glue_root / "secret_id",
        ),
        secrets.with_credential_paths(
            role_id_path=autotask_root / "role_id",
            secret_id_path=autotask_root / "secret_id",
        ),
    )


def build_provider_read_invoker(
    *,
    transport: HttpTransport,
    audit: AuditSink,
    secrets: SecretResolver | None = None,
    it_glue_secrets: SecretResolver | None = None,
    autotask_secrets: SecretResolver | None = None,
) -> GovernedProviderReadConnectorInvoker:
    """Compose governed provider reads while preserving provider identities.

    Explicit provider resolvers take precedence. The compatibility ``secrets``
    seam remains for bounded single-provider acceptance and tests. In normal
    runtime composition the known generic OpenBao bootstrap is deterministically
    split into provider-specific runtime AppRole identities.
    """

    if secrets is not None and it_glue_secrets is None and autotask_secrets is None:
        it_glue_secrets, autotask_secrets = scope_runtime_provider_secret_resolvers(
            secrets
        )

    it_glue_resolver = it_glue_secrets or secrets
    autotask_resolver = autotask_secrets or secrets
    if it_glue_resolver is None or autotask_resolver is None:
        raise ValueError(
            "IT Glue and Autotask secret resolvers are required for provider reads"
        )

    connectors = {
        IT_GLUE_PROVIDER: ItGlueConnector(
            secrets=it_glue_resolver,
            transport=transport,
            audit=audit,
        ),
        AUTOTASK_PROVIDER: AutotaskConnector(
            secrets=autotask_resolver,
            transport=transport,
            audit=audit,
        ),
    }
    delegate = GovernedConnectorCapabilityInvoker(
        connectors=connectors,
        provider_capability_map=_PROVIDER_CAPABILITY_MAP,
    )
    return GovernedProviderReadConnectorInvoker(delegate=delegate)


def register_provider_read_invokers(
    *,
    invokers: CapabilityInvokerRegistry,
    invoker: GovernedProviderReadConnectorInvoker,
) -> None:
    for capability in sorted(IT_GLUE_CAPABILITIES | AUTOTASK_CAPABILITIES):
        invokers.register(capability, invoker)
