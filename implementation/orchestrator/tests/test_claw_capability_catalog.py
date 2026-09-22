from datetime import datetime, timezone

from kernel.capabilities import CapabilityLifecycle
from kernel.execution_providers import ProviderLifecycle
from orchestrator.claw_capability_catalog import (
    CLAW_PROVIDER,
    OPERATIONS_TASK_REQUEST_CREATE,
    claw_capabilities,
    claw_provider,
)


def test_claw_reads_are_active_and_task_write_is_staged():
    now = datetime.now(timezone.utc)
    capabilities = {item.capability_name: item for item in claw_capabilities(now)}
    assert capabilities[OPERATIONS_TASK_REQUEST_CREATE].lifecycle_status is CapabilityLifecycle.BUILDING
    assert capabilities[OPERATIONS_TASK_REQUEST_CREATE].metadata["mcp_action_enabled"] == "false"
    reads = [
        item
        for item in capabilities.values()
        if item.capability_name != OPERATIONS_TASK_REQUEST_CREATE
    ]
    assert reads
    assert all(item.lifecycle_status is CapabilityLifecycle.ACTIVE for item in reads)
    assert all(item.metadata["provider_neutral"] == "true" for item in reads)
    assert all(item.metadata["read_only"] == "true" for item in reads)


def test_claw_provider_identity_is_distinct_from_openclaw():
    provider = claw_provider(datetime.now(timezone.utc), enabled=True)
    assert provider.provider_id == CLAW_PROVIDER == "claw"
    assert provider.display_name == "Claw"
    assert provider.lifecycle_status is ProviderLifecycle.AVAILABLE
    assert provider.metadata["source_identity"] == "external_claw"
