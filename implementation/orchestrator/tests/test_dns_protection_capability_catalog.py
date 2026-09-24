from datetime import datetime, timezone

from kernel.capabilities import CapabilityLifecycle
from kernel.execution_providers import ProviderApproval, ProviderHealth, ProviderLifecycle
from orchestrator.dns_protection_capability_catalog import (
    DNS_INVESTIGATION_ANOMALY_SEARCH,
    DNS_INVESTIGATION_BLOCKED_TRAFFIC_SEARCH,
    DNS_INVESTIGATION_QUERY_EXPLAIN,
    DNS_INVESTIGATION_QUERY_SEARCH,
    DNS_PROTECTION_AGENT_COUNTS_READ,
    DNS_PROTECTION_AGENT_DUPLICATE_SEARCH,
    DNS_PROTECTION_AGENT_SEARCH,
    DNS_PROTECTION_AGENT_STALE_SEARCH,
    DNS_PROTECTION_AGENT_VERSION_REPORT,
    DNS_PROTECTION_ORGANIZATION_READ,
    DNS_PROTECTION_POLICY_CATEGORY_SEARCH,
    DNS_PROTECTION_POLICY_SEARCH,
    DNS_PROTECTION_SITE_DRIFT_SEARCH,
    DNS_PROTECTION_SITE_SEARCH,
    DNS_PROTECTION_UNBLOCK_REQUEST_COUNT_READ,
    DNS_PROTECTION_UNBLOCK_REQUEST_SEARCH,
    dns_protection_capabilities,
    dnsfilter_mcp_provider,
    dnsfilter_provider,
)

NOW = datetime(2026, 9, 24, tzinfo=timezone.utc)


def test_dnsfilter_capabilities_are_read_only_active_and_company_partitioned():
    definitions = {item.capability_name: item for item in dns_protection_capabilities(NOW)}
    assert set(definitions) == {
        DNS_PROTECTION_ORGANIZATION_READ,
        DNS_PROTECTION_SITE_SEARCH,
        DNS_PROTECTION_POLICY_SEARCH,
        DNS_PROTECTION_AGENT_SEARCH,
        DNS_PROTECTION_AGENT_COUNTS_READ,
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
    }
    for item in definitions.values():
        assert item.lifecycle_status is CapabilityLifecycle.ACTIVE
        assert item.metadata["read_only"] == "true"
        assert item.approval.required is False
        assert item.metadata["client_partition_enforced_by"] == (
            "validated_dnsfilter_organization_boundary"
        )
        assert "company_id" in item.metadata["selector_keys"]


def test_dnsfilter_provider_is_blocked_until_explicit_enablement():
    provider = dnsfilter_provider(NOW, enabled=False)
    assert provider.lifecycle_status is ProviderLifecycle.PLANNED
    assert provider.health_status is ProviderHealth.UNAVAILABLE
    assert provider.approval_status is ProviderApproval.BLOCKED


def test_dnsfilter_provider_can_be_available_after_activation_gate():
    provider = dnsfilter_provider(NOW, enabled=True)
    assert provider.lifecycle_status is ProviderLifecycle.AVAILABLE
    assert provider.health_status is ProviderHealth.HEALTHY
    assert provider.approval_status is ProviderApproval.APPROVED
    assert provider.metadata["live_enablement"] == "enabled"


def test_dnsfilter_mcp_provider_is_separately_gated():
    provider = dnsfilter_mcp_provider(NOW, enabled=False)
    assert provider.lifecycle_status is ProviderLifecycle.PLANNED
    assert provider.health_status is ProviderHealth.UNAVAILABLE
    assert provider.approval_status is ProviderApproval.BLOCKED
    assert provider.metadata["oauth_user_session_required"] == "true"
    assert provider.metadata["provider_write_surface_registered"] == "false"


def test_dnsfilter_mcp_provider_can_be_available_after_oauth_acceptance():
    provider = dnsfilter_mcp_provider(NOW, enabled=True)
    assert provider.lifecycle_status is ProviderLifecycle.AVAILABLE
    assert provider.health_status is ProviderHealth.HEALTHY
    assert provider.approval_status is ProviderApproval.APPROVED
    assert provider.metadata["live_enablement"] == "enabled"
