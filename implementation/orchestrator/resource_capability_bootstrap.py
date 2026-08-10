"""Canonical bootstrap definitions for broad, provider-neutral resource capabilities.

These definitions describe what Jason may ask for. Provider-specific connectors remain
behind execution-provider routing; human-facing planning must not depend on DRMM names.
"""

from __future__ import annotations

from datetime import datetime, timezone

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


ENDPOINT_DEVICE_SEARCH = "endpoint.device.search"
DATTO_RMM_ENDPOINT_PROVIDER = "datto-rmm-endpoint-read"


def endpoint_device_search_capability(*, created_at: datetime | None = None) -> CapabilityDefinition:
    now = created_at or datetime.now(timezone.utc)
    return CapabilityDefinition(
        capability_name=ENDPOINT_DEVICE_SEARCH,
        version="1.0",
        display_name="Endpoint Device Search",
        lifecycle_status=CapabilityLifecycle.ACTIVE,
        business_purpose=(
            "Retrieve existing managed-endpoint facts using governed resource providers "
            "before considering custom collection or scripts."
        ),
        owner_service="Jason Resource Intelligence",
        architectural_capability_ids=frozenset({"JAC-006"}),
        risk_level=CapabilityRisk.LOW,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"observe"}),
        input_schema_reference="schema://resource-query/1.0",
        output_schema_reference="schema://resource-result/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(required=True, requirements=("provider result",)),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=30,
        maximum_attempts=1,
        failure_behavior="Fail closed when no governed provider can satisfy the inquiry.",
        tenant_isolation_required=True,
        client_isolation_required=True,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Prefer reusable access to existing endpoint-management data over bespoke scripts."
            ),
            review_interval_days=90,
            retirement_criteria=("Replaced by a governed equivalent resource capability.",),
            authoritative_change_sources=("Datto RMM API", "Kaseya platform capability reviews"),
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "resource_types": "endpoint",
            "fact_semantics": "device inventory,status,identity,last user,audit facts",
        },
    )


def datto_rmm_endpoint_provider(*, created_at: datetime | None = None) -> ExecutionProvider:
    now = created_at or datetime.now(timezone.utc)
    return ExecutionProvider(
        provider_id=DATTO_RMM_ENDPOINT_PROVIDER,
        display_name="Datto RMM Endpoint Read Provider",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
        health_status=ProviderHealth.HEALTHY,
        approval_status=ProviderApproval.APPROVED,
        execution_modes=frozenset({"observe"}),
        capabilities=frozenset({ENDPOINT_DEVICE_SEARCH}),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(maximum_execution_seconds=30),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="datto-rmm-api",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification=(
                "Use Datto RMM as an existing authoritative managed-endpoint resource."
            ),
            review_interval_days=90,
            last_reviewed_at=now,
            retirement_criteria=(
                "Datto RMM is no longer authoritative or a better governed provider supersedes it.",
            ),
            vendor_change_sources=("Datto RMM API", "Kaseya release notes"),
        ),
        created_at=now,
        metadata={
            "connector": "datto_rmm",
            "connector_capability": "datto_rmm.device.search",
            "resource_types": "endpoint",
        },
    )


def register_endpoint_resource_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    created_at: datetime | None = None,
) -> None:
    """Register the broad endpoint contract and its current approved DRMM provider."""
    capabilities.register(endpoint_device_search_capability(created_at=created_at))
    providers.register(datto_rmm_endpoint_provider(created_at=created_at))
