"""Dormant, separately activatable IT Glue records write integration.

This is not a general provider API proxy. The existing Central Orchestrator
J-102 action boundary is the only execution path, and a validated exact client
mapping plus trusted Entra/Jason identity are mandatory. Default OFF.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from connectors.core.contracts import (
    AuditSink, ConnectorAuthorizationError, ConnectorContext, HttpTransport,
)
from connectors.core.openbao_secrets import OpenBaoSecretResolver
from connectors.it_glue.create_claim_store import SQLiteItGlueCreationClaimStore
from connectors.it_glue.governed_record_write import (
    CAPABILITIES as PROVIDER_CAPABILITIES,
    PROFILE_ENV, PROFILE_VALUE, ItGlueGovernedRecordWriter,
)
from kernel.capabilities import (
    CapabilityLifecycle, CapabilityRegistryService, IdempotencyBehavior,
)
from kernel.client_boundaries import ClientBoundaryRepository, BoundaryStatus
from kernel.execution_providers import (
    ExecutionProvider, ExecutionProviderRegistryService, ProviderApproval,
    ProviderFeatures, ProviderHealth, ProviderLifecycle, ProviderLimits,
    ProviderStewardship, ProviderType,
)
from orchestrator.connector_invoker import GovernedConnectorCapabilityInvoker
from orchestrator.invokers import CapabilityInvokerRegistry
from orchestrator.provider_mutation_capability_catalog import _mutation_capability
from orchestrator.provider_read_information_authorizer import TrustedPrincipalBindingResolver
from orchestrator.service import CapabilityInvoker

PROVIDER_ID = "it_glue_record_management"
IT_GLUE_BOUNDARY_PROVIDER = "it_glue"
WRITE_ROLE_PATH = Path("/run/jason-secrets/openbao/it-glue-write/role_id")
WRITE_SECRET_PATH = Path("/run/jason-secrets/openbao/it-glue-write/secret_id")
WRITE_CLAIMS_PATH = Path("/var/lib/jason/authority/itglue-create-claims.sqlite3")
MAP_DB_PATH = Path("/var/lib/jason/authority/client-boundaries.sqlite3")
CANONICAL_CAPABILITIES = {
    "documentation.flexible.asset.create": "it_glue.flexible_asset.create",
    "documentation.flexible.asset.update": "it_glue.flexible_asset.update",
    "documentation.document.create": "it_glue.document.create",
    "documentation.document.update": "it_glue.document.update",
    "documentation.configuration.create": "it_glue.configuration.create",
}
_ID = re.compile(r"^[1-9][0-9]*$")


class ItGlueWriteActivationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ItGlueWriteActivation:
    enabled: bool
    profile: str
    capability_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ValidatedClientItGlueWriteAuthority:
    """Reuse native Jason binding and client boundary; never trust caller org IDs."""

    bindings: TrustedPrincipalBindingResolver
    boundaries: ClientBoundaryRepository

    def require_authorized(self, context: ConnectorContext) -> None:
        if not context.principal_id or not context.client_id:
            raise ConnectorAuthorizationError("IT_GLUE_REQUESTER_AND_CLIENT_REQUIRED")
        if context.principal_id.startswith("jason-autonomy"):
            raise ConnectorAuthorizationError("IT_GLUE_AUTONOMY_SCOPE_NOT_AUTHORIZED")
        binding = self.bindings.find_active_by_jason_identity(
            jason_identity_id=context.principal_id,
        )
        email = getattr(binding, "email_address", None)
        if not isinstance(email, str) or "@" not in email or not email.strip():
            raise ConnectorAuthorizationError("IT_GLUE_TRUSTED_IDENTITY_MISSING")
        self.organization_id_for_client(client_id=context.client_id)

    def organization_id_for_client(self, *, client_id: str) -> int:
        if not client_id or not isinstance(client_id, str):
            raise ConnectorAuthorizationError("IT_GLUE_CLIENT_ID_INVALID")
        b = self.boundaries.find_active_for_client(
            client_id=client_id, provider=IT_GLUE_BOUNDARY_PROVIDER)
        if (b is None or b.status != BoundaryStatus.VALIDATED
                or b.provider != IT_GLUE_BOUNDARY_PROVIDER
                or b.client_id != client_id
                or b.validated_at is None
                or not _ID.fullmatch(str(b.external_tenant_id))):
            raise ConnectorAuthorizationError("IT_GLUE_VALIDATED_CLIENT_ORGANIZATION_MAPPING_REQUIRED")
        reverse = self.boundaries.find_active_for_external_tenant(
            provider=IT_GLUE_BOUNDARY_PROVIDER,
            external_tenant_id=b.external_tenant_id,
        )
        if (reverse is None or reverse.client_id != client_id
                or reverse.id != b.id or reverse.status != BoundaryStatus.VALIDATED):
            raise ConnectorAuthorizationError("IT_GLUE_CLIENT_ORGANIZATION_MAPPING_CONFLICT")
        return int(b.external_tenant_id)


def _definition(*, now: datetime, name: str):
    create = name.endswith(".create")
    original = _mutation_capability(
        now=now,
        capability_name=name,
        display_name="IT Glue: " + name.split(".", 1)[1].replace(".", " ").title(),
        business_purpose="Create or update one explicitly authorized client IT Glue record.",
        resource_types="documentation_flexible_asset,documentation_document,documentation_configuration",
        operation="create" if create else "update",
        idempotency_behavior=(
            IdempotencyBehavior.NON_IDEMPOTENT
            if create else IdempotencyBehavior.CONDITIONALLY_IDEMPOTENT
        ),
    )
    metadata = dict(original.metadata)
    metadata.update({
        "pilot_provider": "it_glue",
        "provider_native_impersonation_required": "false",
        "provider_identity_type": "separate_it_glue_api_key",
        "mcp_action_enabled": "true",
        "mcp_tool_name": "execute_governed_capability",
        "activation_state": "source_only_disabled_by_default",
        "pilot_scope": "exact_client_validated_boundary_only",
    })
    return replace(original, metadata=metadata)


def _provider(*, now: datetime) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=PROVIDER_ID,
        display_name="IT Glue Governed Records Write",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.PLANNED,
        health_status=ProviderHealth.UNKNOWN,
        approval_status=ProviderApproval.PILOT,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset(CANONICAL_CAPABILITIES),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=1,
            maximum_requests_per_minute=10,
            maximum_execution_seconds=60,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification="Create and update authorized client IT Glue records with exact approved plans.",
            review_interval_days=30, last_reviewed_at=now,
            retirement_criteria=(
                "Exact client identity or source authorization cannot be proven.",
                "Write credential becomes unavailable.",
            ),
            vendor_change_sources=("IT Glue API developer specification",),
            operational_owner="AOT IT Operations",
            approval_owner="AOT Owner",
        ),
        created_at=now,
        metadata={
            "connector_id": IT_GLUE_BOUNDARY_PROVIDER,
            "resource_authority": "documentation",
            "write_capability": "true",
            "provider_api_key_service_identity": "true",
            "client_isolation_required": "true",
            "activation_state": "source_only_disabled_by_default",
        },
    )


def register_it_glue_write_foundation(*, capabilities: CapabilityRegistryService,
                                      providers: ExecutionProviderRegistryService,
                                      now: datetime) -> ItGlueWriteActivation:
    """Register BUILDING metadata; only exact release-controlled env activates."""
    for name in CANONICAL_CAPABILITIES:
        capabilities.register(_definition(now=now, name=name))
    providers.register(_provider(now=now))
    profile = os.getenv(PROFILE_ENV, "").strip()
    if not profile:
        return ItGlueWriteActivation(False, "", ())
    if profile != PROFILE_VALUE:
        raise ItGlueWriteActivationError("IT_GLUE_WRITE_PROFILE_NOT_APPROVED")
    provider = providers.get(PROVIDER_ID)
    if (provider.lifecycle_status != ProviderLifecycle.PLANNED
            or provider.approval_status != ProviderApproval.PILOT
            or provider.capabilities != frozenset(CANONICAL_CAPABILITIES)):
        raise ItGlueWriteActivationError("IT_GLUE_WRITE_PROVIDER_CONTRACT_DRIFT")
    for name in CANONICAL_CAPABILITIES:
        current = capabilities.get(capability_name=name, version="1.0")
        if (current.lifecycle_status != CapabilityLifecycle.BUILDING
                or current.maximum_attempts != 1
                or not current.approval.required
                or not current.client_isolation_required
                or current.metadata.get("mcp_action_enabled") != "true"):
            raise ItGlueWriteActivationError("IT_GLUE_WRITE_AUTHORITY_CONTRACT_DRIFT")
    # Exact-release profile is necessary but not sufficient: credentials,
    # validated mapping and exact J-102 approval are checked at invocation.
    for name in CANONICAL_CAPABILITIES:
        capabilities.set_lifecycle(
            capability_name=name, version="1.0",
            lifecycle_status=CapabilityLifecycle.ACTIVE)
    providers.set_approval(provider_id=PROVIDER_ID,
                           approval_status=ProviderApproval.APPROVED)
    providers.set_health(provider_id=PROVIDER_ID,
                         health_status=ProviderHealth.HEALTHY)
    providers.set_lifecycle(provider_id=PROVIDER_ID,
                            lifecycle_status=ProviderLifecycle.AVAILABLE)
    return ItGlueWriteActivation(True, profile, tuple(sorted(CANONICAL_CAPABILITIES)))


def build_it_glue_write_invoker(*, openbao_url: str,
                                transport: HttpTransport, audit: AuditSink,
                                bindings: TrustedPrincipalBindingResolver,
                                boundaries: ClientBoundaryRepository,
                                role_id_path: Path = WRITE_ROLE_PATH,
                                secret_id_path: Path = WRITE_SECRET_PATH,
                                claims_path: Path = WRITE_CLAIMS_PATH,
                                base_url: str = "https://api.itglue.com") -> CapabilityInvoker:
    if os.getenv(PROFILE_ENV, "") != PROFILE_VALUE:
        raise ItGlueWriteActivationError("IT_GLUE_WRITE_PROFILE_DISABLED")
    if bindings is None or boundaries is None:
        raise ItGlueWriteActivationError("IT_GLUE_TRUSTED_IDENTITY_AND_MAPPING_REQUIRED")
    if not role_id_path.is_file() or not secret_id_path.is_file():
        raise ItGlueWriteActivationError("IT_GLUE_WRITE_APPROLE_UNPROVISIONED")
    secret_resolver = OpenBaoSecretResolver(
        base_url=openbao_url, role_id_path=role_id_path,
        secret_id_path=secret_id_path)
    connector = ItGlueGovernedRecordWriter(
        transport=transport, credentials=secret_resolver,
        authorization=ValidatedClientItGlueWriteAuthority(
            bindings=bindings, boundaries=boundaries),
        audit=audit,
        creation_claims=SQLiteItGlueCreationClaimStore(claims_path),
        base_url=base_url,
    )
    return GovernedConnectorCapabilityInvoker(
        connectors={PROVIDER_ID: connector},
        provider_capability_map={
            (PROVIDER_ID, canonical): native
            for canonical, native in CANONICAL_CAPABILITIES.items()
        },
    )


def register_it_glue_write_invoker(*, invokers: CapabilityInvokerRegistry,
                                   invoker: CapabilityInvoker) -> None:
    for name in CANONICAL_CAPABILITIES:
        invokers.register(name, invoker)
