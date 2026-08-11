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
    InMemoryExecutionProviderRegistry,
    ProviderApproval,
    ProviderFeatures,
    ProviderHealth,
    ProviderLifecycle,
    ProviderLimits,
    ProviderStewardship,
    ProviderType,
)


ENDPOINT_DEVICE_SEARCH = "endpoint.device.search"
ENDPOINT_DEVICE_READ = "endpoint.device.read"
DATTO_RMM_PROVIDER = "datto_rmm"


def endpoint_device_search(now: datetime) -> CapabilityDefinition:
    """Broad provider-neutral endpoint discovery/read capability.

    This is intentionally not a field-specific operation. A caller supplies a resource
    selector and requested facts; the selected provider may return a richer device
    record from which governed reasoning can answer the question.
    """

    return CapabilityDefinition(
        capability_name=ENDPOINT_DEVICE_SEARCH,
        version="1.0",
        display_name="Search Managed Endpoints",
        lifecycle_status=CapabilityLifecycle.ACTIVE,
        business_purpose=(
            "Locate managed endpoints by provider-neutral selectors and retrieve "
            "read-only device records for governed resource inquiries."
        ),
        owner_service="Jason Resource Intelligence",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-013"}),
        risk_level=CapabilityRisk.LOW,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference="schema://jason/endpoint-device-search/1.0",
        output_schema_reference="schema://jason/endpoint-device-records/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(
            required=True,
            requirements=("provider result", "source provider identity"),
            verification_requirements=(
                "resource selector remains in authorized scope",
                "ambiguous selectors never auto-select a resource",
                "a unique discovery candidate exposes a durable resource identifier",
            ),
        ),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=30,
        maximum_attempts=2,
        failure_behavior="Fail closed without shell, node, agent, or first-match fallback.",
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Use existing endpoint-management data dynamically instead of creating "
                "one-off scripts for each endpoint fact."
            ),
            review_interval_days=90,
            retirement_criteria=(
                "Replaced by a broader governed endpoint resource interface.",
            ),
            authoritative_change_sources=("Datto RMM API documentation",),
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "true",
            "resource_types": "endpoint",
            "operation": "search",
            "selector_keys": "hostname,name,resource_id,site,serial_number",
            "fact_hints": (
                "hostname device name last user logged in user username site status "
                "online offline operating system ip address mac address hardware software "
                "device identifier serial number inventory"
            ),
            "identity_semantics": (
                "Human-readable names, hostnames, aliases, labels, serial-like tokens, and "
                "site labels are discovery selectors, not durable identity. Discovery must "
                "observe ambiguity and may proceed only after one authorized candidate is "
                "resolved to a durable resource_id. Never select the first provider result."
            ),
            "planning_guidance": (
                "Prefer this capability when the human names an endpoint but does not "
                "already supply its durable provider-neutral resource identifier. Treat "
                "the supplied name/hostname as discovery criteria and require explicit "
                "disambiguation when more than one authorized resource remains."
            ),
        },
    )


def endpoint_device_read(now: datetime) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=ENDPOINT_DEVICE_READ,
        version="1.0",
        display_name="Read Managed Endpoint",
        lifecycle_status=CapabilityLifecycle.ACTIVE,
        business_purpose=(
            "Retrieve a managed endpoint record by durable resource identifier for "
            "governed read-only resource inquiries."
        ),
        owner_service="Jason Resource Intelligence",
        architectural_capability_ids=frozenset({"JAC-005", "JAC-013"}),
        risk_level=CapabilityRisk.LOW,
        data_classifications=frozenset({"internal"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference="schema://jason/endpoint-device-read/1.0",
        output_schema_reference="schema://jason/endpoint-device-record/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(
            required=True,
            requirements=("provider result", "source provider identity"),
            verification_requirements=("resource identifier remains in authorized scope",),
        ),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=30,
        maximum_attempts=2,
        failure_behavior="Fail closed without shell, node, or agent fallback.",
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification="Read existing endpoint-management records through a reusable resource interface.",
            review_interval_days=90,
            retirement_criteria=(
                "Replaced by a broader governed endpoint resource interface.",
            ),
            authoritative_change_sources=("Datto RMM API documentation",),
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "true",
            "resource_types": "endpoint",
            "operation": "read",
            "selector_keys": "resource_id",
            "fact_hints": (
                "device details hostname last user logged in user site status operating "
                "system ip address mac address hardware software serial number inventory"
            ),
            "identity_semantics": "resource_id is a durable resolved endpoint identity",
            "planning_guidance": (
                "Prefer this capability when a durable endpoint resource identifier is already known."
            ),
        },
    )


def datto_rmm_endpoint_provider(now: datetime) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=DATTO_RMM_PROVIDER,
        display_name="Datto RMM",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.AVAILABLE,
        health_status=ProviderHealth.HEALTHY,
        approval_status=ProviderApproval.APPROVED,
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset({ENDPOINT_DEVICE_SEARCH, ENDPOINT_DEVICE_READ}),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=10,
            maximum_requests_per_minute=120,
            maximum_execution_seconds=30,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification=(
                "Datto RMM is the authoritative existing endpoint-management platform; "
                "Jason integrates with it instead of duplicating endpoint state collection."
            ),
            review_interval_days=90,
            last_reviewed_at=now,
            retirement_criteria=(
                "Datto RMM is no longer the approved managed-endpoint authority.",
                "A replacement provider satisfies the same canonical endpoint capabilities.",
            ),
            vendor_change_sources=("Datto RMM API documentation",),
            operational_owner="AOT IT Operations",
            approval_owner="Jason Architecture Authority",
        ),
        created_at=now,
        metadata={
            "connector_id": "datto_rmm",
            "resource_authority": "managed_endpoint",
        },
    )


def register_endpoint_resource_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
) -> None:
    """Register reusable endpoint resource primitives and the current approved provider."""

    capabilities.register(endpoint_device_search(now))
    capabilities.register(endpoint_device_read(now))
    providers.register(datto_rmm_endpoint_provider(now))
