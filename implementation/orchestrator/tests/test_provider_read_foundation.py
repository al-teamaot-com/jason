from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from connectors.autotask.capability_manifest import build_autotask_manifest
from connectors.it_glue.capability_manifest import build_it_glue_manifest
from kernel.capabilities import CapabilityLifecycle, CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
    ProviderApproval,
    ProviderCandidateQuery,
    ProviderHealth,
    ProviderLifecycle,
)
from orchestrator.integration_broker import IntegrationBroker
from orchestrator.provider_read_argument_adapter import (
    adapt_autotask_arguments,
    adapt_it_glue_arguments,
)
from orchestrator.provider_read_capability_catalog import (
    AUTOTASK_PROVIDER,
    DOCUMENTATION_CONFIGURATION_SEARCH,
    DOCUMENTATION_CONTACT_READ,
    DOCUMENTATION_ORGANIZATION_SEARCH,
    IT_GLUE_PROVIDER,
    SERVICE_COMPANY_SEARCH,
    SERVICE_CONTACT_SEARCH,
    SERVICE_ENTITY_DESCRIBE,
    SERVICE_TICKET_NOTES_SEARCH,
    SERVICE_TICKET_READ,
    SERVICE_TICKET_SEARCH,
    register_provider_read_foundation,
)


NOW = datetime(2026, 9, 9, tzinfo=timezone.utc)


def _services():
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
    register_provider_read_foundation(
        capabilities=capabilities,
        providers=providers,
        now=NOW,
    )
    return capabilities, providers


def _manifest_operation_selectors(manifest) -> dict[str, set[str]]:
    return {
        operation.capability_name: set(operation.selector_names)
        for resource in manifest.resources
        for operation in resource.operations
    }


def test_provider_read_foundation_is_read_only_pilot_until_live_acceptance() -> None:
    capabilities, providers = _services()

    organization = capabilities.get_current(
        capability_name=DOCUMENTATION_ORGANIZATION_SEARCH,
        allow_pilot=True,
    )
    ticket = capabilities.get_current(
        capability_name=SERVICE_TICKET_SEARCH,
        allow_pilot=True,
    )
    itg = providers.get(IT_GLUE_PROVIDER)
    autotask = providers.get(AUTOTASK_PROVIDER)

    assert organization.lifecycle_status is CapabilityLifecycle.PILOT
    assert ticket.lifecycle_status is CapabilityLifecycle.PILOT
    assert organization.metadata["read_only"] == "true"
    assert ticket.metadata["read_only"] == "true"
    assert itg.lifecycle_status is ProviderLifecycle.PLANNED
    assert autotask.lifecycle_status is ProviderLifecycle.PLANNED
    assert itg.approval_status is ProviderApproval.PILOT
    assert autotask.approval_status is ProviderApproval.PILOT
    assert itg.health_status is ProviderHealth.UNKNOWN
    assert autotask.health_status is ProviderHealth.UNKNOWN
    assert itg.metadata["activation_state"] == "awaiting_provider_backed_acceptance"
    assert autotask.metadata["activation_state"] == "awaiting_provider_backed_acceptance"


def test_planned_provider_reads_cannot_be_selected_even_when_pilot_is_allowed() -> None:
    _, providers = _services()

    for capability in (
        DOCUMENTATION_ORGANIZATION_SEARCH,
        SERVICE_TICKET_SEARCH,
    ):
        candidates = providers.find_candidates(
            ProviderCandidateQuery(
                capability=capability,
                execution_mode="deterministic",
                classification="internal",
                include_warning=True,
                allow_pilot=True,
            )
        )
        assert candidates == ()


def test_integration_broker_accepts_it_glue_and_autotask_manifests() -> None:
    capabilities, providers = _services()
    broker = IntegrationBroker(capabilities=capabilities, providers=providers)

    broker.register(build_it_glue_manifest())
    broker.register(build_autotask_manifest())

    assert {item.integration_id for item in broker.list_integrations()} == {
        "autotask",
        "it_glue",
    }
    assert not broker.get("it_glue").operational
    assert not broker.get("autotask").operational


def test_search_discovery_metadata_matches_manifest_selectors() -> None:
    capabilities, _ = _services()
    manifests = (build_it_glue_manifest(), build_autotask_manifest())

    for manifest in manifests:
        operation_selectors = _manifest_operation_selectors(manifest)
        for capability_name, manifest_selectors in operation_selectors.items():
            if not capability_name.endswith(".search"):
                continue
            capability = capabilities.get_current(
                capability_name=capability_name,
                allow_pilot=True,
            )
            discovered = {
                item.strip()
                for item in capability.metadata["selector_keys"].split(",")
                if item.strip()
            }
            assert discovered == manifest_selectors


def test_it_glue_adapter_injects_only_approved_noncredential_entity_families() -> None:
    organization = adapt_it_glue_arguments(
        DOCUMENTATION_ORGANIZATION_SEARCH,
        {"name": "Hitt Electric", "page_size": 100},
    )
    contact = adapt_it_glue_arguments(
        DOCUMENTATION_CONTACT_READ,
        {"resource_id": "42"},
    )
    configuration = adapt_it_glue_arguments(
        DOCUMENTATION_CONFIGURATION_SEARCH,
        {"organization_id": "208", "name": "AOT-50282"},
    )

    assert organization == {
        "entity": "Organizations",
        "filters": {"name": "Hitt Electric"},
        "page_size": 100,
    }
    assert contact == {"entity": "Contacts", "entity_id": "42"}
    assert configuration == {
        "entity": "Configurations",
        "filters": {"organization_id": "208", "name": "AOT-50282"},
        "page_size": 100,
    }
    assert "Passwords" not in {organization["entity"], contact["entity"], configuration["entity"]}


def test_it_glue_collection_search_is_bounded_by_default() -> None:
    adapted = adapt_it_glue_arguments(DOCUMENTATION_ORGANIZATION_SEARCH, {})
    assert adapted == {
        "entity": "Organizations",
        "filters": {},
        "page_size": 100,
    }

    for invalid_size in (0, 1001, True, "not-an-integer"):
        with pytest.raises(ValueError, match="page_size"):
            adapt_it_glue_arguments(
                DOCUMENTATION_ORGANIZATION_SEARCH,
                {"page_size": invalid_size},
            )


def test_autotask_adapter_builds_deterministic_structured_search() -> None:
    adapted = adapt_autotask_arguments(
        SERVICE_TICKET_SEARCH,
        {
            "ticket_number": "T20260909.0012",
            "company_id": 77,
            "filters": {"queueID": 8},
        },
    )

    query = json.loads(adapted["search"])
    assert query == {
        "MaxRecords": 100,
        "filter": [
            {"op": "eq", "field": "queueID", "value": 8},
            {"op": "eq", "field": "ticketNumber", "value": "T20260909.0012"},
            {"op": "eq", "field": "companyID", "value": 77},
        ],
    }


def test_autotask_adapter_preserves_exact_reads_notes_and_schema_description() -> None:
    assert adapt_autotask_arguments(
        SERVICE_TICKET_READ,
        {"resource_id": 101},
    ) == {"ticket_id": 101}
    assert adapt_autotask_arguments(
        SERVICE_TICKET_READ,
        {"ticket_id": 101},
    ) == {"ticket_id": 101}
    assert adapt_autotask_arguments(
        SERVICE_TICKET_READ,
        {"ticket_number": "T20260911.0010"},
    ) == {"ticket_id": "T20260911.0010"}
    assert adapt_autotask_arguments(
        SERVICE_TICKET_READ,
        {
            "ticket_id": "T20260911.0010",
            "resource_id": "T20260911.0010",
        },
    ) == {"ticket_id": "T20260911.0010"}
    with pytest.raises(ValueError, match="conflicting ticket selectors"):
        adapt_autotask_arguments(
            SERVICE_TICKET_READ,
            {"ticket_id": 101, "resource_id": "T20260911.0010"},
        )
    assert adapt_autotask_arguments(
        SERVICE_TICKET_NOTES_SEARCH,
        {"resource_id": 101},
    ) == {"ticket_id": 101}
    assert adapt_autotask_arguments(
        SERVICE_ENTITY_DESCRIBE,
        {"entity": "ConfigurationItems"},
    ) == {"entity": "ConfigurationItems"}


def test_autotask_company_search_supports_bounded_schema_driven_filters() -> None:
    adapted = adapt_autotask_arguments(
        SERVICE_COMPANY_SEARCH,
        {"filters": {"isActive": True}, "page_size": 25},
    )
    assert json.loads(adapted["search"]) == {
        "MaxRecords": 25,
        "filter": [
            {"op": "eq", "field": "isActive", "value": True},
        ],
    }


def test_autotask_collection_search_is_bounded_and_uses_valid_exist_filter() -> None:
    adapted = adapt_autotask_arguments(SERVICE_COMPANY_SEARCH, {})
    assert json.loads(adapted["search"]) == {
        "MaxRecords": 100,
        "filter": [{"op": "exist", "field": "id"}],
    }


def test_autotask_search_maps_durable_resource_identity_and_contact_fields() -> None:
    company = json.loads(
        adapt_autotask_arguments(
            SERVICE_COMPANY_SEARCH,
            {"resource_id": 321},
        )["search"]
    )
    contact = json.loads(
        adapt_autotask_arguments(
            SERVICE_CONTACT_SEARCH,
            {
                "company_id": 77,
                "first_name": "Paulette",
                "last_name": "Example",
                "email": "paulette@example.com",
            },
        )["search"]
    )

    assert company["filter"] == [{"op": "eq", "field": "id", "value": 321}]
    assert contact["filter"] == [
        {"op": "eq", "field": "companyID", "value": 77},
        {"op": "eq", "field": "firstName", "value": "Paulette"},
        {"op": "eq", "field": "lastName", "value": "Example"},
        {"op": "eq", "field": "emailAddress", "value": "paulette@example.com"},
    ]


def test_autotask_continuation_uses_durable_id_without_provider_url() -> None:
    continued = json.loads(
        adapt_autotask_arguments(
            SERVICE_TICKET_SEARCH,
            {
                "company_id": 77,
                "after_resource_id": "900",
                "page_size": 50,
            },
        )["search"]
    )
    assert continued == {
        "MaxRecords": 50,
        "filter": [
            {"op": "gt", "field": "id", "value": 900},
            {"op": "eq", "field": "companyID", "value": 77},
        ],
    }


def test_autotask_search_rejects_unbounded_or_provider_specific_escape_hatches() -> None:
    for invalid_size in (0, 501, True, "not-an-integer"):
        with pytest.raises(ValueError, match="page_size"):
            adapt_autotask_arguments(
                SERVICE_TICKET_SEARCH,
                {"page_size": invalid_size},
            )

    for invalid_after in (0, -1, True, "not-an-integer"):
        with pytest.raises(ValueError, match="after_resource_id"):
            adapt_autotask_arguments(
                SERVICE_TICKET_SEARCH,
                {"after_resource_id": invalid_after},
            )

    with pytest.raises(ValueError, match="after_resource_id cannot be combined"):
        adapt_autotask_arguments(
            SERVICE_TICKET_SEARCH,
            {"resource_id": 100, "after_resource_id": 99},
        )

    with pytest.raises(ValueError, match="provider-specific Autotask search"):
        adapt_autotask_arguments(
            SERVICE_TICKET_SEARCH,
            {"search": '{"filter":[]}'},
        )
