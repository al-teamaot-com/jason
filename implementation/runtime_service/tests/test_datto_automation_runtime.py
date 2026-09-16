from __future__ import annotations

from datetime import datetime, timezone

from connectors.datto_rmm.capability_manifest import build_datto_rmm_manifest
from connectors.datto_rmm.automation_reads import DattoRmmAutomationReadConnector
from kernel.capabilities import CapabilityRegistryService, InMemoryCapabilityRegistry
from kernel.execution_providers import (
    ExecutionProviderRegistryService,
    InMemoryExecutionProviderRegistry,
)
from orchestrator.capability_routing_invoker import CanonicalCapabilityRoutingInvoker
from orchestrator.integration_broker import IntegrationBroker
from orchestrator.invokers import CapabilityInvokerRegistry
from orchestrator.resource_capability_catalog import (
    AUTOMATION_COMPONENT_SEARCH,
    AUTOMATION_JOB_READ,
    AUTOMATION_JOB_OUTPUT_READ,
    DATTO_RMM_PROVIDER,
    register_endpoint_resource_foundation,
)
from jason_runtime.provider_reads import (
    build_provider_read_invoker,
    register_provider_read_invokers,
)


class Secrets:
    def resolve(self, logical_name, context):
        raise AssertionError("composition test must not resolve provider secrets")


class Transport:
    def request(self, **kwargs):
        raise AssertionError("composition test must not contact provider APIs")


class Audit:
    def record(self, event_type, context, details):
        return None


def test_datto_provider_declares_automation_reads_without_execution() -> None:
    capabilities = CapabilityRegistryService(
        registry=InMemoryCapabilityRegistry()
    )
    providers = ExecutionProviderRegistryService(
        registry=InMemoryExecutionProviderRegistry()
    )
    register_endpoint_resource_foundation(
        capabilities=capabilities,
        providers=providers,
        now=datetime(2026, 9, 14, tzinfo=timezone.utc),
    )

    component = capabilities.get_current(
        capability_name=AUTOMATION_COMPONENT_SEARCH
    )
    job = capabilities.get_current(
        capability_name=AUTOMATION_JOB_READ
    )
    output = capabilities.get_current(
        capability_name=AUTOMATION_JOB_OUTPUT_READ
    )
    provider = providers.get(DATTO_RMM_PROVIDER)

    assert component.metadata["read_only"] == "true"
    assert job.metadata["read_only"] == "true"
    assert output.metadata["read_only"] == "true"
    assert AUTOMATION_COMPONENT_SEARCH in provider.capabilities
    assert AUTOMATION_JOB_READ in provider.capabilities
    assert AUTOMATION_JOB_OUTPUT_READ in provider.capabilities
    assert "automation.component.execute" not in provider.capabilities


def test_datto_integration_broker_exposes_read_only_automation_resources() -> None:
    capabilities = CapabilityRegistryService(
        registry=InMemoryCapabilityRegistry()
    )
    providers = ExecutionProviderRegistryService(
        registry=InMemoryExecutionProviderRegistry()
    )
    register_endpoint_resource_foundation(
        capabilities=capabilities,
        providers=providers,
        now=datetime(2026, 9, 14, tzinfo=timezone.utc),
    )
    broker = IntegrationBroker(
        capabilities=capabilities,
        providers=providers,
    )
    broker.register(build_datto_rmm_manifest())

    manifest = broker.get_manifest(DATTO_RMM_PROVIDER)
    component = manifest.resource("automation_component")
    job = manifest.resource("automation_job")

    assert component is not None
    assert job is not None
    assert component.operations[0].capability_name == AUTOMATION_COMPONENT_SEARCH
    assert component.operations[0].read_only is True
    operations = {
        operation.capability_name: operation
        for operation in job.operations
    }
    assert AUTOMATION_JOB_READ in operations
    assert AUTOMATION_JOB_OUTPUT_READ in operations
    assert operations[AUTOMATION_JOB_READ].read_only is True
    assert operations[AUTOMATION_JOB_OUTPUT_READ].read_only is True
    assert all(
        operation.read_only
        for resource in (component, job)
        for operation in resource.operations
    )


def test_runtime_read_invoker_routes_datto_automation_without_write_surface() -> None:
    invoker = build_provider_read_invoker(
        secrets=Secrets(),
        transport=Transport(),
        audit=Audit(),
    )

    assert isinstance(invoker, CanonicalCapabilityRoutingInvoker)
    assert AUTOMATION_COMPONENT_SEARCH in invoker.routes
    assert AUTOMATION_JOB_READ in invoker.routes
    assert AUTOMATION_JOB_OUTPUT_READ in invoker.routes
    assert "automation.component.execute" not in invoker.routes

    registry = CapabilityInvokerRegistry()
    register_provider_read_invokers(
        invokers=registry,
        invoker=invoker,
    )
    registered = set(registry.registered_capabilities())

    assert AUTOMATION_COMPONENT_SEARCH in registered
    assert AUTOMATION_JOB_READ in registered
    assert AUTOMATION_JOB_OUTPUT_READ in registered
    assert "automation.component.execute" not in registered


def test_datto_job_output_path_is_exact_and_read_only() -> None:
    path, params = DattoRmmAutomationReadConnector._resolve_operation(
        "datto_rmm.job.output.read",
        {
            "resource_id": "job-123",
            "device_uid": "device-123",
            "component_uid": "component-456",
            "stream": "stdout",
        },
    )

    assert path == (
        "/api/v2/job/job-123/results/device-123/stdout"
    )
    assert params is None

    path, _ = DattoRmmAutomationReadConnector._resolve_operation(
        "datto_rmm.job.output.read",
        {
            "resource_id": "job-123",
            "device_uid": "device-123",
            "component_uid": "component-456",
            "stream": "stderr",
        },
    )
    assert path.endswith("/stderr")

    try:
        DattoRmmAutomationReadConnector._resolve_operation(
            "datto_rmm.job.output.read",
            {
                "resource_id": "job-123",
                "device_uid": "device-123",
                "component_uid": "component-456",
                "stream": "other",
            },
        )
    except ValueError as exc:
        assert str(exc) == "stream must be stdout or stderr"
    else:
        raise AssertionError(
            "unsupported job output stream must fail closed"
        )


def test_datto_job_output_filters_component_and_bounds_text() -> None:
    maximum = (
        DattoRmmAutomationReadConnector.maximum_job_output_chars
    )

    result = (
        DattoRmmAutomationReadConnector
        ._canonical_job_output_result(
            payload=[
                {
                    "componentUid": "other-component",
                    "componentName": "Other",
                    "stdData": "must-not-escape",
                },
                {
                    "componentUid": "component-456",
                    "componentName": "DNS Diagnostic",
                    "stdData": "x" * (maximum + 50),
                },
            ],
            arguments={
                "resource_id": "job-123",
                "device_uid": "device-123",
                "component_uid": "component-456",
                "stream": "stdout",
            },
        )
    )

    assert result["resource_id"] == "job-123"
    assert result["device_uid"] == "device-123"
    assert result["component_uid"] == "component-456"
    assert result["stream"] == "stdout"
    assert result["match_count"] == 1
    assert result["output_bounded"] is True
    assert len(result["outputs"]) == 1
    assert len(result["outputs"][0]["text"]) == maximum
    assert result["outputs"][0]["truncated"] is True
    assert "must-not-escape" not in str(result)
