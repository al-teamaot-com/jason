from datetime import datetime, timezone

from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
    ProviderCandidateQuery,
)
from orchestrator.resource_capability_bootstrap import (
    DATTO_RMM_ENDPOINT_PROVIDER,
    ENDPOINT_DEVICE_SEARCH,
    register_endpoint_resource_foundation,
)


NOW = datetime(2026, 8, 10, tzinfo=timezone.utc)


def services():
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
    return capabilities, providers


def test_bootstrap_registers_provider_neutral_endpoint_capability():
    capabilities, providers = services()
    register_endpoint_resource_foundation(
        capabilities=capabilities,
        providers=providers,
        created_at=NOW,
    )

    capability = capabilities.get_current(capability_name=ENDPOINT_DEVICE_SEARCH)
    assert capability.metadata["provider_neutral"] == "true"
    assert capability.metadata["resource_types"] == "endpoint"
    assert "observe" in capability.permitted_execution_modes
    assert "datto" not in capability.capability_name


def test_bootstrap_routes_endpoint_search_to_governed_datto_provider():
    capabilities, providers = services()
    register_endpoint_resource_foundation(
        capabilities=capabilities,
        providers=providers,
        created_at=NOW,
    )

    candidates = providers.find_candidates(
        ProviderCandidateQuery(
            capability=ENDPOINT_DEVICE_SEARCH,
            execution_mode="observe",
            classification="internal",
        )
    )

    assert [candidate.provider_id for candidate in candidates] == [DATTO_RMM_ENDPOINT_PROVIDER]
    assert candidates[0].metadata["connector"] == "datto_rmm"
    assert candidates[0].metadata["connector_capability"] == "datto_rmm.device.search"


def test_provider_mapping_is_metadata_not_a_new_human_facing_capability():
    capabilities, providers = services()
    register_endpoint_resource_foundation(
        capabilities=capabilities,
        providers=providers,
        created_at=NOW,
    )

    names = {capability.capability_name for capability in capabilities.list_all()}
    assert names == {ENDPOINT_DEVICE_SEARCH}
    assert all(not name.startswith("datto_rmm.") for name in names)
