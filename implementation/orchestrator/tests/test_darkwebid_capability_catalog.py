from datetime import datetime, timezone

from kernel.execution_providers import ProviderApproval, ProviderHealth, ProviderLifecycle
from orchestrator.darkwebid_capability_catalog import (
    CREDENTIAL_EXPOSURE_ORGANIZATION_READ,
    CREDENTIAL_EXPOSURE_ORGANIZATION_SEARCH,
    darkwebid_capabilities,
    darkwebid_provider,
)

NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)


def test_darkwebid_capabilities_are_read_only_and_aot_internal():
    definitions = {item.capability_name: item for item in darkwebid_capabilities(NOW)}
    assert set(definitions) == {
        CREDENTIAL_EXPOSURE_ORGANIZATION_SEARCH,
        CREDENTIAL_EXPOSURE_ORGANIZATION_READ,
    }
    for item in definitions.values():
        assert item.metadata["read_only"] == "true"
        assert item.approval.required is False
        assert item.tenant_isolation_required is True
        assert item.client_isolation_required is False
        assert item.metadata["scope_model"] == "aot_internal_msp_organization_inventory"


def test_darkwebid_provider_is_blocked_until_explicit_enablement():
    provider = darkwebid_provider(NOW, enabled=False)
    assert provider.lifecycle_status is ProviderLifecycle.PLANNED
    assert provider.health_status is ProviderHealth.UNAVAILABLE
    assert provider.approval_status is ProviderApproval.BLOCKED
    assert provider.metadata["live_enablement"] == "blocked_pending_activation"


def test_darkwebid_provider_can_be_enabled_after_acceptance():
    provider = darkwebid_provider(NOW, enabled=True)
    assert provider.lifecycle_status is ProviderLifecycle.AVAILABLE
    assert provider.health_status is ProviderHealth.HEALTHY
    assert provider.approval_status is ProviderApproval.APPROVED
    assert provider.metadata["live_enablement"] == "enabled"
