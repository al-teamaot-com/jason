from datetime import datetime, timezone
from types import SimpleNamespace

from connectors.core.connector_base import PreparedRequest
from connectors.core.contracts import ConnectorContext, ConnectorRequest
from kernel.capabilities import CapabilityLifecycle, CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_providers import ExecutionProviderRegistryService, InMemoryExecutionProviderRegistry
from jason_runtime.autotask_procurement import (
    AUTOTASK_PROCUREMENT_PROFILE_ENV,
    AUTOTASK_PROCUREMENT_PROVIDER,
    PROCUREMENT_CAPABILITIES,
    PROVIDER_MAP,
    PROVIDER_ENTITY,
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



class BindingResolver:
    def __init__(self, binding):
        self.binding = binding
        self.calls = []

    def find_active_by_jason_identity(self, *, jason_identity_id):
        self.calls.append(jason_identity_id)
        return self.binding


def procurement_connector_request(*, microsoft_object_id):
    return ConnectorRequest(
        context=ConnectorContext(
            correlation_id="corr-procurement",
            principal_id="jason-procurement-worker",
            organization_id="aot",
            client_id=None,
            capability="autotask.vendor.create",
            mode="execute",
            policy_ids=("aot-procurement-delegated-spend-v1",),
            principal_attributes={
                "workload": "jason-procurement-worker",
                "procurement_submission_id": "procsub-1",
                "procurement_digest": "digest-1",
                "submitted_by": "person-al",
                "submitted_email": "al@teamaot.com",
                "submitted_microsoft_object_id": microsoft_object_id,
            },
        ),
        arguments={"payload": {"companyName": "Synthetic Vendor"}},
    )



def test_procurement_worker_uses_bound_submitter_for_autotask_impersonation():
    binding = SimpleNamespace(
        microsoft_object_id="bee80bdc-ffb0-4c50-b453-c09d4d411f5f",
        email_address=None,
    )
    resolver = BindingResolver(binding)
    connector = object.__new__(AutotaskProductionProcurementConnector)
    connector._bindings = resolver

    email = connector._trusted_email(
        procurement_connector_request(
            microsoft_object_id="bee80bdc-ffb0-4c50-b453-c09d4d411f5f"
        )
    )

    assert email == "al@teamaot.com"
    assert resolver.calls == ["person-al"]


def test_procurement_worker_rejects_submitter_object_id_mismatch():
    binding = SimpleNamespace(
        microsoft_object_id="bee80bdc-ffb0-4c50-b453-c09d4d411f5f",
        email_address=None,
    )
    resolver = BindingResolver(binding)
    connector = object.__new__(AutotaskProductionProcurementConnector)
    connector._bindings = resolver

    email = connector._trusted_email(
        procurement_connector_request(
            microsoft_object_id="00000000-0000-4000-8000-000000000001"
        )
    )

    assert email is None
    assert resolver.calls == ["person-al"]


def test_procurement_runtime_registers_every_flow_mutation() -> None:
    from orchestrator.provider_mutation_capability_catalog import (
        SERVICE_VENDOR_CREATE,
        SERVICE_PRODUCT_CREATE,
        SERVICE_PRODUCT_VENDOR_CREATE,
        SERVICE_OPPORTUNITY_CREATE,
        SERVICE_QUOTE_LOCATION_CREATE,
        SERVICE_QUOTE_CREATE,
        SERVICE_QUOTE_ITEM_CREATE,
        SERVICE_PURCHASE_ORDER_CREATE,
        SERVICE_PURCHASE_ORDER_ITEM_CREATE,
        SERVICE_PURCHASE_ORDER_UPDATE,
        SERVICE_TICKET_CHARGE_CREATE,
    )

    required = {
        SERVICE_VENDOR_CREATE: ("autotask.vendor.create", "Companies"),
        SERVICE_PRODUCT_CREATE: ("autotask.product.create", "Products"),
        SERVICE_PRODUCT_VENDOR_CREATE: ("autotask.product.vendor.create", "ProductVendors"),
        SERVICE_OPPORTUNITY_CREATE: ("autotask.opportunity.create", "Opportunities"),
        SERVICE_QUOTE_LOCATION_CREATE: ("autotask.quote.location.create", "QuoteLocations"),
        SERVICE_QUOTE_CREATE: ("autotask.quote.create", "Quotes"),
        SERVICE_QUOTE_ITEM_CREATE: ("autotask.quote.item.create", "QuoteItems"),
        SERVICE_PURCHASE_ORDER_CREATE: ("autotask.purchase.order.create", "PurchaseOrders"),
        SERVICE_PURCHASE_ORDER_ITEM_CREATE: ("autotask.purchase.order.item.create", "PurchaseOrderItems"),
        SERVICE_PURCHASE_ORDER_UPDATE: ("autotask.purchase.order.update", "PurchaseOrders"),
        SERVICE_TICKET_CHARGE_CREATE: ("autotask.ticket.charge.create", "TicketCharges"),
    }
    for capability, (provider_capability, entity) in required.items():
        assert capability in PROCUREMENT_CAPABILITIES
        assert PROVIDER_MAP[(AUTOTASK_PROCUREMENT_PROVIDER, capability)] == provider_capability
        assert PROVIDER_ENTITY[provider_capability] == entity
