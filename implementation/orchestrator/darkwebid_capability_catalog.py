from __future__ import annotations

from datetime import datetime

from kernel.capabilities import (
    CapabilityApproval,
    CapabilityDefinition,
    CapabilityEvidence,
    CapabilityLifecycle,
    CapabilityRegistryService,
    CapabilityRisk,
    CapabilityStewardship,
    IdempotencyBehavior,
)
from kernel.execution_providers import (
    ExecutionProvider,
    ExecutionProviderRegistryService,
    ProviderApproval,
    ProviderFeatures,
    ProviderHealth,
    ProviderLifecycle,
    ProviderLimits,
    ProviderStewardship,
    ProviderType,
)

CREDENTIAL_EXPOSURE_ORGANIZATION_SEARCH = "credential.exposure.organization.search"
CREDENTIAL_EXPOSURE_ORGANIZATION_READ = "credential.exposure.organization.read"
DARKWEBID_PROVIDER = "darkwebid"

_DARKWEBID_CAPABILITIES = (
    CREDENTIAL_EXPOSURE_ORGANIZATION_SEARCH,
    CREDENTIAL_EXPOSURE_ORGANIZATION_READ,
)


def _read_capability(
    *,
    now: datetime,
    name: str,
    display_name: str,
    purpose: str,
    operation: str,
    selector_keys: str,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=name,
        version="1.0",
        display_name=display_name,
        lifecycle_status=CapabilityLifecycle.ACTIVE,
        business_purpose=purpose,
        owner_service="Jason Credential Exposure Intelligence",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-013"}),
        risk_level=CapabilityRisk.LOW,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference=f"schema://jason/{name.replace('.', '-')}/1.0",
        output_schema_reference=f"schema://jason/{name.replace('.', '-')}-result/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(
            required=True,
            requirements=("provider result",),
            verification_requirements=(
                "request remains organization-wide AOT internal",
                "provider response is obtained through the vaulted Dark Web ID identity",
            ),
        ),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=30,
        maximum_attempts=2,
        failure_behavior="Fail closed without shell, browser, or unscoped provider fallback.",
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Use Dark Web ID as AOT's provider-native source for managed credential-exposure organization inventory."
            ),
            review_interval_days=90,
            retirement_criteria=(
                "Dark Web ID is no longer AOT's approved credential-exposure source.",
                "A replacement satisfies the canonical credential-exposure contracts.",
            ),
            authoritative_change_sources=(
                "Kaseya Dark Web ID External API documentation",
                "AOT credential exposure operations policy",
            ),
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "true",
            "resource_types": "credential_exposure_organization,darkwebid_organization",
            "operation": operation,
            "selector_keys": selector_keys,
            "scope_model": "aot_internal_msp_organization_inventory",
        },
    )


def darkwebid_capabilities(now: datetime) -> tuple[CapabilityDefinition, ...]:
    return (
        _read_capability(
            now=now,
            name=CREDENTIAL_EXPOSURE_ORGANIZATION_SEARCH,
            display_name="Search Credential Exposure Organizations",
            purpose="List organizations available to AOT's governed Dark Web ID integration identity.",
            operation="search",
            selector_keys="page,limit",
        ),
        _read_capability(
            now=now,
            name=CREDENTIAL_EXPOSURE_ORGANIZATION_READ,
            display_name="Read Credential Exposure Organization",
            purpose="Read one Dark Web ID organization by provider UUID.",
            operation="read",
            selector_keys="uuid",
        ),
    )


def darkwebid_provider(now: datetime, *, enabled: bool) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=DARKWEBID_PROVIDER,
        display_name="Kaseya Dark Web ID External API",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=(ProviderLifecycle.AVAILABLE if enabled else ProviderLifecycle.PLANNED),
        health_status=(ProviderHealth.HEALTHY if enabled else ProviderHealth.UNAVAILABLE),
        approval_status=(ProviderApproval.APPROVED if enabled else ProviderApproval.BLOCKED),
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset(_DARKWEBID_CAPABILITIES),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=5,
            maximum_requests_per_minute=30,
            maximum_execution_seconds=30,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification=(
                "Dark Web ID is AOT's provider-native source for monitored organization and credential-exposure evidence."
            ),
            review_interval_days=90,
            last_reviewed_at=now,
            retirement_criteria=(
                "Dark Web ID is no longer AOT's approved credential-exposure source.",
                "A replacement satisfies the canonical credential-exposure contracts.",
            ),
            vendor_change_sources=(
                "Kaseya Dark Web ID External API documentation",
                "Kaseya Dark Web ID release notes",
            ),
            operational_owner="AOT Managed Services",
            approval_owner="Jason Architecture Authority",
        ),
        created_at=now,
        metadata={
            "connector_id": DARKWEBID_PROVIDER,
            "resource_authority": "credential_exposure",
            "live_enablement": "enabled" if enabled else "blocked_pending_activation",
            "initial_scope": "organization_inventory_read_only",
        },
    )


def register_darkwebid_resource_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
    enabled: bool,
) -> None:
    for capability in darkwebid_capabilities(now):
        capabilities.register(capability)
    providers.register(darkwebid_provider(now, enabled=enabled))
