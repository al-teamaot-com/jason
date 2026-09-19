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
    assert operations == {IDENTITY_USER_SEARCH, IDENTITY_USER_READ}


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
