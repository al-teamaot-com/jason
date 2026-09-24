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

DNSFILTER_PROVIDER = "dnsfilter"
DNS_PROTECTION_ORGANIZATION_READ = "dns.protection.organization.read"
DNS_PROTECTION_SITE_SEARCH = "dns.protection.site.search"
DNS_PROTECTION_POLICY_SEARCH = "dns.protection.policy.search"
DNS_PROTECTION_AGENT_SEARCH = "dns.protection.agent.search"
DNS_PROTECTION_AGENT_COUNTS_READ = "dns.protection.agent.counts.read"

_DNSFILTER_CAPABILITIES = (
    DNS_PROTECTION_ORGANIZATION_READ,
    DNS_PROTECTION_SITE_SEARCH,
    DNS_PROTECTION_POLICY_SEARCH,
    DNS_PROTECTION_AGENT_SEARCH,
    DNS_PROTECTION_AGENT_COUNTS_READ,
)


def _read_capability(
    *,
    now: datetime,
    name: str,
    display_name: str,
    purpose: str,
    resource_types: str,
    operation: str,
    selector_keys: str,
    fact_hints: str,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_name=name,
        version="1.0",
        display_name=display_name,
        lifecycle_status=CapabilityLifecycle.PILOT,
        business_purpose=purpose,
        owner_service="Jason DNS Protection Intelligence",
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
            requirements=("provider result", "validated client boundary"),
            verification_requirements=(
                "Autotask company maps to one validated DNSFilter organization ID",
                "provider queries are server-scoped to the mapped organization",
                "resource reads prove the mapped organization where the API exposes that relationship",
            ),
        ),
        dependencies=frozenset(),
        idempotency_behavior=IdempotencyBehavior.IDEMPOTENT,
        idempotency_key_required=False,
        timeout_seconds=30,
        maximum_attempts=2,
        failure_behavior=(
            "Fail closed without shell, browser, private endpoint, mutation, "
            "or unscoped provider fallback."
        ),
        tenant_isolation_required=True,
        client_isolation_required=False,
        stewardship=CapabilityStewardship(
            steward="technology-steward",
            business_justification=(
                "Use DNSFilter as authoritative evidence for protective DNS "
                "coverage, policy assignment, and roaming-client posture."
            ),
            review_interval_days=90,
            retirement_criteria=(
                "DNSFilter is no longer AOT's approved protective DNS authority.",
                "A replacement satisfies the canonical DNS protection contracts.",
            ),
            authoritative_change_sources=(
                "DNSFilter API documentation",
                "AOT DNSFilter posture standard",
            ),
        ),
        created_at=now,
        metadata={
            "provider_neutral": "true",
            "read_only": "true",
            "resource_types": resource_types,
            "operation": operation,
            "selector_keys": selector_keys,
            "fact_hints": fact_hints,
            "scope_model": "aot_internal_msp_client_partitioned",
            "client_partition_enforced_by": "validated_dnsfilter_organization_boundary",
            "pilot_gate": "credentials_boundary_and_controlled_read_acceptance",
        },
    )


def dns_protection_capabilities(
    now: datetime,
) -> tuple[CapabilityDefinition, ...]:
    return (
        _read_capability(
            now=now,
            name=DNS_PROTECTION_ORGANIZATION_READ,
            display_name="Read DNS Protection Organization",
            purpose="Read the mapped DNSFilter organization for one AOT client.",
            resource_types="dns_organization,dns_protection_tenant",
            operation="read",
            selector_keys="company_id",
            fact_hints="DNSFilter organization protective DNS client tenant",
        ),
        _read_capability(
            now=now,
            name=DNS_PROTECTION_SITE_SEARCH,
            display_name="Search DNS Protection Sites",
            purpose="Search DNSFilter networks/sites for one mapped AOT client.",
            resource_types="dns_site,dns_network",
            operation="search",
            selector_keys="company_id,protected,unprotected,page_number,page_size",
            fact_hints=(
                "DNSFilter network site protected unprotected IP address "
                "policy assignment local domain resolver"
            ),
        ),
        _read_capability(
            now=now,
            name=DNS_PROTECTION_POLICY_SEARCH,
            display_name="Search DNS Protection Policies",
            purpose="Search DNSFilter policies for one mapped AOT client.",
            resource_types="dns_policy,dns_exception",
            operation="search",
            selector_keys="company_id,include_global_policies,page_number,page_size",
            fact_hints=(
                "DNSFilter policy allowlist denylist category application "
                "safe search exception network assignment"
            ),
        ),
        _read_capability(
            now=now,
            name=DNS_PROTECTION_AGENT_SEARCH,
            display_name="Search DNS Protection Agents",
            purpose=(
                "Search organization-scoped DNSFilter roaming/user agents "
                "for endpoint protection posture."
            ),
            resource_types="dns_agent,dns_roaming_client,endpoint",
            operation="search",
            selector_keys=(
                "company_id,search,state,status,agent_state,network_ids,"
                "policy_id,traffic_received_last_15_mins,page_number,page_size"
            ),
            fact_hints=(
                "DNSFilter agent roaming client protected unprotected bypassed "
                "offline hostname version policy last sync traffic"
            ),
        ),
        _read_capability(
            now=now,
            name=DNS_PROTECTION_AGENT_COUNTS_READ,
            display_name="Read DNS Protection Agent Counts",
            purpose=(
                "Read organization-scoped DNSFilter protection-state counts "
                "for client coverage evidence."
            ),
            resource_types="dns_agent_count,dns_protection_coverage",
            operation="read",
            selector_keys=(
                "company_id,search,state,status,network_ids,new_agent_states"
            ),
            fact_hints=(
                "DNSFilter protected unprotected bypassed offline agent count "
                "coverage protective DNS posture"
            ),
        ),
    )


def dnsfilter_provider(now: datetime, *, enabled: bool) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=DNSFILTER_PROVIDER,
        display_name="DNSFilter Management API",
        provider_type=ProviderType.EXTERNAL_CONNECTOR,
        lifecycle_status=(
            ProviderLifecycle.AVAILABLE if enabled else ProviderLifecycle.PLANNED
        ),
        health_status=(
            ProviderHealth.HEALTHY if enabled else ProviderHealth.UNAVAILABLE
        ),
        approval_status=(
            ProviderApproval.APPROVED if enabled else ProviderApproval.BLOCKED
        ),
        execution_modes=frozenset({"deterministic"}),
        capabilities=frozenset(_DNSFILTER_CAPABILITIES),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=5,
            maximum_requests_per_minute=60,
            maximum_execution_seconds=30,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification=(
                "DNSFilter is AOT's provider-native source for protective DNS "
                "site, policy, and roaming-agent posture evidence."
            ),
            review_interval_days=90,
            last_reviewed_at=now,
            retirement_criteria=(
                "DNSFilter is no longer AOT's approved protective DNS provider.",
                "A replacement satisfies the canonical DNS protection contracts.",
            ),
            vendor_change_sources=("DNSFilter API documentation",),
            operational_owner="AOT Managed Services",
            approval_owner="Jason Architecture Authority",
        ),
        created_at=now,
        metadata={
            "connector_id": DNSFILTER_PROVIDER,
            "resource_authority": "protective_dns",
            "live_enablement": (
                "enabled"
                if enabled
                else "blocked_pending_credentials_boundaries_and_acceptance"
            ),
            "read_only": "true",
        },
    )


def register_dns_protection_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
    enabled: bool,
) -> None:
    for capability in dns_protection_capabilities(now):
        capabilities.register(capability)
    providers.register(dnsfilter_provider(now, enabled=enabled))
