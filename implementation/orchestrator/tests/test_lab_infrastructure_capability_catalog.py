from __future__ import annotations

from datetime import datetime, timezone

from kernel.capabilities import CapabilityLifecycle
from kernel.execution_providers import (
    ProviderApproval,
    ProviderHealth,
    ProviderLifecycle,
)
from orchestrator.lab_infrastructure_capability_catalog import (
    LAB_CAPABILITIES,
    LAB_HOST_READ,
    LAB_VM_CREATE,
    lab_capabilities,
    libvirt_lab_provider,
)


NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)


def test_lab_capabilities_are_building_until_live_acceptance() -> None:
    capabilities = lab_capabilities(NOW)

    assert {item.capability_name for item in capabilities} == set(LAB_CAPABILITIES)
    assert all(
        item.lifecycle_status is CapabilityLifecycle.BUILDING
        for item in capabilities
    )


def test_reads_do_not_require_approval_but_mutations_do() -> None:
    by_name = {
        item.capability_name: item
        for item in lab_capabilities(NOW)
    }

    assert by_name[LAB_HOST_READ].approval.required is False
    assert by_name[LAB_VM_CREATE].approval.required is True
    assert by_name[LAB_VM_CREATE].approval.approver_classes == ("owner",)


def test_provider_is_blocked_until_real_host_acceptance() -> None:
    provider = libvirt_lab_provider(NOW, ready=False)

    assert provider.lifecycle_status is ProviderLifecycle.PLANNED
    assert provider.health_status is ProviderHealth.UNAVAILABLE
    assert provider.approval_status is ProviderApproval.BLOCKED
    assert provider.metadata["activation_gate"] == (
        "real_windows_11_acceptance_required"
    )


def test_ready_provider_is_pilot_not_production_authority() -> None:
    provider = libvirt_lab_provider(NOW, ready=True)

    assert provider.lifecycle_status is ProviderLifecycle.AVAILABLE
    assert provider.approval_status is ProviderApproval.PILOT
    assert provider.metadata["production_authority"] == "none"
