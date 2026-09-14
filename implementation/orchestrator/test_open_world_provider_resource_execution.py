from dataclasses import dataclass, field
from decimal import Decimal

import pytest

from kernel.execution_policy import DataHandlingPolicy, ExecutionBudget
from orchestrator.contracts import (
    ExecutionStage,
    OrchestrationMode,
    OrchestrationRequest,
    OrchestrationResult,
    OrchestrationStatus,
)
from orchestrator.open_world_execution import (
    OpenWorldExecutionCoordinator,
    OpenWorldExecutionError,
)
from orchestrator.open_world_schema import DiscoveredField, DiscoveredResourceSchema


def dynamic_resource():
    return DiscoveredResourceSchema(
        provider_id="example_provider",
        capability_name="provider.resource.search",
        resource_type="futureObject",
        operation="search",
        collection_supported=True,
        selector_keys=("id",),
        fields=(
            DiscoveredField(name="id", path="id", value_type="string"),
            DiscoveredField(name="friendly", path="friendly", value_type="string"),
        ),
        provider_resource_handle="example_provider:futureObjects",
    )


def test_dynamic_resource_binding_is_derived_from_catalog_not_model_arguments():
    coordinator = OpenWorldExecutionCoordinator(materializer=None, query_engine=None)
    intent = coordinator._intent(
        resource=dynamic_resource(),
        selector_reference="example literal",
        field_paths=("id", "friendly"),
    )

    assert intent.capability_name == "provider.resource.search"
    assert intent.permission_mode == "observe"
    assert intent.execution_mode == "deterministic"
    assert intent.arguments == {
        "selector": "example literal",
        "provider_resource_handle": "example_provider:futureObjects",
        "field_paths": ("id", "friendly"),
    }
    assert "required_provider_id" not in intent.arguments


def test_dynamic_resource_execution_revalidates_field_projection_fail_closed():
    coordinator = OpenWorldExecutionCoordinator(materializer=None, query_engine=None)
    with pytest.raises(OpenWorldExecutionError, match="outside the governed schema"):
        coordinator._intent(
            resource=dynamic_resource(),
            selector_reference=None,
            field_paths=("id", "notAField"),
        )


def test_existing_capability_intent_shape_does_not_change():
    coordinator = OpenWorldExecutionCoordinator(materializer=None, query_engine=None)
    resource = DiscoveredResourceSchema(
        provider_id="datto_rmm",
        capability_name="endpoint.device.search",
        resource_type="endpoint_device",
        operation="search",
        collection_supported=True,
        selector_keys=("selector",),
        fields=(DiscoveredField(name="name", path="name", value_type="string"),),
    )

    intent = coordinator._intent(
        resource=resource,
        selector_reference="AOT-50282",
        field_paths=("name",),
    )

    assert intent.capability_name == "endpoint.device.search"
    assert intent.arguments == {"selector": "AOT-50282"}


@dataclass
class RequestFactory:
    requests: list = field(default_factory=list)

    def build(self, *, principal, intent, identity, correlation_id):
        request = OrchestrationRequest(
            execution_id="exec-1",
            correlation_id=correlation_id,
            principal_id=principal.principal_id,
            organization_id=principal.organization_id,
            client_id=principal.client_id,
            capability_name=intent.capability_name,
            capability_version=None,
            requested_mode=intent.execution_mode,
            permission_mode=intent.permission_mode,
            orchestration_mode=OrchestrationMode.EXECUTE,
            authority_allowed=True,
            approval_present=False,
            risk=intent.risk,
            data_handling=DataHandlingPolicy(
                classification="internal",
                hosted_processing_allowed=False,
                retention_allowed=False,
            ),
            budget=ExecutionBudget(
                maximum_estimated_cost=Decimal("1.00"),
                maximum_attempts=1,
            ),
            arguments=dict(intent.arguments),
            requester_kind="human",
            authority_context_id="ctx-1",
        )
        self.requests.append(request)
        return request


@dataclass
class Principal:
    principal_id: str = "person-1"
    organization_id: str = "aot"
    client_id: str | None = "client-1"


@dataclass
class Identity:
    authentication_assurance: str = "mfa"


@dataclass
class Orchestrator:
    requests: list = field(default_factory=list)

    def execute(self, request):
        self.requests.append(request)
        return OrchestrationResult(
            execution_id=request.execution_id,
            correlation_id=request.correlation_id,
            capability_name=request.capability_name,
            status=OrchestrationStatus.SUCCEEDED,
            stage=ExecutionStage.COMPLETED,
            reason_codes=("test",),
            resolution=None,
            provider_id=request.required_provider_id,
        )


class Executor:
    def __init__(self):
        self.request_factory = RequestFactory()
        self.orchestrator = Orchestrator()
        self.principal = Principal()
        self.identity = Identity()
        self.correlation_id = "corr-1"
        self.results = []

    def _validate(self, *, request, intent):
        assert request.correlation_id == self.correlation_id
        assert request.capability_name == intent.capability_name


def test_provider_affinity_is_trusted_catalog_state_not_model_argument():
    coordinator = OpenWorldExecutionCoordinator(materializer=None, query_engine=None)
    executor = Executor()
    intent = coordinator._intent(
        resource=dynamic_resource(),
        selector_reference=None,
        field_paths=("id",),
    )

    result = coordinator._execute_provider_bound_intent(
        executor=executor,
        intent=intent,
        required_provider_id=dynamic_resource().provider_id,
    )

    assert executor.request_factory.requests[0].required_provider_id is None
    assert executor.orchestrator.requests[0].required_provider_id == "example_provider"
    assert "required_provider_id" not in intent.arguments
    assert result.provider_id == "example_provider"
    assert executor.results == [result]
