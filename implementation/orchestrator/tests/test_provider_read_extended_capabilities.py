from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from connectors.autotask.capability_manifest import build_autotask_manifest
from connectors.microsoft_graph.capability_manifest import build_microsoft_graph_manifest
from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
)
from orchestrator.integration_broker import IntegrationBroker
from orchestrator.provider_read_argument_adapter import (
    adapt_autotask_arguments,
    adapt_microsoft_graph_arguments,
)
from orchestrator.provider_read_capability_catalog import (
    IDENTITY_USER_READ,
    IDENTITY_USER_SEARCH,
    MICROSOFT_GRAPH_PROVIDER,
    SERVICE_TICKET_COUNT,
    SERVICE_CONTRACT_SEARCH,
    SERVICE_CONTRACT_READ,
    SERVICE_TICKET_ATTACHMENT_SEARCH,
    SERVICE_TICKET_ATTACHMENT_READ,
    SERVICE_TICKET_ATTACHMENT_CONTENT_READ,
    register_provider_read_foundation,
)


NOW = datetime(2026, 9, 14, tzinfo=timezone.utc)


def services():
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
    register_provider_read_foundation(
        capabilities=capabilities,
        providers=providers,
        now=NOW,
    )
    return capabilities, providers


def test_ticket_count_uses_filter_only_autotask_count_contract():
    adapted = adapt_autotask_arguments(
        SERVICE_TICKET_COUNT,
        {"status": "New", "company_id": 77},
    )

    assert json.loads(adapted["search"]) == {
        "filter": [
            {"op": "eq", "field": "companyID", "value": 77},
            {"op": "eq", "field": "status", "value": "New"},
        ]
    }


def test_ticket_count_rejects_continuation_selector():
    with pytest.raises(ValueError, match="after_resource_id"):
        adapt_autotask_arguments(
            SERVICE_TICKET_COUNT,
            {"status": "New", "after_resource_id": 100},
        )


def test_autotask_manifest_exposes_ticket_count_with_status_selector():
    operations = {
        operation.capability_name: operation
        for resource in build_autotask_manifest().resources
        for operation in resource.operations
    }
    count = operations[SERVICE_TICKET_COUNT]
    assert count.read_only is True
    assert "status" in count.selector_names
    assert "page_size" not in count.selector_names


def test_microsoft_user_adapter_requires_one_exact_selector_and_bounds_results():
    assert adapt_microsoft_graph_arguments(
        IDENTITY_USER_SEARCH,
        {"email": "user@example.com", "page_size": 5},
    ) == {"email": "user@example.com", "page_size": 5}

    for arguments in (
        {},
        {"email": "a@example.com", "display_name": "Example"},
        {"email": "a@example.com", "page_size": 26},
    ):
        with pytest.raises(ValueError):
            adapt_microsoft_graph_arguments(IDENTITY_USER_SEARCH, arguments)

    assert adapt_microsoft_graph_arguments(
        IDENTITY_USER_READ,
        {"resource_id": "object-1"},
    ) == {"resource_id": "object-1"}


def test_microsoft_manifest_registers_provider_neutral_user_search_and_read():
    capabilities, providers = services()
    broker = IntegrationBroker(capabilities=capabilities, providers=providers)

    broker.register(build_microsoft_graph_manifest())

    view = broker.get("microsoft_graph_directory")
    assert view.provider_id == MICROSOFT_GRAPH_PROVIDER
    operations = {
        operation.capability_name
        for resource in build_microsoft_graph_manifest().resources
        for operation in resource.operations
    }
    assert {IDENTITY_USER_SEARCH, IDENTITY_USER_READ}.issubset(operations)


def test_autotask_notification_history_requires_company_boundary() -> None:
    from orchestrator.provider_read_argument_adapter import adapt_autotask_arguments
    from orchestrator.provider_read_capability_catalog import SERVICE_NOTIFICATION_HISTORY_SEARCH
    import json
    try:
        adapt_autotask_arguments(SERVICE_NOTIFICATION_HISTORY_SEARCH, {"template_name": "Ticket Created"})
    except ValueError as error:
        assert "company_id is required" in str(error)
    else:
        raise AssertionError("unbounded notification history must fail closed")
    out = adapt_autotask_arguments(SERVICE_NOTIFICATION_HISTORY_SEARCH, {"company_id": 311, "ticket_id": 140654, "template_name": "Ticket Created", "page_size": 25})
    query=json.loads(out["search"]); fields={x["field"]:x["value"] for x in query["filter"]}
    assert fields == {"companyID":311,"ticketID":140654,"templateName":"Ticket Created"}
    assert query["MaxRecords"] == 25


def test_contract_search_requires_exact_company_boundary_and_bounds_continuation():
    with pytest.raises(ValueError, match="company_id is required"):
        adapt_autotask_arguments(SERVICE_CONTRACT_SEARCH, {"status": 1})

    adapted = adapt_autotask_arguments(
        SERVICE_CONTRACT_SEARCH,
        {
            "company_id": 333,
            "status": 1,
            "contract_type": 7,
            "page_size": 25,
            "after_resource_id": 1000,
        },
    )
    assert adapted["entity"] == "Contracts"
    query = json.loads(adapted["search"])
    assert query["MaxRecords"] == 25
    fields = {(x["field"], x["op"]): x["value"] for x in query["filter"]}
    assert fields[("companyID", "eq")] == 333
    assert fields[("status", "eq")] == 1
    assert fields[("contractType", "eq")] == 7
    assert fields[("id", "gt")] == 1000


def test_contract_read_requires_company_and_exact_id_in_same_query():
    for args in ({"resource_id": 44}, {"company_id": 333}):
        with pytest.raises(ValueError):
            adapt_autotask_arguments(SERVICE_CONTRACT_READ, args)

    adapted = adapt_autotask_arguments(
        SERVICE_CONTRACT_READ,
        {"company_id": 333, "resource_id": 44},
    )
    assert adapted["entity"] == "Contracts"
    query = json.loads(adapted["search"])
    fields = {x["field"]: x["value"] for x in query["filter"]}
    assert fields == {"companyID": 333, "id": 44}


def test_contract_reads_reject_raw_provider_search_expressions():
    with pytest.raises(ValueError, match="provider-specific"):
        adapt_autotask_arguments(
            SERVICE_CONTRACT_SEARCH,
            {"company_id": 333, "search": '{"filter":[]}'},
        )


def test_autotask_manifest_exposes_company_bound_contract_reads():
    operations = {
        operation.capability_name: operation
        for resource in build_autotask_manifest().resources
        for operation in resource.operations
    }
    assert operations[SERVICE_CONTRACT_SEARCH].read_only is True
    assert "company_id" in operations[SERVICE_CONTRACT_SEARCH].selector_names
    assert operations[SERVICE_CONTRACT_READ].selector_names == ("company_id", "resource_id")


def test_contract_client_selector_binding_rejects_cross_client_before_delegate():
    from orchestrator.provider_read_argument_adapter import GovernedProviderReadConnectorInvoker
    from orchestrator.contracts import OrchestrationRequest, OrchestrationMode
    from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
    from decimal import Decimal

    class Delegate:
        called = False
        def invoke(self, **kwargs):
            self.called = True
            raise AssertionError("provider delegate must not be called")

    req = OrchestrationRequest(
        execution_id="e", correlation_id="c", principal_id="p", organization_id="aot",
        client_id="333", capability_name=SERVICE_CONTRACT_SEARCH, capability_version="1.0",
        requested_mode="deterministic", orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=True, approval_present=False, risk="low",
        data_handling=DataHandlingPolicy(classification="internal", hosted_processing_allowed=False),
        budget=ExecutionBudget(maximum_estimated_cost=Decimal("0"), maximum_attempts=1),
        arguments={"company_id": 311}, authority_context_id="ctx",
    )
    resolution = type("R", (), {"selected_provider_id":"autotask", "capability_name":SERVICE_CONTRACT_SEARCH})()
    delegate=Delegate(); invoker=GovernedProviderReadConnectorInvoker(delegate=delegate)
    with pytest.raises(PermissionError, match="does not match governed client context"):
        invoker.invoke(request=req, resolution=resolution)
    assert delegate.called is False


def test_contract_client_selector_binding_allows_matching_client():
    from orchestrator.provider_read_argument_adapter import GovernedProviderReadConnectorInvoker
    from orchestrator.contracts import OrchestrationRequest, OrchestrationMode
    from orchestrator.service import InvocationResult
    from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
    from decimal import Decimal

    class Delegate:
        called = False
        def invoke(self, *, request, resolution):
            self.called = True
            assert request.arguments["entity"] == "Contracts"
            return InvocationResult(output={"provider":"autotask","provider_capability":"autotask.entity.query","data":{"items":[]}})

    req = OrchestrationRequest(
        execution_id="e", correlation_id="c", principal_id="p", organization_id="aot",
        client_id="333", capability_name=SERVICE_CONTRACT_SEARCH, capability_version="1.0",
        requested_mode="deterministic", orchestration_mode=OrchestrationMode.EXECUTE,
        authority_allowed=True, approval_present=False, risk="low",
        data_handling=DataHandlingPolicy(classification="internal", hosted_processing_allowed=False),
        budget=ExecutionBudget(maximum_estimated_cost=Decimal("0"), maximum_attempts=1),
        arguments={"company_id": 333, "page_size": 10}, authority_context_id="ctx",
    )
    resolution = type("R", (), {"selected_provider_id":"autotask", "capability_name":SERVICE_CONTRACT_SEARCH})()
    delegate=Delegate(); invoker=GovernedProviderReadConnectorInvoker(delegate=delegate)
    invoker.invoke(request=req, resolution=resolution)
    assert delegate.called is True


def test_ticket_attachment_read_arguments_are_company_and_ticket_bound():
    from orchestrator.provider_read_argument_adapter import adapt_autotask_arguments
    search=adapt_autotask_arguments(
        SERVICE_TICKET_ATTACHMENT_SEARCH,{"company_id":333,"ticket_id":140000}
    )
    assert search == {"company_id":333,"ticket_id":140000}
    read=adapt_autotask_arguments(
        SERVICE_TICKET_ATTACHMENT_READ,{"company_id":333,"ticket_id":140000,"resource_id":555}
    )
    assert read == {"company_id":333,"ticket_id":140000,"attachment_id":555}
    content=adapt_autotask_arguments(
        SERVICE_TICKET_ATTACHMENT_CONTENT_READ,{"company_id":333,"ticket_id":140000,"resource_id":555,"max_bytes":1234}
    )
    assert content["max_bytes"] == 1234
    with pytest.raises(ValueError):
        adapt_autotask_arguments(SERVICE_TICKET_ATTACHMENT_SEARCH,{"ticket_id":140000})
