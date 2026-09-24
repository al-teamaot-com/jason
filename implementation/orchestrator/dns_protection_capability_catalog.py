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

DNSFILTER_MCP_PROVIDER = "dnsfilter_mcp"
DNS_INVESTIGATION_QUERY_SEARCH = "dns.investigation.query.search"
DNS_INVESTIGATION_QUERY_EXPLAIN = "dns.investigation.query.explain"
DNS_INVESTIGATION_BLOCKED_TRAFFIC_SEARCH = "dns.investigation.blocked.traffic.search"
DNS_INVESTIGATION_ANOMALY_SEARCH = "dns.investigation.anomaly.search"
DNS_PROTECTION_AGENT_STALE_SEARCH = "dns.protection.agent.stale.search"
DNS_PROTECTION_AGENT_VERSION_REPORT = "dns.protection.agent.version.report"
DNS_PROTECTION_AGENT_DUPLICATE_SEARCH = "dns.protection.agent.duplicate.search"
DNS_PROTECTION_SITE_DRIFT_SEARCH = "dns.protection.site.drift.search"
DNS_PROTECTION_POLICY_CATEGORY_SEARCH = "dns.protection.policy.category.search"
DNS_PROTECTION_UNBLOCK_REQUEST_SEARCH = "dns.protection.unblock.request.search"
DNS_PROTECTION_UNBLOCK_REQUEST_COUNT_READ = "dns.protection.unblock.request.count.read"

_DNSFILTER_CAPABILITIES = (
    DNS_PROTECTION_ORGANIZATION_READ,
    DNS_PROTECTION_SITE_SEARCH,
    DNS_PROTECTION_POLICY_SEARCH,
    DNS_PROTECTION_AGENT_SEARCH,
    DNS_PROTECTION_AGENT_COUNTS_READ,
)

_DNSFILTER_MCP_CAPABILITIES = (
    DNS_INVESTIGATION_QUERY_SEARCH,
    DNS_INVESTIGATION_QUERY_EXPLAIN,
    DNS_INVESTIGATION_BLOCKED_TRAFFIC_SEARCH,
    DNS_INVESTIGATION_ANOMALY_SEARCH,
    DNS_PROTECTION_AGENT_STALE_SEARCH,
    DNS_PROTECTION_AGENT_VERSION_REPORT,
    DNS_PROTECTION_AGENT_DUPLICATE_SEARCH,
    DNS_PROTECTION_SITE_DRIFT_SEARCH,
    DNS_PROTECTION_POLICY_CATEGORY_SEARCH,
    DNS_PROTECTION_UNBLOCK_REQUEST_SEARCH,
    DNS_PROTECTION_UNBLOCK_REQUEST_COUNT_READ,
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
        _read_capability(
            now=now,
            name=DNS_INVESTIGATION_QUERY_SEARCH,
            display_name="Search DNS Query Evidence",
            purpose="Search provider-native DNS query logs for one mapped client.",
            resource_types="dns_query,dns_event,dns_investigation",
            operation="search",
            selector_keys="company_id,from,to,fqdn,domain,agent_id,network_id,user_id,result,page,per_page",
            fact_hints="DNS query log blocked allowed domain device user policy threat forensic",
        ),
        _read_capability(
            now=now,
            name=DNS_INVESTIGATION_QUERY_EXPLAIN,
            display_name="Explain DNS Query Decision",
            purpose="Explain why a recent DNS query was blocked or allowed for one mapped client.",
            resource_types="dns_query,dns_policy_decision",
            operation="read",
            selector_keys="company_id,fqdn,from,to,agent_id,network_id",
            fact_hints="why blocked allowed domain DNSFilter decision policy category threat",
        ),
        _read_capability(
            now=now,
            name=DNS_INVESTIGATION_BLOCKED_TRAFFIC_SEARCH,
            display_name="Search Blocked DNS Traffic",
            purpose="Summarize provider-observed blocked DNS traffic for one mapped client.",
            resource_types="dns_query,dns_blocked_traffic",
            operation="search",
            selector_keys="company_id,from,to,limit",
            fact_hints="top blocked domains categories DNS traffic client",
        ),
        _read_capability(
            now=now,
            name=DNS_INVESTIGATION_ANOMALY_SEARCH,
            display_name="Search DNS Traffic Anomalies",
            purpose="Compare DNS traffic with a prior baseline for one mapped client.",
            resource_types="dns_anomaly,dns_query",
            operation="search",
            selector_keys="company_id,from,to,network_id",
            fact_hints="DNS anomaly spike drop new domain unusual traffic site",
        ),
        _read_capability(
            now=now,
            name=DNS_PROTECTION_AGENT_STALE_SEARCH,
            display_name="Search Stale DNS Protection Agents",
            purpose="Find roaming clients that have not checked in within a bounded threshold.",
            resource_types="dns_agent,endpoint",
            operation="search",
            selector_keys="company_id,days",
            fact_hints="DNSFilter stale agent last sync offline roaming client",
        ),
        _read_capability(
            now=now,
            name=DNS_PROTECTION_AGENT_VERSION_REPORT,
            display_name="Read DNS Protection Agent Version Report",
            purpose="Summarize roaming-client versions and CyberSight install state for one client.",
            resource_types="dns_agent,endpoint,dns_agent_version",
            operation="read",
            selector_keys="company_id,latest_version",
            fact_hints="DNSFilter agent version outdated CyberSight service state",
        ),
        _read_capability(
            now=now,
            name=DNS_PROTECTION_AGENT_DUPLICATE_SEARCH,
            display_name="Search Duplicate DNS Protection Agents",
            purpose="Find likely duplicate roaming-client registrations for one mapped client.",
            resource_types="dns_agent,endpoint",
            operation="search",
            selector_keys="company_id",
            fact_hints="DNSFilter duplicate agent hostname conflicting registration",
        ),
        _read_capability(
            now=now,
            name=DNS_PROTECTION_SITE_DRIFT_SEARCH,
            display_name="Search DNS Site Policy Drift",
            purpose="Find sites not using one expected DNS filtering policy.",
            resource_types="dns_site,dns_policy,dns_configuration_drift",
            operation="search",
            selector_keys="company_id,policy_id",
            fact_hints="DNSFilter site network expected policy drift unassigned",
        ),
        _read_capability(
            now=now,
            name=DNS_PROTECTION_POLICY_CATEGORY_SEARCH,
            display_name="Search DNS Policy Category Coverage",
            purpose="Identify which client policies block or do not block one category.",
            resource_types="dns_policy,dns_category",
            operation="search",
            selector_keys="company_id,category_id,include_global_policies",
            fact_hints="DNSFilter policy category blocking coverage global policy",
        ),
        _read_capability(
            now=now,
            name=DNS_PROTECTION_UNBLOCK_REQUEST_SEARCH,
            display_name="Search DNS Unblock Requests",
            purpose="Search the client's DNSFilter unblock-request queue and history.",
            resource_types="dns_unblock_request,dns_policy_request",
            operation="search",
            selector_keys="company_id,tab,page,per_page,requested_after,requested_before,resolved_after,resolved_before,search,sort,status",
            fact_hints="DNSFilter unblock request pending allow deny domain requester",
        ),
        _read_capability(
            now=now,
            name=DNS_PROTECTION_UNBLOCK_REQUEST_COUNT_READ,
            display_name="Read Pending DNS Unblock Request Count",
            purpose="Read the number of pending DNSFilter unblock requests for one client.",
            resource_types="dns_unblock_request_count",
            operation="read",
            selector_keys="company_id",
            fact_hints="DNSFilter pending unblock requests count queue",
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


def dnsfilter_mcp_provider(now: datetime, *, enabled: bool) -> ExecutionProvider:
    return ExecutionProvider(
        provider_id=DNSFILTER_MCP_PROVIDER,
        display_name="DNSFilter MCP",
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
        capabilities=frozenset(_DNSFILTER_MCP_CAPABILITIES),
        supported_classifications=frozenset({"internal"}),
        regions=frozenset(),
        limits=ProviderLimits(
            maximum_concurrent_executions=4,
            maximum_requests_per_minute=60,
            maximum_execution_seconds=60,
        ),
        features=ProviderFeatures(structured_output=True),
        pricing_profile_id="zero-cost-foundation",
        stewardship=ProviderStewardship(
            technology_steward="technology-steward",
            business_justification=(
                "Use DNSFilter's provider-supported MCP server for DNS investigation "
                "and interactive administrative evidence while retaining Jason governance."
            ),
            review_interval_days=30,
            last_reviewed_at=now,
            retirement_criteria=(
                "DNSFilter MCP is no longer provider-supported.",
                "A replacement satisfies the canonical DNS investigation contracts.",
            ),
            vendor_change_sources=(
                "DNSFilter MCP connector documentation",
                "DNSFilter MCP public tool catalog",
            ),
            operational_owner="AOT Managed Services",
            approval_owner="Jason Architecture Authority",
        ),
        created_at=now,
        metadata={
            "connector_id": DNSFILTER_MCP_PROVIDER,
            "resource_authority": "dns_investigation_and_admin_evidence",
            "live_enablement": (
                "enabled"
                if enabled
                else "blocked_pending_oauth_boundaries_and_acceptance"
            ),
            "read_only": "true",
            "oauth_user_session_required": "true",
            "provider_write_surface_registered": "false",
        },
    )


def register_dns_protection_foundation(
    *,
    capabilities: CapabilityRegistryService,
    providers: ExecutionProviderRegistryService,
    now: datetime,
    enabled: bool,
    mcp_enabled: bool = False,
) -> None:
    for capability in dns_protection_capabilities(now):
        capabilities.register(capability)
    providers.register(dnsfilter_provider(now, enabled=enabled))
    providers.register(dnsfilter_mcp_provider(now, enabled=mcp_enabled))
