from __future__ import annotations

from connectors.datto_rmm.automation_manifest import (
    build_datto_rmm_automation_resources,
)
from orchestrator.integration_broker import OperationKind


def test_automation_resources_are_provider_neutral_read_only_capabilities() -> None:
    resources = build_datto_rmm_automation_resources()

    assert [resource.resource_type for resource in resources] == [
        "automation_component",
        "automation_job",
    ]

    component, job = resources

    component_operation = component.operations[0]
    assert component_operation.operation_id == "automation.component.search"
    assert component_operation.capability_name == "automation.component.search"
    assert component_operation.kind is OperationKind.SEARCH
    assert component_operation.read_only is True
    assert component_operation.collection_supported is True
    assert component_operation.selector_names == ("name",)

    job_operation = job.operations[0]
    assert job_operation.operation_id == "automation.job.read"
    assert job_operation.capability_name == "automation.job.read"
    assert job_operation.kind is OperationKind.READ
    assert job_operation.read_only is True
    assert job_operation.collection_supported is False
    assert job_operation.selector_names == ("resource_id",)


def test_job_resource_requires_verified_durable_identity() -> None:
    _, job = build_datto_rmm_automation_resources()
    selector = job.selectors[0]

    assert selector.name == "resource_id"
    assert selector.verified_identity_required is True


def test_read_foundation_does_not_advertise_execution() -> None:
    resources = build_datto_rmm_automation_resources()
    capabilities = {
        operation.capability_name
        for resource in resources
        for operation in resource.operations
    }

    assert capabilities == {
        "automation.component.search",
        "automation.job.read",
        "automation.job.output.read",
    }
    assert "automation.component.execute" not in capabilities