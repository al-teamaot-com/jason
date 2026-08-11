from __future__ import annotations

from datetime import datetime, timezone

from connectors.datto_rmm.connector import DattoRmmConnector
from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
)
from orchestrator.resource_capability_catalog import (
    DATTO_RMM_PROVIDER,
    ENDPOINT_DEVICE_READ,
    ENDPOINT_DEVICE_SEARCH,
    register_endpoint_resource_foundation,
)
from orchestrator.resource_inquiry import GovernedResourceInquiryPlanner, ResourceInquiry
from orchestrator.resource_reasoner import MetadataResourceCapabilityReasoner


NOW = datetime(2026, 8, 10, tzinfo=timezone.utc)


def services():
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
    register_endpoint_resource_foundation(
        capabilities=capabilities,
        providers=providers,
        now=NOW,
    )
    return capabilities, providers


def test_bootstrap_registers_broad_provider_neutral_endpoint_reads():
    capabilities, providers = services()

    search = capabilities.get_current(capability_name=ENDPOINT_DEVICE_SEARCH)
    read = capabilities.get_current(capability_name=ENDPOINT_DEVICE_READ)
    datto = providers.get(DATTO_RMM_PROVIDER)

    assert search.metadata["provider_neutral"] == "true"
    assert search.metadata["read_only"] == "true"
    assert search.permitted_execution_modes == frozenset({"deterministic"})
    assert read.metadata["operation"] == "read"
    assert datto.capabilities == frozenset({ENDPOINT_DEVICE_SEARCH, ENDPOINT_DEVICE_READ})
    assert datto.execution_modes == frozenset({"deterministic"})


def test_reasoner_selects_search_for_hostname_without_field_specific_script():
    capabilities, _ = services()
    planner = GovernedResourceInquiryPlanner(
        registry=capabilities,
        reasoner=MetadataResourceCapabilityReasoner(),
    )

    plan = planner.plan(
        ResourceInquiry(
            resource_type="endpoint",
            resource_selector={"hostname": "AOT-50282"},
            requested_facts=("last logged in user",),
        )
    )

    assert len(plan.steps) == 1
    assert plan.steps[0].capability_name == ENDPOINT_DEVICE_SEARCH
    assert plan.steps[0].arguments == {
        "hostname": "AOT-50282",
        "requested_facts": ("last logged in user",),
    }


def test_reasoner_selects_direct_read_when_resource_id_is_known():
    capabilities, _ = services()
    planner = GovernedResourceInquiryPlanner(
        registry=capabilities,
        reasoner=MetadataResourceCapabilityReasoner(),
    )

    plan = planner.plan(
        ResourceInquiry(
            resource_type="endpoint",
            resource_selector={"resource_id": "device-uid-1"},
            requested_facts=("operating system",),
        )
    )

    assert plan.steps[0].capability_name == ENDPOINT_DEVICE_READ


def test_datto_connector_translates_provider_neutral_hostname_selector_to_search():
    path, params = DattoRmmConnector._resolve_operation(
        "datto_rmm.device.search",
        {"hostname": "AOT-50282", "requested_facts": ("last logged in user",)},
    )

    assert path == "/api/v2/account/devices"
    assert params is not None
    assert params["hostname"] == "AOT-50282"
    assert "search" not in params


def test_datto_connector_translates_provider_neutral_resource_id_to_get():
    path, params = DattoRmmConnector._resolve_operation(
        "datto_rmm.device.get",
        {"resource_id": "device-uid-1"},
    )

    assert path == "/api/v2/device/device-uid-1"
    assert params is None
