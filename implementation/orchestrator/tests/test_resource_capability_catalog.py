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
    ENDPOINT_ALERT_SEARCH,
    ENDPOINT_AUDIT_READ,
    ENDPOINT_SOFTWARE_SEARCH,
    MANAGEMENT_ALERT_SEARCH,
    MANAGEMENT_SITE_SEARCH,
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
    assert search.timeout_seconds == 60
    assert "exact read" in search.metadata["identity_semantics"]
    assert read.metadata["operation"] == "read"
    assert {
        ENDPOINT_DEVICE_SEARCH,
        ENDPOINT_DEVICE_READ,
        ENDPOINT_ALERT_SEARCH,
        ENDPOINT_AUDIT_READ,
        ENDPOINT_SOFTWARE_SEARCH,
        MANAGEMENT_ALERT_SEARCH,
        MANAGEMENT_SITE_SEARCH,
    } <= datto.capabilities
    assert datto.execution_modes == frozenset({"deterministic"})
    assert datto.limits.maximum_execution_seconds == 60


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
        "result_intent": "summary",
        "completeness_requirement": "sufficient",
    }


def test_reasoner_propagates_complete_collection_outcome():
    capabilities, _ = services()
    planner = GovernedResourceInquiryPlanner(
        registry=capabilities,
        reasoner=MetadataResourceCapabilityReasoner(),
    )

    plan = planner.plan(
        ResourceInquiry(
            resource_type="management_site",
            resource_selector={},
            requested_facts=("sites",),
            result_intent="enumerate",
            completeness_requirement="complete",
        )
    )

    assert len(plan.steps) == 1
    assert plan.steps[0].capability_name == MANAGEMENT_SITE_SEARCH
    assert plan.steps[0].arguments == {
        "requested_facts": ("sites",),
        "result_intent": "enumerate",
        "completeness_requirement": "complete",
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


def test_datto_provider_exposes_broad_governed_read_surface() -> None:
    from datetime import datetime, timezone

    from orchestrator.resource_capability_catalog import (
        ENDPOINT_ALERT_SEARCH,
        ENDPOINT_AUDIT_READ,
        ENDPOINT_DEVICE_READ,
        ENDPOINT_DEVICE_SEARCH,
        ENDPOINT_SOFTWARE_SEARCH,
        MANAGEMENT_ALERT_SEARCH,
        MANAGEMENT_SITE_SEARCH,
        datto_rmm_endpoint_provider,
        endpoint_alert_search,
        endpoint_audit_read,
        endpoint_software_search,
        management_alert_search,
        management_site_search,
    )

    now = datetime.now(timezone.utc)
    provider = datto_rmm_endpoint_provider(now)

    assert {
        ENDPOINT_DEVICE_SEARCH,
        ENDPOINT_DEVICE_READ,
        ENDPOINT_ALERT_SEARCH,
        ENDPOINT_AUDIT_READ,
        ENDPOINT_SOFTWARE_SEARCH,
        MANAGEMENT_ALERT_SEARCH,
        MANAGEMENT_SITE_SEARCH,
    } <= provider.capabilities

    definitions = (
        endpoint_alert_search(now),
        endpoint_audit_read(now),
        endpoint_software_search(now),
        management_alert_search(now),
        management_site_search(now),
    )

    assert all(item.metadata["provider_neutral"] == "true" for item in definitions)
    assert all(item.metadata["read_only"] == "true" for item in definitions)

    hints = ",".join(item.metadata["fact_hints"] for item in definitions)
    assert "alert" in hints
    assert "bios" in hints
    assert "software" in hints
    assert "site" in hints


def test_management_resource_inquiry_hints_do_not_cross_match_incidental_site_fields():
    from orchestrator.resource_capability_catalog import (
        management_alert_search,
        management_site_search,
    )

    alerts = management_alert_search(NOW)
    sites = management_site_search(NOW)

    assert "site" in sites.metadata["inquiry_hints"].split(",")
    assert "site" not in alerts.metadata["inquiry_hints"].split(",")
    assert "site" in alerts.metadata["fact_hints"].split(",")


def test_metadata_reasoner_preserves_semantic_evidence_and_relationship_contract():
    capabilities, _ = services()
    planner = GovernedResourceInquiryPlanner(
        registry=capabilities,
        reasoner=MetadataResourceCapabilityReasoner(),
    )

    plan = planner.plan(
        ResourceInquiry(
            resource_type="endpoint",
            resource_selector={"user_identity": "Lindsey Collins"},
            requested_facts=("operating system display version",),
            evidence_contexts={
                "operating system display version": (
                    "operating_system",
                    "windows_release",
                ),
            },
            relationship_type="logged_in_to",
            temporal_semantics="most_recent",
        )
    )

    assert plan.steps[0].arguments["evidence_contexts"] == {
        "operating system display version": (
            "operating_system",
            "windows_release",
        ),
    }
    assert plan.steps[0].arguments["relationship_type"] == "logged_in_to"
    assert plan.steps[0].arguments["temporal_semantics"] == "most_recent"
