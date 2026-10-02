from datetime import datetime, timezone

from connectors.core.connector_base import PreparedRequest
from kernel.capabilities import CapabilityLifecycle, CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_providers import ExecutionProviderRegistryService, InMemoryExecutionProviderRegistry
from jason_runtime.autotask_procurement import (
    AUTOTASK_PROCUREMENT_PROFILE_ENV,
    AUTOTASK_PROCUREMENT_PROVIDER,
    PROCUREMENT_CAPABILITIES,
    AutotaskProductionProcurementConnector,
    register_autotask_procurement_runtime_foundation,
)


def test_procurement_profile_activates_exact_governed_surface(monkeypatch) -> None:
    monkeypatch.setenv("JASON_AUTOTASK_MUTATION_ENABLED", "true")
    monkeypatch.setenv(AUTOTASK_PROCUREMENT_PROFILE_ENV, "owner-procurement-v1")
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())

    state = register_autotask_procurement_runtime_foundation(
        capabilities=capabilities,
        providers=providers,
        now=datetime.now(timezone.utc),
    )
    assert state.enabled is True
    assert set(state.capability_names) == set(PROCUREMENT_CAPABILITIES)
    provider = providers.get(AUTOTASK_PROCUREMENT_PROVIDER)
    assert set(provider.capabilities) == set(PROCUREMENT_CAPABILITIES)
    for name in PROCUREMENT_CAPABILITIES:
        definition = capabilities.get(capability_name=name, version="1.0")
        assert definition.lifecycle_status is CapabilityLifecycle.ACTIVE
        assert definition.metadata["mcp_action_enabled"] == "true"
        assert definition.approval.required is True


def test_procurement_profile_is_dormant_when_unset(monkeypatch) -> None:
    monkeypatch.delenv(AUTOTASK_PROCUREMENT_PROFILE_ENV, raising=False)
    monkeypatch.setenv("JASON_AUTOTASK_MUTATION_ENABLED", "true")
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())

    state = register_autotask_procurement_runtime_foundation(
        capabilities=capabilities,
        providers=providers,
        now=datetime.now(timezone.utc),
    )
    assert state.enabled is False
    for name in PROCUREMENT_CAPABILITIES:
        definition = capabilities.get(capability_name=name, version="1.0")
        assert definition.lifecycle_status is CapabilityLifecycle.BUILDING


def test_procurement_readback_reuses_authorized_write_headers() -> None:
    class Transport:
        def __init__(self):
            self.calls = []

        def request(self, **kwargs):
            self.calls.append(kwargs)
            return {"item": {"id": 136, "vendorID": 528}}

    connector = object.__new__(AutotaskProductionProcurementConnector)
    transport = Transport()
    connector._transport = transport
    prepared = PreparedRequest(
        method="POST",
        url="https://webservices.example/ATServicesRest/V1.0/Products/29686513/Vendors",
        headers={"ApiIntegrationCode": "redacted", "UserName": "redacted"},
        json={"productID": 29686513, "vendorID": 528},
        timeout_seconds=30.0,
    )

    observed = connector._readback(prepared, "ProductVendors", 136)

    assert observed == {"id": 136, "vendorID": 528}
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["method"] == "GET"
    assert call["url"] == "https://webservices.example/ATServicesRest/V1.0/ProductVendors/136"
    assert call["headers"] is prepared.headers
    assert call["params"] is None
    assert call["json"] is None
