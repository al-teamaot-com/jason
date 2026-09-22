from __future__ import annotations

from datetime import datetime, timezone

from connectors.datto_rmm.capability_manifest import build_datto_rmm_manifest
from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_providers import ExecutionProviderRegistryService, InMemoryExecutionProviderRegistry
from orchestrator.resource_capability_catalog import (
    DATTO_RMM_PROVIDER,
    ENDPOINT_PATCH_SEARCH,
    register_endpoint_resource_foundation,
)


NOW = datetime(2026, 9, 22, tzinfo=timezone.utc)


def _services():
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
    register_endpoint_resource_foundation(
        capabilities=capabilities,
        providers=providers,
        now=NOW,
    )
    return capabilities, providers


def test_endpoint_patch_capability_is_active_read_only_and_provider_bound() -> None:
    capabilities, providers = _services()
    definition = capabilities.get_current(capability_name=ENDPOINT_PATCH_SEARCH)
    provider = providers.get(DATTO_RMM_PROVIDER)

    assert definition.metadata["read_only"] == "true"
    assert definition.metadata["operation"] == "search"
    assert "kb" in definition.metadata["selector_keys"].split(",")
    assert "exact patch approval state" in definition.metadata["canonical_facts"]
    assert ENDPOINT_PATCH_SEARCH in provider.capabilities


def test_datto_manifest_exposes_endpoint_patch_search() -> None:
    operations = {
        operation.capability_name: operation
        for resource in build_datto_rmm_manifest().resources
        for operation in resource.operations
    }

    patch = operations[ENDPOINT_PATCH_SEARCH]
    assert patch.read_only is True
    assert set(patch.selector_names) == {
        "resource_id",
        "kb",
        "patch_identity",
        "install_status",
    }
