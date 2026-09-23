from datetime import datetime, timezone

from kernel.execution_providers import (
    ProviderApproval,
    ProviderHealth,
    ProviderLifecycle,
)
from orchestrator.backup_capability_catalog import (
    BACKUP_BACKUPIQ_ALERT_SEARCH,
    BACKUP_ENDPOINT_ASSET_READ,
    BACKUP_ENDPOINT_ASSET_SEARCH,
    BACKUP_ENDPOINT_BACKUP_SEARCH,
    backup_capabilities,
    backup_net_provider,
)


NOW = datetime(2026, 9, 23, tzinfo=timezone.utc)


def test_backup_capabilities_are_read_only_and_company_partitioned():
    definitions = {item.capability_name: item for item in backup_capabilities(NOW)}
    assert set(definitions) == {
        BACKUP_ENDPOINT_ASSET_SEARCH,
        BACKUP_ENDPOINT_ASSET_READ,
        BACKUP_ENDPOINT_BACKUP_SEARCH,
        BACKUP_BACKUPIQ_ALERT_SEARCH,
    }
    for item in definitions.values():
        assert item.metadata["read_only"] == "true"
        assert item.approval.required is False
        assert item.maximum_attempts == 2
        assert item.tenant_isolation_required is True
        assert item.client_isolation_required is False
        assert item.metadata["client_partition_enforced_by"] == (
            "validated_backup_net_customer_boundary"
        )
        assert "company_id" in item.metadata["selector_keys"]


def test_backup_net_provider_stays_blocked_until_explicit_enablement():
    provider = backup_net_provider(NOW, enabled=False)
    assert provider.lifecycle_status is ProviderLifecycle.PLANNED
    assert provider.health_status is ProviderHealth.UNAVAILABLE
    assert provider.approval_status is ProviderApproval.BLOCKED
    assert provider.metadata["live_enablement"] == (
        "blocked_pending_credentials_and_boundaries"
    )


def test_backup_net_provider_can_be_marked_available_after_acceptance_gate():
    provider = backup_net_provider(NOW, enabled=True)
    assert provider.lifecycle_status is ProviderLifecycle.AVAILABLE
    assert provider.health_status is ProviderHealth.HEALTHY
    assert provider.approval_status is ProviderApproval.APPROVED
    assert provider.metadata["live_enablement"] == "enabled"
