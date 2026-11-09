"""Disabled-by-default canonical Constant Contact read capability definitions."""
from __future__ import annotations

from datetime import datetime
from kernel.capabilities import (
    CapabilityApproval, CapabilityDefinition, CapabilityEvidence,
    CapabilityLifecycle, CapabilityRegistryService, CapabilityRisk,
    CapabilityStewardship, IdempotencyBehavior,
)
from kernel.execution_providers import (
    ExecutionProvider, ExecutionProviderRegistryService, ProviderApproval,
    ProviderFeatures, ProviderHealth, ProviderLifecycle, ProviderLimits,
    ProviderStewardship, ProviderType,
)

PROVIDER = "constant_contact"
CONTACTS_SEARCH = "marketing.contact.search"
LISTS_SEARCH = "marketing.contact.list.search"
FIELDS_SEARCH = "marketing.contact.field.search"
CAPABILITIES = frozenset({CONTACTS_SEARCH, LISTS_SEARCH, FIELDS_SEARCH})


def definitions(now: datetime) -> tuple[CapabilityDefinition, ...]:
    specs = (
        (CONTACTS_SEARCH, "Search Constant Contact Contacts", "contact", "contacts email opt-in"),
        (LISTS_SEARCH, "Search Constant Contact Lists", "contact_list", "lists contact groups"),
        (FIELDS_SEARCH, "Search Constant Contact Custom Fields", "contact_field", "custom field mapping"),
    )
    return tuple(CapabilityDefinition(
        capability_name=name,
        version="1.0",
        display_name=display,
        lifecycle_status=CapabilityLifecycle.PILOT,
        business_purpose="Governed read-only AOT Constant Contact contact management evidence",
        owner_service="Jason Contact Management",
        architectural_capability_ids=frozenset(),
        risk_level=CapabilityRisk.LOW,
        data_classifications=frozenset({"internal", "confidential"}),
        permitted_execution_modes=frozenset({"deterministic"}),
        input_schema_reference=f"schema://jason/{name.replace('.', '-')}/1.0",
        output_schema_reference=f"schema://jason/{name.replace('.', '-')}-result/1.0",
        invoking_roles=frozenset({"orchestrator"}),
        approval=CapabilityApproval(required=False),
        evidence=CapabilityEvidence(
            required=True,
            requirements=("OAuth-authorized AOT account", "provider response"),
            verification_requirements=("Requester permission and information-release gate",),
        ),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=30,
        maximum_attempts=2,
        failure_behavior="Fail closed; no direct access, provider writes or alternate account",
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification="Read AOT contact-list and contact evidence before approved imports",
            review_interval_days=90,
            retirement_criteria=("Constant Contact no longer approved by AOT",),
            authoritative_change_sources=("Constant Contact V3 developer documentation",),
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "true",
            "resource_types": resource,
            "operation": "search",
            "selector_keys": "limit,cursor",
            "fact_hints": hints,
            "scope_model": "aot_internal_single_oauth_account",
            "account_bound_by": "approved_oauth_connection",
        },
    ) for name, display, resource, hints in specs)


def provider(now: datetime) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=PROVIDER,
        display_name="Constant Contact V3 API",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=ProviderLifecycle.PLANNED,
        health_status=ProviderHealth.UNKNOWN,
        approval_status=ProviderApproval.PILOT,
        execution_modes=frozenset({"deterministic"}),
        capabilities=CAPABILITIES,
        supported_classifications=frozenset({"internal", "confidential"}),
        regions=frozenset({"US"}),
        limits=ProviderLimits(
            maximum_concurrent_executions=2,
            maximum_requests_per_minute=20,
            maximum_execution_seconds=30,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification="AOT contact management integration",
            review_interval_days=90,
            last_reviewed_at=now,
            retirement_criteria=("Provider no longer approved by AOT",),
            vendor_change_sources=("Constant Contact V3 API developer documentation",),
            operational_owner="AOT Managed Services",
            approval_owner="Jason Architecture Authority",
        ),
        created_at=now,
        metadata={
            "connector_id": PROVIDER,
            "resource_authority": "aot_contacts",
            "live_enablement": "disabled_pending_explicit_profile_and_acceptance",
            "oauth_scope": "contact_data offline_access",
        },
    )


def register_foundation(*, capabilities: CapabilityRegistryService,
                        providers: ExecutionProviderRegistryService, now: datetime) -> None:
    for capability in definitions(now):
        capabilities.register(capability)
    providers.register(provider(now))
