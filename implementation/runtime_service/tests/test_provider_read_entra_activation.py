from __future__ import annotations

from datetime import datetime, timezone

from kernel.capabilities import (
    CapabilityLifecycle,
    CapabilityRegistryService,
    InMemoryCapabilityRegistry,
)
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
    ProviderApproval,
    ProviderHealth,
    ProviderLifecycle,
)
from orchestrator.provider_read_capability_catalog import (
    AUTOTASK_CAPABILITIES,
    AUTOTASK_PROVIDER,
    IT_GLUE_CAPABILITIES,
    IT_GLUE_PROVIDER,
    MICROSOFT_GRAPH_CAPABILITIES,
    MICROSOFT_GRAPH_DIRECTORY_CAPABILITIES,
    MICROSOFT_GRAPH_PROVIDER,
    register_provider_read_foundation,
)
from jason_runtime.provider_read_activation import (
    PROVIDER_READ_ENTRA_GOVERNED_CATALOG_CAPABILITIES,
    PROVIDER_READ_AUTOTASK_PROCUREMENT_CAPABILITIES,
    PROVIDER_READ_ENTRA_GOVERNED_CATALOG_PROFILE,
    PROVIDER_READ_GOVERNED_CATALOG_PROFILE,
    apply_provider_read_activation_profile,
)


def registries():
    capabilities = CapabilityRegistryService(registry=InMemoryCapabilityRegistry())
    providers = ExecutionProviderRegistryService(registry=InMemoryExecutionProviderRegistry())
    register_provider_read_foundation(
        capabilities=capabilities,
        providers=providers,
        now=datetime(2026, 9, 14, tzinfo=timezone.utc),
    )
    return capabilities, providers


def test_v3_does_not_silently_activate_new_microsoft_provider():
    capabilities, providers = registries()

    state = apply_provider_read_activation_profile(
        capabilities=capabilities,
        providers=providers,
        profile=PROVIDER_READ_GOVERNED_CATALOG_PROFILE,
    )

    assert set(state.provider_ids) == {IT_GLUE_PROVIDER, AUTOTASK_PROVIDER}
    legacy_autotask = (AUTOTASK_CAPABILITIES - PROVIDER_READ_AUTOTASK_PROCUREMENT_CAPABILITIES
                       - {"service.entity.search", "service.entity.read"})
    assert set(state.capability_names) == IT_GLUE_CAPABILITIES | legacy_autotask
    for capability_name in PROVIDER_READ_AUTOTASK_PROCUREMENT_CAPABILITIES:
        assert capabilities.get(
            capability_name=capability_name,
            version="1.0",
        ).lifecycle_status is CapabilityLifecycle.PILOT

    microsoft = providers.get(MICROSOFT_GRAPH_PROVIDER)
    assert microsoft.lifecycle_status is ProviderLifecycle.PLANNED
    assert microsoft.health_status is ProviderHealth.UNKNOWN
    assert microsoft.approval_status is ProviderApproval.PILOT
    for capability_name in MICROSOFT_GRAPH_CAPABILITIES:
        assert capabilities.get(
            capability_name=capability_name,
            version="1.0",
        ).lifecycle_status is CapabilityLifecycle.PILOT


def test_v4_explicitly_activates_itglue_autotask_and_entra_reads():
    capabilities, providers = registries()

    state = apply_provider_read_activation_profile(
        capabilities=capabilities,
        providers=providers,
        profile=PROVIDER_READ_ENTRA_GOVERNED_CATALOG_PROFILE,
    )

    legacy_autotask = (AUTOTASK_CAPABILITIES - PROVIDER_READ_AUTOTASK_PROCUREMENT_CAPABILITIES
                       - {"service.entity.search", "service.entity.read"})
    expected = IT_GLUE_CAPABILITIES | legacy_autotask | MICROSOFT_GRAPH_DIRECTORY_CAPABILITIES
    assert PROVIDER_READ_ENTRA_GOVERNED_CATALOG_CAPABILITIES == expected
    assert set(state.capability_names) == expected
    assert set(state.provider_ids) == {
        IT_GLUE_PROVIDER,
        AUTOTASK_PROVIDER,
        MICROSOFT_GRAPH_PROVIDER,
    }

    for provider_id in state.provider_ids:
        provider = providers.get(provider_id)
        assert provider.lifecycle_status is ProviderLifecycle.AVAILABLE
        assert provider.health_status is ProviderHealth.HEALTHY
        assert provider.approval_status is ProviderApproval.APPROVED

    for capability_name in expected:
        capability = capabilities.get(
            capability_name=capability_name,
            version="1.0",
        )
        assert capability.lifecycle_status is CapabilityLifecycle.ACTIVE
        assert capability.metadata["read_only"] == "true"

    for capability_name in PROVIDER_READ_AUTOTASK_PROCUREMENT_CAPABILITIES:
        assert capabilities.get(
            capability_name=capability_name,
            version="1.0",
        ).lifecycle_status is CapabilityLifecycle.PILOT
    for capability_name in MICROSOFT_GRAPH_CAPABILITIES - MICROSOFT_GRAPH_DIRECTORY_CAPABILITIES:
        assert capabilities.get(
            capability_name=capability_name,
            version="1.0",
        ).lifecycle_status is CapabilityLifecycle.PILOT

    # Regression coverage for the governed Entra read surface:
    # directory capabilities must be the ones promoted by the read-activation profile.
    assert MICROSOFT_GRAPH_DIRECTORY_CAPABILITIES == {
        capability_name
        for capability_name in MICROSOFT_GRAPH_DIRECTORY_CAPABILITIES
    }


def test_v13_dynamic_schema_activation_is_one_generic_pair_without_new_mutations():
    from connectors.autotask.dynamic_schema_read import DYNAMIC_READ_PROFILE
    from orchestrator.provider_read_capability_catalog import SERVICE_ENTITY_SEARCH, SERVICE_ENTITY_READ
    from jason_runtime.provider_read_activation import (
        PROVIDER_READ_AUTOTASK_COMPREHENSIVE_ENTITY_READ_PROFILE,
    )
    caps, providers = registries()
    dynamic = apply_provider_read_activation_profile(
        capabilities=caps, providers=providers, profile=DYNAMIC_READ_PROFILE,
    )
    old_caps, old_providers = registries()
    v11 = apply_provider_read_activation_profile(
        capabilities=old_caps, providers=old_providers,
        profile=PROVIDER_READ_AUTOTASK_COMPREHENSIVE_ENTITY_READ_PROFILE,
    )
    assert set(dynamic.capability_names) == set(v11.capability_names)
    assert set(dynamic.provider_ids) == set(v11.provider_ids)
    assert SERVICE_ENTITY_SEARCH in dynamic.capability_names
    assert SERVICE_ENTITY_READ in dynamic.capability_names
    assert all("service.entity." not in name or name in {
        SERVICE_ENTITY_SEARCH, SERVICE_ENTITY_READ, "service.entity.describe",
        "service.entity.fields.describe", "service.entity.udf.fields.describe",
    } for name in dynamic.capability_names)
