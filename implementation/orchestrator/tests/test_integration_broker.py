from dataclasses import replace
from datetime import datetime, timezone

import pytest

from connectors.datto_rmm.capability_manifest import (
    build_datto_rmm_manifest,
)
from kernel.capabilities import (
    CapabilityRegistryService,
    InMemoryCapabilityRegistry,
)
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
    ProviderHealth,
)
from orchestrator.integration_broker import (
    DuplicateIntegrationError,
    IntegrationBroker,
    IntegrationManifestValidationError,
)
from orchestrator.resource_capability_catalog import (
    DATTO_RMM_PROVIDER,
    register_endpoint_resource_foundation,
)


def runtime_registries():
    capabilities = CapabilityRegistryService(
        registry=InMemoryCapabilityRegistry()
    )
    providers = ExecutionProviderRegistryService(
        registry=InMemoryExecutionProviderRegistry()
    )

    register_endpoint_resource_foundation(
        capabilities=capabilities,
        providers=providers,
        now=datetime.now(timezone.utc),
    )

    return capabilities, providers


def broker():
    capabilities, providers = runtime_registries()

    return (
        IntegrationBroker(
            capabilities=capabilities,
            providers=providers,
        ),
        capabilities,
        providers,
    )


def test_drmm_manifest_is_descriptive_not_runtime_health_authority():
    manifest = build_datto_rmm_manifest()

    assert manifest.integration_id == "datto_rmm"
    assert manifest.provider_id == DATTO_RMM_PROVIDER

    assert not hasattr(manifest, "health")

    endpoint = manifest.resource("endpoint")
    assert endpoint is not None

    assert {
        operation.capability_name
        for operation in endpoint.operations
    } >= {
        "endpoint.device.search",
        "endpoint.device.read",
        "endpoint.audit.read",
        "endpoint.software.search",
    }


def test_broker_registers_manifest_against_existing_kernel_state():
    instance, _, _ = broker()

    instance.register(build_datto_rmm_manifest())

    view = instance.get("datto_rmm")

    assert view.integration_id == "datto_rmm"
    assert view.provider_health == "healthy"
    assert view.provider_lifecycle == "available"
    assert view.provider_approval in {"approved", "pilot"}
    assert view.operational is True


def test_broker_derives_health_live_from_provider_registry():
    instance, _, providers = broker()

    instance.register(build_datto_rmm_manifest())

    before = instance.get("datto_rmm")
    assert before.provider_health == "healthy"
    assert before.operational is True

    providers.set_health(
        provider_id=DATTO_RMM_PROVIDER,
        health_status=ProviderHealth.UNAVAILABLE,
    )

    after = instance.get("datto_rmm")

    assert after.provider_health == "unavailable"
    assert after.operational is False


def test_nonoperational_integration_hidden_from_normal_discovery():
    instance, _, providers = broker()

    instance.register(build_datto_rmm_manifest())

    providers.set_health(
        provider_id=DATTO_RMM_PROVIDER,
        health_status=ProviderHealth.UNAVAILABLE,
    )

    assert instance.integrations_for_resource("endpoint") == ()

    visible = instance.integrations_for_resource(
        "endpoint",
        include_nonoperational=True,
    )

    assert len(visible) == 1
    assert visible[0].integration_id == "datto_rmm"
    assert visible[0].operational is False


def test_broker_exposes_registered_operations_for_resource():
    instance, _, _ = broker()

    instance.register(build_datto_rmm_manifest())

    operations = instance.operations_for_resource("endpoint")

    assert {
        operation.operation_id
        for _, operation in operations
    } >= {
        "endpoint.search",
        "endpoint.read",
        "endpoint.alerts.open",
        "endpoint.audit.read",
    }


def test_manifest_capability_must_exist_in_capability_registry():
    instance, _, _ = broker()

    manifest = build_datto_rmm_manifest()
    endpoint = manifest.resource("endpoint")
    assert endpoint is not None

    bad_operation = replace(
        endpoint.operations[0],
        capability_name="future.unknown.read",
    )
    bad_endpoint = replace(
        endpoint,
        operations=(
            bad_operation,
            *endpoint.operations[1:],
        ),
    )
    bad_manifest = replace(
        manifest,
        resources=(
            bad_endpoint,
            *manifest.resources[1:],
        ),
    )

    with pytest.raises(
        IntegrationManifestValidationError,
        match="unavailable governed capability",
    ):
        instance.register(bad_manifest)


def test_manifest_capability_must_be_supported_by_provider():
    instance, capabilities, providers = broker()

    provider = providers.get(DATTO_RMM_PROVIDER)

    providers._registry._providers[DATTO_RMM_PROVIDER] = replace(
        provider,
        capabilities=frozenset(
            capability
            for capability in provider.capabilities
            if capability != "endpoint.device.read"
        ),
    )

    with pytest.raises(
        IntegrationManifestValidationError,
        match="does not declare support",
    ):
        instance.register(build_datto_rmm_manifest())


def test_manifest_operation_cannot_reference_undeclared_selector():
    instance, _, _ = broker()

    manifest = build_datto_rmm_manifest()
    endpoint = manifest.resource("endpoint")
    assert endpoint is not None

    bad_operation = replace(
        endpoint.operations[0],
        selector_names=("hostname", "invented_selector"),
    )
    bad_endpoint = replace(
        endpoint,
        operations=(
            bad_operation,
            *endpoint.operations[1:],
        ),
    )
    bad_manifest = replace(
        manifest,
        resources=(
            bad_endpoint,
            *manifest.resources[1:],
        ),
    )

    with pytest.raises(
        IntegrationManifestValidationError,
        match="selectors not declared",
    ):
        instance.register(bad_manifest)


def test_duplicate_integration_fails_closed():
    instance, _, _ = broker()

    manifest = build_datto_rmm_manifest()

    instance.register(manifest)

    with pytest.raises(DuplicateIntegrationError):
        instance.register(manifest)


def test_model_context_exposes_resources_without_provider_identity():
    from orchestrator.integration_broker import (
        broker_model_context,
    )

    instance, _, _ = broker()
    instance.register(build_datto_rmm_manifest())

    context = broker_model_context(instance)

    assert "resources" in context
    assert context["resources"]

    serialized = repr(context)

    assert "datto_rmm" not in serialized
    assert "provider_id" not in serialized
    assert "capability_name" not in serialized

    endpoint = next(
        item
        for item in context["resources"]
        if item["resource_type"] == "endpoint"
    )

    assert {
        item["kind"]
        for item in endpoint["operations"]
    } >= {
        "search",
        "read",
    }

    assert all(
        item["operation_ref"].startswith("operation_")
        for item in endpoint["operations"]
    )


def test_model_context_grows_from_registered_integrations_without_reasoning_code_change():
    from dataclasses import replace

    from orchestrator.integration_broker import (
        broker_model_context,
    )

    instance, _, providers = broker()
    manifest = build_datto_rmm_manifest()

    reduced = replace(
        manifest,
        resources=(
            manifest.resource("endpoint"),
        ),
    )

    instance.register(reduced)

    context = broker_model_context(instance)

    assert {
        item["resource_type"]
        for item in context["resources"]
    } == {"endpoint"}

    providers.set_health(
        provider_id=DATTO_RMM_PROVIDER,
        health_status=ProviderHealth.UNAVAILABLE,
    )

    degraded_context = broker_model_context(instance)

    assert degraded_context["resources"] == []
