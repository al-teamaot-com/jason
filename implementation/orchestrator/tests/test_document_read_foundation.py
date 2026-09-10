from datetime import datetime, timezone

from connectors.it_glue.capability_manifest import build_it_glue_manifest
from kernel.capabilities import CapabilityLifecycle, CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_providers import ExecutionProviderRegistryService, InMemoryExecutionProviderRegistry
from orchestrator.provider_read_argument_adapter import adapt_it_glue_arguments
from orchestrator.provider_read_capability_catalog import (
    DOCUMENTATION_DOCUMENT_READ,
    DOCUMENTATION_DOCUMENT_SEARCH,
    register_provider_read_foundation,
)


NOW = datetime(2026, 9, 10, tzinfo=timezone.utc)


def test_it_glue_document_capabilities_are_provider_neutral_read_only_and_pilot() -> None:
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
    register_provider_read_foundation(capabilities=capabilities, providers=providers, now=NOW)

    search = capabilities.get_current(
        capability_name=DOCUMENTATION_DOCUMENT_SEARCH,
        allow_pilot=True,
    )
    exact = capabilities.get_current(
        capability_name=DOCUMENTATION_DOCUMENT_READ,
        allow_pilot=True,
    )

    assert search.lifecycle_status is CapabilityLifecycle.PILOT
    assert exact.lifecycle_status is CapabilityLifecycle.PILOT
    assert search.metadata["provider_neutral"] == "true"
    assert exact.metadata["provider_neutral"] == "true"
    assert search.metadata["read_only"] == "true"
    assert exact.metadata["read_only"] == "true"
    assert "policy" in search.metadata["fact_hints"]


def test_it_glue_document_manifest_and_adapter_do_not_expose_password_resources() -> None:
    manifest = build_it_glue_manifest()
    resources = {resource.resource_type: resource for resource in manifest.resources}
    document = resources["documentation_document"]
    capabilities = {operation.capability_name for operation in document.operations}

    assert capabilities == {
        DOCUMENTATION_DOCUMENT_SEARCH,
        DOCUMENTATION_DOCUMENT_READ,
    }
    assert manifest.metadata["excluded_sensitive_resources"] == "passwords,credential_vault"

    search = adapt_it_glue_arguments(
        DOCUMENTATION_DOCUMENT_SEARCH,
        {
            "organization_id": "208",
            "name": "Remote Access Policy",
            "page_size": 25,
        },
    )
    exact = adapt_it_glue_arguments(
        DOCUMENTATION_DOCUMENT_READ,
        {"resource_id": "42"},
    )

    assert search == {
        "entity": "Documents",
        "filters": {
            "organization_id": "208",
            "name": "Remote Access Policy",
        },
        "page_size": 25,
    }
    assert exact == {"document_id": "42"}
    assert "Passwords" not in str(search)
    assert "credential_vault" not in str(search)
